# Production Deploy Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a successful `main` CI run create and verify the specific Render deployment for the pushed revision instead of silently skipping one when configuration is absent.

**Architecture:** Keep the Render API key as a GitHub Secret and use repository variables for the Render service ID and public service URL. The CI deploy job will fail closed, create a deployment through the Render Public API for `GITHUB_SHA`, poll that deployment to `live`, then poll `/health/ready` with finite retry budgets.

**Tech Stack:** GitHub Actions YAML, bash, curl, Render Public API, Python standard-library JSON parsing, Flask readiness endpoint.

---

### Task 1: Create a traceable Render deployment and verify readiness

**Files:**
- Modify: `.github/workflows/ci.yml:89-105`

- [ ] **Step 1: Verify the existing configuration sources**

Run: `rg -n "RENDER_(DEPLOY_HOOK_URL|BASE_URL)|health/ready" .github/workflows render.yaml`

Expected: the weekly workflow uses `RENDER_BASE_URL`; `render.yaml` uses `/health/ready`; CI configuration names are documented without secret values.

- [ ] **Step 2: Update the deployment step**

Set `RENDER_API_KEY: ${{ secrets.RENDER_API_KEY }}`, `RENDER_SERVICE_ID: ${{ vars.RENDER_SERVICE_ID }}`, and `RENDER_BASE_URL: ${{ vars.RENDER_BASE_URL || 'https://bookrank-ckml.onrender.com' }}` in the step environment. Start with `set -euo pipefail` and fail closed when any variable is absent. Create a deployment for `GITHUB_SHA` through the Render Public API, parse only its deployment ID with Python's standard library, poll that ID until `live` (failing immediately on terminal failure states), then retry `curl --fail --show-error --silent --max-time 30 "$RENDER_BASE_URL/health/ready"` exactly 12 times, sleeping 15 seconds between attempts. Never print an API response or token.

- [ ] **Step 3: Verify the configuration diff**

Run: `rg -n "set -euo pipefail|not configured|RENDER_(API_KEY|SERVICE_ID|BASE_URL)|deploys|health/ready|seq 1 (20|12)|--fail" .github/workflows/ci.yml; git diff --check`

Expected: all controls are present and whitespace validation succeeds.

- [ ] **Step 4: Commit the focused workflow change**

Run: `git add .github/workflows/ci.yml docs/superpowers/plans/2026-08-13-production-deploy-verification.md; git commit -m "ci: verify deployed Render revision"`

### Task 2: Align the rollback runbook

**Files:**
- Modify: `docs/runbooks/deployment-rollback.md:48-57`

- [ ] **Step 1: Confirm the contradiction**

Run: `rg -n "autoDeploy|Auto-Deploy|Deploy Hook|health/ready" docs/runbooks/deployment-rollback.md render.yaml`

Expected: the runbook says `autoDeploy: true` while `render.yaml` actually sets it to `false`.

- [ ] **Step 2: Replace the obsolete instruction**

Document that the service already uses manual/hook deployments (`autoDeploy: false`); during rollback keep automatic deployment disabled and use Render Manual Deploy for a selected commit. State that `RENDER_DEPLOY_HOOK_URL` is a required GitHub Secret and `RENDER_BASE_URL` is the non-secret repository variable for CI readiness verification. Do not put a secret value in the repository.

- [ ] **Step 3: Verify documentation and commit**

Run: `rg -n "autoDeploy: true|autoDeploy: false|RENDER_DEPLOY_HOOK_URL|RENDER_BASE_URL" docs/runbooks/deployment-rollback.md render.yaml; git diff --check; git add docs/runbooks/deployment-rollback.md; git commit -m "docs: align Render rollback runbook"`

Expected: no stale `autoDeploy: true`; documented external configuration names only.

### Task 3: Validate and hand off

**Files:**
- Verify: `.github/workflows/ci.yml`
- Verify: `docs/runbooks/deployment-rollback.md`

- [ ] **Step 1: Run quality gates**

Run: `.\\.venv\\Scripts\\python.exe -m ruff check app tests; .\\.venv\\Scripts\\python.exe -m mypy app; .\\.venv\\Scripts\\python.exe -m pytest tests -q`

Expected: all quality gates pass.

- [ ] **Step 2: Push and open a reviewable PR**

Run: `git push -u origin codex/deployment-p0-auto; gh pr create --base main --head codex/deployment-p0-auto --title "ci: make Render deployment failures visible"`

Expected: a PR whose deployment job intentionally fails until the maintainer adds the missing Hook secret; that failure is the required configuration signal.
