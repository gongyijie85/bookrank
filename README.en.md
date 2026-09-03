# BookRank

**[English](./README.en.md) | [中文](./README.md)**

[![CI - Tests & Quality](https://github.com/gongyijie85/bookrank/actions/workflows/ci.yml/badge.svg)](https://github.com/gongyijie85/bookrank/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/gongyijie85/bookrank/branch/main/graph/badge.svg)](https://codecov.io/gh/gongyijie85/bookrank)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)
[![Flask 3.1](https://img.shields.io/badge/flask-3.1-black.svg)](https://flask.palletsprojects.com/)
[![License MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![GitHub Release](https://img.shields.io/github/v/release/gongyijie85/bookrank)](https://github.com/gongyijie85/bookrank/releases)
[![Live Demo](https://img.shields.io/badge/demo-online-blue)](https://bookrank-ckml.onrender.com)

A New York Times bestseller ranking application that tracks the latest publications from major international publishers and showcases book awards.

Live demo: [bookrank-ckml.onrender.com](https://bookrank-ckml.onrender.com)

## About

BookRank aggregates quality book information from around the world, providing readers with a one-stop book discovery experience. It combines the New York Times bestseller lists with international literary awards, smart translation, and real-time updates to deliver a comprehensive and convenient book information hub.

## Features

- 📚 **Bestseller lists**: NYT bestsellers across categories, with multi-dimensional sorting and filtering
- 🏆 **Award-winning books**: 7 major international awards (Pulitzer Prize, Booker Prize, International Booker Prize, Hugo Award, Nebula Award, Nobel Prize in Literature, Edgar Award) with detailed winner info
- 🆕 **New releases**: tracks the latest publications from major international publishers, filterable by publisher
- 📊 **Multi-dimensional filtering**: by publisher, category, time, and more
- 🌐 **Desktop + mobile**: the same URL serves dedicated desktop and mobile templates selected by User-Agent. The 8 core mobile pages (home, book detail, awards, award detail, about, error, weekly report list, weekly report detail) are feature-aligned with desktop: tab switching, metadata grids, purchase links, favorites/sharing, 30-second polling, search filters, and SEO metadata (canonical + Open Graph + JSON-LD)
- 🔍 **Smart search**: find books quickly by title, author, and other fields
- 📱 **Optimized detail pages**: unified left-right layout with cover and purchase links on the left, book info on the right
- 🎨 **Consistent card design**: uniform 2/3 cover aspect ratio across all book cards
- 🌍 **Smart translation**: Chinese translations for titles and descriptions to lower the language barrier
- 🚀 **Real-time updates**: automatic list synchronization plus a weekly-report self-healing mechanism (triple redundancy) so runs are never missed
- 🔓 **Open API**: public API for third-party integrations

### Ranking data semantics

- **This week** and **Last week** ranks come directly from the New York Times lists; filtering and sorting never change the source rank.
- **Weeks on list** preserves the cumulative value supplied by NYT; `0` means the source did not provide it.
- **NEW** means a true debut (no prior rank and one cumulative week); **RETURN** means a re-entry after appearing before (no prior rank and more than one cumulative week).

## Tech Stack

- **Backend**: Flask 3.1.3 (Python 3.13+)
- **Database**: Flask-SQLAlchemy 2.0 (PostgreSQL / SQLite)
- **Frontend**: Jinja2 + vanilla JS (ES2020+)
- **Deployment**: Render + Gunicorn 23.0
- **API integrations**: NYT Books API, Google Books API, Open Library API, Wikidata SPARQL
- **Translation**: SiliconFlow Hunyuan-MT-7B (production default, OpenAI-compatible endpoint), Zhipu GLM (fallback, default in tests)
  - The previous Google Translate fallback (`deep-translator`) was **removed**: its PyPI account was taken over via a phishing attack and later releases ran malware at install time (PYSEC-2022-252). See [`SECURITY.md`](./SECURITY.md)
- **Rate limiting**: in-process sliding window (default); optional **Redis shared backend** for multi-worker deployments (see [`SECURITY.md`](./SECURITY.md))
- **Code quality**: Ruff (lint + format), mypy (type checks), Pydantic (validation), pytest-cov
- **Scheduling**: APScheduler (in-memory queue)

## Quick Start

### Prerequisites

- Python 3.13 or newer
- pip

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/gongyijie85/bookrank.git
   cd bookrank
   ```

2. **Create a virtual environment**
   ```bash
   # Windows
   python -m venv .venv
   .venv\Scripts\activate

   # macOS/Linux
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   Copy `.env.example` to `.env` and fill in the values:
   ```
   SECRET_KEY=your-secret-key
   ADMIN_SECRET=your-admin-secret          # required (v0.9.61+, shared by all admin endpoints)
   NYT_API_KEY=your-nyt-api-key
   GOOGLE_API_KEY=your-google-api-key
   ZHIPU_API_KEY=your-zhipu-api-key
   DATABASE_URL=your-database-url

   # v0.9.79+ (optional but strongly recommended in production)
   SENTRY_DSN=https://xxx@yyy.ingest.sentry.io/zzz
   ALERT_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
   CORS_ORIGINS=https://yourdomain.com
   API_RATE_LIMIT_WINDOW=60
   IMAGE_TIMEOUT=10
   NYT_RANKING_SYNC_DAYS=7
   SQLALCHEMY_ECHO=false
   ```
   > **v0.9.61 breaking change**: the `ADMIN_TOKEN` env var is deprecated; use `ADMIN_SECRET` (aligned with the other 27 admin endpoints). See [CHANGELOG.md](./CHANGELOG.md).
   >
   > **v0.9.79 note**: `.env.example` contains the full variable reference — just copy it for first-time setup.

5. **Initialize the database (optional)**
   ```bash
   python init_db.py
   ```
   `run.py` also performs lazy database initialization on first start, so this step can be skipped.

6. **Start the dev server**
   ```bash
   python run.py
   ```

   The app runs at `http://localhost:8000` (override with the `PORT` environment variable).

## Project Structure

```
bookrank/
├── app/                          # application core
│   ├── __init__.py               # app factory
│   ├── config.py                 # configuration
│   ├── setup.py                  # service init + background tasks
│   ├── data/                     # static data (publishers, etc.)
│   ├── initialization/           # seed data
│   │   ├── awards.py             # award definitions
│   │   └── sample_books.py       # sample books
│   ├── models/                   # data model layer
│   │   ├── database.py           # database connection
│   │   ├── schemas.py            # SQLAlchemy models
│   │   ├── book.py               # Book dataclass
│   │   └── new_book.py           # NewBook model
│   ├── routes/                   # route layer
│   │   ├── main.py               # page routes
│   │   ├── admin.py              # admin API
│   │   ├── new_books.py          # new releases API
│   │   ├── health.py             # health checks
│   │   ├── public_api.py         # public API
│   │   ├── analytics_bp.py       # analytics
│   │   └── api/                  # internal API submodules
│   │       ├── books.py          # books API
│   │       ├── translation.py    # translation API
│   │       ├── cache.py          # cache management API
│   │       ├── awards.py         # awards API
│   │       ├── recommendations.py # recommendations API
│   │       └── cron.py           # cron trigger endpoints
│   ├── schemas/                  # Pydantic validation layer
│   │   └── validators.py         # request validators
│   ├── services/                 # business services
│   │   ├── api_client.py         # NYT/Google API clients
│   │   ├── book_service.py       # book service
│   │   ├── new_book/             # new releases submodule (__init__ is the assembly factory)
│   │   │   ├── publisher_manager.py  # publisher management
│   │   │   ├── sync_engine.py        # sync engine
│   │   │   ├── ingestor.py           # ingest rules (deep module)
│   │   │   ├── translation_pipeline.py # translation pipeline
│   │   │   └── query_service.py      # query service
│   │   ├── book_detail_service.py # book detail service
│   │   ├── cache_service.py      # cache service
│   │   ├── translation_cache_service.py # translation cache
│   │   ├── zhipu_translation_service.py # Zhipu AI translation
│   │   ├── weekly_report_service.py # weekly report service
│   │   ├── publisher_crawler/    # publisher crawlers
│   │   ├── award_cover_sync_service.py # award cover sync
│   │   └── ...
│   ├── tasks/                    # background tasks
│   │   └── weekly_report_task.py # weekly report task
│   └── utils/                    # utilities
│       ├── exceptions.py         # custom exceptions
│       ├── rate_limiter.py       # rate limiter
│       ├── error_handler.py      # error classification
│       ├── error_tracker.py      # in-memory error tracker
│       ├── service_helpers.py    # service registry
│       ├── book_filters.py       # book filtering/sorting
│       ├── date_helpers.py       # date helpers
│       └── security.py           # security helpers
├── static/                       # static assets
│   ├── css/                      # stylesheets
│   ├── js/                       # JavaScript
│   ├── data/                     # data files
│   └── fonts/                    # fonts
├── templates/                    # Jinja2 templates
│   ├── base.html                 # base template
│   ├── _macros.html              # Jinja2 macros
│   ├── index.html                # home (bestsellers)
│   ├── awards.html               # awards
│   ├── new_books.html            # new releases
│   ├── publishers.html           # publisher navigation
│   └── *detail.html              # detail pages
├── tests/                        # tests
├── scripts/                      # ops scripts
├── migrations/                   # database migrations
├── requirements.txt              # full dependencies (incl. dev tools)
├── requirements-prod.txt         # production-only dependencies
├── run.py                        # Render startup entry
└── Procfile                      # Render deployment config
```

## Documentation & Knowledge Base

Technical documentation is maintained in two forms:

- **`CODE_WIKI.md`**: the complete technical reference as a single file (best for browsing and searching online)
- **`Code Wiki/` directory** (v0.9.80+): the same knowledge base split into an Obsidian vault, organized by chapter
  - 18 chapter notes + 1 index page, with wikilink bidirectional navigation
  - Great for local reading, note-taking, and linking in Obsidian
  - Location: `BookRank3/Code Wiki/`

## API Rate Limits

- **NYT Books API**: 500 requests/day
- **Google Books API**: 1,000 requests/day
- **Zhipu AI API**: depends on your plan

## Deployment

### Render (recommended)

1. Create a new Web Service on Render and connect the GitHub repository.
2. Use the `render.yaml` Blueprint at the repo root, or configure manually:
   - Name: bookrank
   - Region: Oregon / Singapore (choose based on network conditions)
   - Branch: main
   - Build Command: `pip install -r requirements-prod.txt`
   - Start Command: `gunicorn -c gunicorn.conf.py run:application`
   - Health Check Path: `/health/ready`
3. Add environment variables in the Render Dashboard (see `.env.example`):
   - `SECRET_KEY`, `ADMIN_SECRET`, `CRON_SECRET`
   - `DATABASE_URL` (external PostgreSQL, e.g. Supabase Session Pooler)
   - `NYT_API_KEY`, `GOOGLE_API_KEY`, `ZHIPU_API_KEY`
   - `SENTRY_DSN`, `ALERT_WEBHOOK_URL` (recommended for production)
4. **Auto-deploy is disabled**: `render.yaml` sets `autoDeploy: false`. Production deploys are triggered via the Render Public API only by successful CI runs on the current HEAD of `main`; older CI runs skip cleanly so they never overwrite newer commits.
5. Configure the least-privilege secret `RENDER_API_KEY` plus the non-secret repository variables `RENDER_SERVICE_ID` and `RENDER_BASE_URL` on GitHub. CI uses these to call the Render Public API; never commit secrets. In an emergency, use Manual Deploy in the Render Dashboard.
6. The Render free tier is limited to 512 MB; `WEB_CONCURRENCY=1` / `MAX_WORKERS=1` are enforced to avoid OOM with multiple workers.
   > **To raise `WEB_CONCURRENCY`**: you must first set `RATE_LIMIT_REDIS_URL` to enable shared rate limiting —
   > otherwise each worker counts independently, multiplying the effective limit and allowing bypass
   > (see [`SECURITY.md`](./SECURITY.md)).
7. Wait for the build to finish and grab the access URL.

> **Note**: Render's free PostgreSQL service is no longer offered — use an external PostgreSQL (e.g. Supabase). Migration guide: [`docs/supabase-migration.md`](./docs/supabase-migration.md).

### Docker (optional)

```bash
# Build the image
docker build -t bookrank .

# Run the container
docker run -p 5000:5000 --env-file .env bookrank
```

## Security

- Security policy, vulnerability reporting and the **known-risk register**: [`SECURITY.md`](./SECURITY.md)
  (GitHub Private Vulnerability Reporting is enabled).

  | Area | Measure |
  |---|---|
  | CSRF | Admin mutation endpoints enforce `@csrf_protect`; tokens are **single-use** (deleted after validation) |
  | XSS | Output sanitized with bleach allow-lists; CSP uses a **per-request nonce** (no `unsafe-inline`), locked by tests |
  | Rate limiting | Per-IP sliding window; optional **Redis shared backend** for multi-worker |
  | Admin auth | `X-Admin-Secret` + failure counting + IP blocking; failure state **persists across restarts** |
  | Secret leakage | Logs and exceptions never expose secret names or storage locations |
  | Supply chain | `pip-audit` gate in CI; the compromised `deep-translator` package removed |

- ⚠️ Keep `WEB_CONCURRENCY=1` **unless** you set `RATE_LIMIT_REDIS_URL` to enable shared rate limiting
  (in-process counters are per-worker, so the effective limit is multiplied). See [`SECURITY.md`](./SECURITY.md).

## Development Guide

### Code style

- **Python**: PEP 8 with type annotations
- **JavaScript**: modern syntax (ES2020+), using `??` and `?.`
- **CSS**: CSS variables, responsive design
- **Git commits**: Conventional Commits

### Testing

- Test directory: `tests/`
- Config file: `pytest.ini`
- Run: `pytest -m "not slow" --timeout=30`
- Current scale: **2237 passed / 0 failed**

**Merge gate**: `main` has branch protection enabled — all 4 checks below must pass:

| Check | Description |
|---|---|
| `Unit Tests` | pytest suite |
| `Type Check (mypy)` | `mypy app/ --ignore-missing-imports` |
| `Code Quality (Ruff)` | `ruff check` + `ruff format --check` |
| `Dependency Vulnerability Audit` | `pip-audit` scan (exception-register gate, see below) |

> The dependency scan uses an **exception register**: advisory IDs that have been reviewed are allow-listed
> (still printed as `N ignored`, never silently swallowed); **any unregistered vulnerability blocks the merge**.
> Rationale and maintenance rules live in [`SECURITY.md`](./SECURITY.md).

### Data updates

- Automatic: periodic updates via GitHub Actions
- Manual: `python update_books.py`

## Public API

Full API docs: [`API_DOCUMENTATION.md`](./API_DOCUMENTATION.md).

### API endpoint layout

```
/api/public
├── /                         # API info
├── /bestsellers              # all bestseller categories
├── /bestsellers/{category}   # bestsellers by category
├── /bestsellers/search       # search bestsellers
├── /awards                   # all awards
├── /awards/{award_name}      # award winners by award
├── /awards/{award_name}/{year} # award winners by award and year
├── /book/{isbn}              # book details
├── /new-books                # new releases (paginated)
├── /new-books/{publisher}    # new releases by publisher
└── /recommendations          # recommendations
```

### User API

```
/api
├── /favorites                # list favorites (GET)
├── /favorites                # add favorite (POST)
├── /favorites/{isbn}         # remove favorite (DELETE)
└── /favorites/check/{isbn}   # check favorite status (GET)
```

## Recent Updates

- **v0.9.101 - Security & CI hardening (2026-09-03)**:
  - **Rate limiter now supports a Redis shared backend** (root-cause fix for audit High #2): counters were per-process,
    so the effective limit was multiplied across workers; set `RATE_LIMIT_REDIS_URL` to enable cross-worker counting
    (Redis ZSET sliding window + **atomic Lua**). Default behavior is unchanged; failures degrade gracefully
  - **Fixed mobile CSRF token reuse**: tokens are single-use but the mobile client cached one forever, so deleting
    favorites worked once and then failed with 403. Added `csrfFetch()` (clears cache after use, retries on invalidation)
  - **Fixed admin lockout bypass**: failure counters were only persisted on the 5th attempt, so a restart/redeploy
    reset them and the threshold could never be reached. Every failure is now persisted (24h retention window)
  - **Removed the compromised `deep-translator` dependency** (PYSEC-2022-252 supply-chain attack), see `SECURITY.md`
  - Logs/exceptions no longer leak secret names or storage locations; `mistune` upgrade cleared
    **2 GitHub HIGH advisories** (Dependabot open alerts now zero)
  - CI gained a **dependency vulnerability gate** (`pip-audit`, exception-register) as a required status check
  - Quality: ruff / mypy (99 files) pass, **2237 passed / 0 failed**. See [CHANGELOG.md](./CHANGELOG.md)
- v0.9.100 - Fix batch import digest mismatch causing permanent 409 (2026-08-31). See [CHANGELOG.md](./CHANGELOG.md)
- v0.9.99 - Low-priority review cleanups (2026-08-19): cooldown race / cover selection & commit / ops scripts. See [CHANGELOG.md](./CHANGELOG.md)
- v0.9.98 - Source-downgrade alerts dispatched in background (2026-08-19): imports no longer wait on the GitHub API. See [CHANGELOG.md](./CHANGELOG.md)
- v0.9.97 - Batch preloaded index for ingest dedup (2026-08-19): removes the ingestor N+1 query. See [CHANGELOG.md](./CHANGELOG.md)
- v0.9.96 - Sync endpoint moved to a background task (2026-08-19): removes up to 600s/Publisher request-thread blocking. See [CHANGELOG.md](./CHANGELOG.md)
- v0.9.95 - Cover batch sync as background task + module-level lock fix (2026-08-19). See [CHANGELOG.md](./CHANGELOG.md)
- v0.9.94 - Extracted shared translation-override helper (2026-08-19): removes model-layer duplication and back-references. See [CHANGELOG.md](./CHANGELOG.md)
- v0.9.93 - Wired the `fallback_google_enabled` flag (2026-08-19): #137 spec gap. See [CHANGELOG.md](./CHANGELOG.md)
- v0.9.92 - Removed direct interpolation of secrets/inputs in GitHub Actions scripts (2026-08-19). See [CHANGELOG.md](./CHANGELOG.md)
- v0.9.91 - Perf & cover sync fixes (2026-08-19): removed O(N×M) full-table scans in batch import; fixed cover sync not detecting "cache file missing". See [CHANGELOG.md](./CHANGELOG.md)
- v0.9.90 - Fix production cover sync (2026-08-14): detect the "path in DB but local cache file missing" case and re-download; two regression tests added. See [CHANGELOG.md](./CHANGELOG.md)
- v0.9.89 - Award cover fallback + 2026 winners (2026-08-14): multi-level cover fallback (local cache → original URL → default cover); synced 2020-2026 winners (4 Pulitzer titles, International Booker: *Taiwan Travelogue*, Edgar: *The Big Empty*). See [CHANGELOG.md](./CHANGELOG.md)
- v0.9.88 - Extract the NewBookIngestor deep module (2026-08-14): ingest rules consolidated behind two stable interfaces (`save_book` / `update_book_fields`), SyncEngine slimmed down; TranslationPipeline gains public seams; 2381 passed. See [CHANGELOG.md](./CHANGELOG.md)
- v0.9.87 - Dependency security fixes (2026-07-16): fixed 36 vulnerabilities reported by GitHub Dependabot; upgraded Werkzeug, Flask-CORS, requests, python-dotenv, Pillow, bleach, mistune; 2130 passed, 81.55% coverage. See [CHANGELOG.md](./CHANGELOG.md)
- v0.9.86 - Cron endpoint standardization (2026-07-16): migrated to `app/routes/api/` with unified `@handle_api_errors` handling; `trigger-weekly-report.yml` uses `RENDER_BASE_URL` with Fri/Sat/Sun fallback triggers. See [CHANGELOG.md](./CHANGELOG.md)
- v0.9.85 - v0.9.84 wrap-up and repo housekeeping (2026-07-16): confirmed GitHub Private Vulnerability Reporting enabled; ignored `.gh-cache/`; committed agent docs; archived v0.9.83 audit deliverables. See [CHANGELOG.md](./CHANGELOG.md)
- v0.9.84 - OSS community maturity (2026-07-13): added MIT `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `ROADMAP.md`; Issue Forms, PR templates, Dependabot and CodeQL config; fixed `Dockerfile` and added `compose.yaml`; fixed Issue #8. See [CHANGELOG.md](./CHANGELOG.md)

> Older releases: see [CHANGELOG.md](./CHANGELOG.md) and [VERSION.md](./VERSION.md).

## Roadmap

See [ROADMAP.md](./ROADMAP.md) for the full roadmap. Current focus:

### v1.0 (in progress)
- Machine-readable OpenAPI spec and docs (`/openapi.json`)
- Publisher crawler selector drift monitoring and alerts
- mypy override debt cleanup (remove `disable_error_code`)
- Raise test coverage of low-coverage modules (overall ≥80%)
- N+1 query regression protection
- Translation quality evaluation and sampling (monthly manual samples)
- Code Wiki ↔ GitHub Wiki sync mechanism
- Render resource threshold alerts (memory / response time)

### Long term
- Keep dependency security and performance in good shape
- Adjust feature priorities based on community feedback
- Keep quality gates green (Ruff / mypy / pytest-cov)

## License

MIT License

## Contributing

Issues and pull requests are welcome!

- Please read [CONTRIBUTING.md](./CONTRIBUTING.md) and [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md) before contributing
- Report security issues as described in [SECURITY.md](./SECURITY.md)
- Issue label convention: type (`bug` / `enhancement` / `documentation`) + priority (`p0`–`p3`) + module (`awards` / `new-books` / `mobile`, etc.); full vocabulary in [docs/agents/triage-labels.md](./docs/agents/triage-labels.md)

## Contact

For questions or suggestions, reach us via [GitHub Issues](https://github.com/gongyijie85/bookrank/issues).

## Links

- **Production**: https://bookrank-ckml.onrender.com
- **Repository**: https://github.com/gongyijie85/bookrank
- **API docs**: [API_DOCUMENTATION.md](./API_DOCUMENTATION.md)
- **Project overview (Chinese)**: [docs/项目说明文档.md](./docs/项目说明文档.md)
- **Roadmap**: [ROADMAP.md](./ROADMAP.md)
- **Contributing guide**: [CONTRIBUTING.md](./CONTRIBUTING.md)
- **Security policy**: [SECURITY.md](./SECURITY.md)
