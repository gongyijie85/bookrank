## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues for `gongyijie85/bookrank`. See `docs/agents/issue-tracker.md`.

### Triage labels

Issues use the five canonical triage labels, plus type, priority (`p0`–`p3`) and module labels
(e.g. `awards`, `new-books`, `mobile`, `i18n`). Apply labels when creating or triaging an
issue. See `docs/agents/triage-labels.md`.

### Domain docs

This is a single-context repo. See `docs/agents/domain.md`.

## Verify your change (command surface)

Run from the repo root. CI runs the same commands, so local green ≈ CI green:

```bash
ruff check app/ tests/          # lint, must be clean
ruff format --check app/ tests/ # formatting gate (run `ruff format` to fix)
mypy app/                       # type gate, zero errors (pyproject whitelist is the only config)
python -m pytest tests/         # ~2300 tests, coverage gate --cov-fail-under=70 (currently ~83%)
make check                      # all of the above + pybabel translations extract/update/compile
```

Notes:

- `mypy` takes no CLI flags: `pyproject.toml [tool.mypy]` is the single source of truth.
  Do not re-add `--ignore-missing-imports` or `disable_error_code` overrides.
- Column operators (`.is_()/.desc()/.ilike()`) and `db.Model` bases are known mypy
  false positives: line-level `# type: ignore[...]` with a narrow code list is the
  convention (see `app/services/new_book/query_service.py`). Do not broaden to
  module-level disables.
- Frontend: `node scripts/build_frontend.mjs` rebuilds `static/dist/` (hashed bundles).
  Never hand-edit `static/dist/`; edit `static/js|css` + templates, then rebuild.
- i18n: after touching `_()` strings run `make translations` (extract → update → compile)
  or the `.po`/`.mo` files drift from the templates.
- Full suite takes ~2 min; use `pytest tests/test_x.py -q` for a tight loop.

## Quality gates (current)

| Gate | Threshold | Status |
| ---- | --------- | ------ |
| ruff check + format | clean | enforced in CI |
| mypy `app/` | 0 errors | enforced in CI (T5 #100) |
| pytest `--cov-fail-under` | 70 (local == CI) | ~83% actual |
| ESLint `static/js` | zero-tolerance job | see T6 #101 |

## Hotspots (read before touching)

- `app/services/new_book/` (`sync_engine.py`, `query_service.py`, `ingestor.py`): crawler
  orchestration + batch import. Concurrency (ThreadPoolExecutor) and idempotency
  (`batch_id`) matter; run the new-book tests after any change.
- Translation stack (`zhipu_translation_service.py`, `free_translation_service.py`,
  `book_language_pack.py`, `translation_cache_service.py`): primary/fallback/cache
  layers. `deep-translator` is intentionally NOT installed (security); the code
  degrades gracefully, keep it that way.
- `app/services/award_book_service.py`: N+1-sensitive; `test_n_plus_one_regression.py`
  and `test_save_book_metadata_batch_uses_single_select` lock the query counts.
- `app/models/schemas.py` + `new_book.py`: classic `db.Column` declarative style.
  Keep it; do not "modernize" to `Mapped[]` without a tracking issue (spike showed
  150+ constructor false positives, T5 #100).
- `app/routes/admin.py`: admin-only endpoints (`admin_required` + CSRF). CSRF tokens
  are single-use with 1h TTL; residual risk accepted and recorded in `SECURITY.md`.
- Mobile templates (`templates/mobile/`, `static/mobile/js/`): parallel to desktop,
  keep feature parity (search entry, filters, badges).

## Area map

```text
app/routes/          # Flask blueprints (main, new_books, api/* incl. awards, admin, analytics, health, public_api)
app/services/        # business logic; clients (nyt/google_books/open_library/wikidata/zhipu)
app/services/new_book/  # new-books pipeline: sync_engine → ingestor → query_service
app/models/          # SQLAlchemy models (schemas.py, new_book.py, book.py) + db in database.py
app/utils/           # service_helpers (service registry), api_helpers (CSRF/auth), error_handler
app/tasks/           # APScheduler jobs (weekly_report_task); external cron via CRON_SECRET
scripts/             # build_frontend.mjs, sync_wiki.py, init/migrate helpers
tests/               # pytest suite; regression evidence lives next to specs
static/dist/         # BUILD OUTPUT (frontend bundles) — do not hand-edit
templates/ (+mobile/)# Jinja2 desktop + mobile views
docs/agents/         # agent skill wiring (issue tracker, triage labels, domain)
```

Test files mirror the area they cover (`test_<area>.py`); put regression tests for a
bugfix next to the module's existing test file, not in the repo root
(root-level `test_*.py` are local debug scraps, git-ignored — see CONTRIBUTING.md).
