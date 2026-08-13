# Production Deploy Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make only the successful CI run for the current `main` HEAD create and verify the corresponding Render deployment; an older queued CI run exits successfully without deploying.

**Architecture:** Keep the Render API key as a GitHub Secret and use repository variables for the Render service ID and public service URL. After validating configuration, CI reads the current `main` ref through GitHub's API and skips stale commits. It uses one shared two-hour deployment deadline across queued-deployment discovery and deployment-status polling, then checks `/health/ready` 12 times at 15-second intervals. This records implementation intent only; it does not claim an online deployment was verified.

**Tech Stack:** GitHub Actions YAML, bash, curl, Render Public API, Python standard-library JSON parsing, Flask readiness endpoint.

---

### Task 1: Create a traceable Render API deployment and verify readiness

**Files:**
- Modify: `.github/workflows/ci.yml:89-105`

- [ ] **Step 1: Verify the existing configuration sources**

Run: `rg -n "RENDER_(API_KEY|SERVICE_ID|BASE_URL)|health/ready" .github/workflows render.yaml`

Expected: the weekly workflow uses `RENDER_BASE_URL`; `render.yaml` uses `/health/ready`; CI configuration names are documented without secret values.

- [x] **Step 2: Update the deployment step**

Set `GH_TOKEN: ${{ github.token }}`, `RENDER_API_KEY: ${{ secrets.RENDER_API_KEY }}`, `RENDER_SERVICE_ID: ${{ vars.RENDER_SERVICE_ID }}`, and `RENDER_BASE_URL: ${{ vars.RENDER_BASE_URL || 'https://bookrank-ckml.onrender.com' }}` in the step environment. Start with `set -euo pipefail` and fail closed when any Render variable is absent. Before contacting Render, read `main` through `gh api repos/${GITHUB_REPOSITORY}/git/ref/heads/main --jq .object.sha`; if it differs from `GITHUB_SHA`, report a stale deployment skip and exit successfully. Serialize production runs, create a deployment for the current `GITHUB_SHA` through the Render Public API, and use a single `DEPLOY_DEADLINE=$((SECONDS + 7200))` for queued discovery and status polling; retry failed requests after 30 seconds until that shared deadline. Verify every fetched deployment belongs to `GITHUB_SHA`, require a final `live` confirmation, then retry `curl --fail --show-error --silent --max-time 30 "$RENDER_BASE_URL/health/ready"` exactly 12 times, sleeping 15 seconds between attempts. Never print an API response or token. README and the backup/restore and rollback runbooks document this current API-based CI mechanism and the Dashboard emergency route. This is workflow implementation evidence only; no production deployment has been verified here.

- [x] **Step 3: Verify the configuration diff**

Run: `rg -n "set -euo pipefail|not configured|GH_TOKEN|git/ref/heads/main|DEPLOY_DEADLINE|while|RENDER_(API_KEY|SERVICE_ID|BASE_URL)|deploys|health/ready|seq 1 12|--fail" .github/workflows/ci.yml; git diff --check`

Expected: all controls are present and whitespace validation succeeds.

- [ ] **Step 4: Commit the focused workflow and documentation change**

Run: `git add .github/workflows/ci.yml README.md docs/runbooks/database-backup-restore.md docs/runbooks/deployment-rollback.md docs/superpowers/plans/2026-08-13-production-deploy-verification.md; git commit -m "ci: serialize current Render deployment"`

### Task 2: Align the rollback runbook

**Files:**
- Modify: `docs/runbooks/deployment-rollback.md:48-57`

- [x] **Step 1: Confirm the contradiction**

Run: `rg -n "autoDeploy|Auto-Deploy|Render Public API|health/ready" docs/runbooks/deployment-rollback.md render.yaml`

Expected: the runbook says `autoDeploy: true` while `render.yaml` actually sets it to `false`.

- [x] **Step 2: Replace the obsolete instruction**

Document that the service already uses manual deployments (`autoDeploy: false`); during rollback keep automatic deployment disabled and use CI's Render Public API deployment for a pushed rollback commit, or Render Manual Deploy for an emergency selected commit. State that `RENDER_API_KEY` is the required least-privilege GitHub Secret and `RENDER_SERVICE_ID` plus `RENDER_BASE_URL` are non-secret repository variables. Do not put a secret value in the repository.

- [x] **Step 3: Verify documentation and commit**

Run: `rg -n "autoDeploy: true|autoDeploy: false|RENDER_(API_KEY|SERVICE_ID|BASE_URL)" README.md docs/runbooks/database-backup-restore.md docs/runbooks/deployment-rollback.md render.yaml; git diff --check`

Expected: no stale `autoDeploy: true`; documented external configuration names only.

### Task 3: Validate and hand off

**Files:**
- Verify: `.github/workflows/ci.yml`
- Verify: `README.md`, `docs/runbooks/database-backup-restore.md`, and `docs/runbooks/deployment-rollback.md`

- [ ] **Step 1: Run quality gates**

Run: `.\\.venv\\Scripts\\python.exe -m ruff check app tests; .\\.venv\\Scripts\\python.exe -m mypy app; .\\.venv\\Scripts\\python.exe -m pytest tests -q`

Expected: all quality gates pass.

- [ ] **Step 2: Push and open a reviewable PR**

Run: `git push -u origin codex/deployment-p0-auto; gh pr create --base main --head codex/deployment-p0-auto --title "ci: make Render deployment failures visible"`

Expected: a reviewable PR. This plan does not assert that a production deployment has run; maintainers configure the API secret and repository variables outside the repository.
