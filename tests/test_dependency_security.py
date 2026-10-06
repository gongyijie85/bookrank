"""Exercise upstream file-serving protection required by our dependency pins."""

import ntpath
from types import SimpleNamespace

import pytest
from werkzeug import security


@pytest.mark.parametrize('filename', ['NUL:', 'aux:', 'con.txt:', 'nested/COM1:'])
def test_safe_join_rejects_windows_device_names_with_empty_ads(monkeypatch, filename):
    # Emulate only this module's Windows path checks on Linux CI; do not mutate
    # the process-wide os module or open a device that could hang the test.
    monkeypatch.setattr(security, 'os', SimpleNamespace(name='nt', path=ntpath))

    assert security.safe_join('public', filename) is None


def test_safe_join_keeps_ordinary_windows_file_paths(monkeypatch):
    monkeypatch.setattr(security, 'os', SimpleNamespace(name='nt', path=ntpath))

    assert security.safe_join('public', 'covers/book.jpg') == 'public/covers/book.jpg'
