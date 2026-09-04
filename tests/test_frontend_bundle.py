"""Frontend bundle regression: app.min.css must include page-level styles.

Regression: build script took only outputFiles[0] of a 5-entry esbuild CSS
bundle -> only base.css shipped -> home grid/filter/toggle styles lost.
This test asserts the bundled CSS contains selectors that only live in
index.css / new-books.css (would have caught the original bug).
"""

from pathlib import Path

DIST = Path(__file__).resolve().parent.parent / 'static' / 'dist' / 'app.min.css'

REQUIRED_SELECTORS = (
    '.books-grid',      # index.css only
    '.filter-bar',      # components.css (index/new-books variants)
    '.view-toggle',     # index.css only
    '.card-badge',      # index.css only
    '.card',            # base/components shared
    '.top-nav',         # base.css global
)


def test_bundle_contains_page_selectors():
    assert DIST.exists(), f'{DIST} missing - run node scripts/build_frontend.mjs'
    css = DIST.read_text(encoding='utf-8')
    missing = [sel for sel in REQUIRED_SELECTORS if sel not in css]
    assert not missing, f'bundled CSS missing selectors: {missing}'


def test_bundle_not_only_base_size():
    """Bundle must exceed a bare base.css min (~16KB) - guards against the
    outputFiles[0]-only regression (only base.css shipped before)."""
    css = DIST.read_text(encoding='utf-8')
    assert len(css) > 40000, f'bundle suspiciously small ({len(css)} bytes) - likely single-entry'
