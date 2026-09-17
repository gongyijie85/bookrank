"""Wiki sync script tests (ROADMAP #7)."""

from pathlib import Path

from scripts.sync_wiki import _wiki_name


def test_wiki_name_mapping():
    assert _wiki_name('Code Wiki 索引.md') == 'Home.md'
    assert _wiki_name('三-数据库模型.md') == '三-数据库模型.md'
    assert _wiki_name('other.md') == 'other.md'


def test_script_dry_run_runs():
    """dry-run 可执行且退出码 0（克隆 public wiki + 对比本地镜像）。"""
    import scripts.sync_wiki as m

    m.LOCAL_WIKI_DIR = Path(__file__).resolve().parent.parent / 'Code Wiki'
    code = m.main()
    assert code == 0
