"""Source alert service tests (GitHub issue alerts; was 0%)."""

from unittest.mock import MagicMock, patch

import pytest

from app.models.new_book import Publisher
from app.services import source_alert_service as sas


@pytest.fixture
def degraded_publisher(app, db):
    with app.app_context():
        pub = Publisher(
            name='哈珀柯林斯',
            name_en='HarperCollins',
            crawler_class='Dummy',
            is_active=True,
            source_status='degraded',
            consecutive_failures=3,
            last_error_code='E',
            last_error_summary='boom',
        )
        db.session.add(pub)
        db.session.commit()
        yield pub
        db.session.remove()


class FakeClient:
    def __init__(self, existing=None):
        self.existing = existing
        self.created = []
        self.updated = []
        self.commented = []
        self.closed = []
        self.find_calls = 0

    def find_open_by_title(self, title):
        self.find_calls += 1
        return self.existing

    def create_issue(self, title, body, labels=None):
        self.created.append({'number': 101, 'title': title, 'body': body, 'labels': labels})
        return self.created[-1]

    def update_issue(self, number, body):
        self.updated.append((number, body))

    def add_comment(self, number, body):
        self.commented.append((number, body))

    def close_issue(self, number, comment=None):
        self.closed.append((number, comment))


def test_alert_title():
    assert sas.alert_title('HARPERCOLLINS') == '[source-degraded] harpercollins'


def test_get_github_client_null_when_unconfigured():
    with patch.dict('os.environ', {}, clear=True):
        client = sas.get_github_client()
        assert isinstance(client, sas.NullGithubClient)


def test_get_github_client_urtllib_when_configured():
    with patch.dict('os.environ', {'GITHUB_TOKEN': 't', 'GITHUB_REPOSITORY': 'o/r'}):
        client = sas.get_github_client()
        assert isinstance(client, sas.UrllibGithubClient)


def test_sync_creates_when_no_existing(app, db, degraded_publisher):
    fake = FakeClient(existing=None)
    with patch.object(sas, 'get_github_client', return_value=fake):
        result = sas.sync_degraded_alert('harpercollins', degraded_publisher)
    assert result is not None
    assert len(fake.created) == 1
    assert fake.created[0]['title'] == '[source-degraded] harpercollins'
    assert fake.created[0]['labels'] == ['source-health']
    # issue map 持久化
    mapped = sas._load_issue_map()
    assert mapped.get('harpercollins') == 101


def test_sync_updates_existing(app, db, degraded_publisher):
    fake = FakeClient(existing={'number': 55, 'title': '[source-degraded] harpercollins', 'state': 'open'})
    with patch.object(sas, 'get_github_client', return_value=fake):
        result = sas.sync_degraded_alert('harpercollins', degraded_publisher)
    assert result['number'] == 55
    assert len(fake.updated) == 1
    assert len(fake.created) == 0


def test_sync_noop_when_not_degraded(app, db):
    pub = MagicMock()
    pub.source_status = 'healthy'
    with patch.object(sas, 'get_github_client') as mock_client:
        result = sas.sync_degraded_alert('harpercollins', pub)
    assert result is None
    mock_client.assert_not_called()


def test_close_alert(app, db):
    fake = FakeClient(existing={'number': 60, 'title': '[source-degraded] harpercollins'})
    with patch.object(sas, 'get_github_client', return_value=fake):
        sas.close_degraded_alert('harpercollins', recovery_batch_id='b9')
    assert len(fake.closed) == 1
    number, comment = fake.closed[0]
    assert number == 60
    assert 'b9' in comment
