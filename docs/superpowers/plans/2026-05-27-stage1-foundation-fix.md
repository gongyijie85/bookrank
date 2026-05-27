# 阶段1：地基修复（v0.9.28）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一 Python 版本配置、修复 CI lint 门禁、切换生产依赖，确保部署和构建稳定。

**Architecture:** 纯配置文件修改，不涉及 Python 业务代码。4个文件各改1-2处，每个改动独立可验证。

**Tech Stack:** YAML (GitHub Actions, Render), Python build script

---

## 验证发现（修正设计文档）

经过代码探索，原设计文档中2项任务确认无需操作：

- **`css/all.min.css` 404**：`base.html:40-46` 有条件逻辑 `if config.get('ENV') == 'production' and config.get('MINIFIED_CSS_EXISTS')`，仅生产环境加载。`app/__init__.py:44` 根据文件存在性设置标志。`build.py` 在部署时生成。`test_routes.py:59` 已验证回退行为。**无需修复。**
- **模板继承**：所有12个内容模板均已继承 `base.html`（`_macros.html` 是工具宏文件，无需继承）。**无需修复。**

---

## 文件变更清单

| 文件 | 操作 | 变更内容 |
|------|------|----------|
| `render.yaml:27` | 修改 | `PYTHON_VERSION: 3.11.0` → `3.13.0` |
| `render.yaml:15` | 修改 | `pip install -r requirements.txt` → `pip install -r requirements-prod.txt` |
| `.github/workflows/test.yml:35` | 修改 | `python-version: '3.11'` → `'3.13'` |
| `.github/workflows/test.yml:53` | 修改 | 移除 `--exit-zero` |
| `.github/workflows/update-books.yml:29` | 修改 | `python-version: '3.10'` → `'3.13'` |

---

## Task 1: 统一 render.yaml Python 版本和生产依赖

**Files:**
- Modify: `render.yaml:15,27`

- [ ] **Step 1: 修改 render.yaml 第27行 Python 版本**

将 `PYTHON_VERSION` 从 `3.11.0` 改为 `3.13.0`：

```yaml
# render.yaml 第26-27行
      - key: PYTHON_VERSION
        value: 3.13.0
```

- [ ] **Step 2: 修改 render.yaml 第15行构建命令**

将 `requirements.txt` 改为 `requirements-prod.txt`，减少生产环境不必要的开发工具安装：

```yaml
# render.yaml 第15行
    buildCommand: pip install -r requirements-prod.txt && python build.py
```

- [ ] **Step 3: 验证 YAML 语法**

Run: `python -c "import yaml; yaml.safe_load(open('render.yaml'))"`
Expected: 无报错，YAML 语法正确

- [ ] **Step 4: Commit**

```bash
git add render.yaml
git commit -chore(deploy): unify Python 3.13 and use prod requirements in render.yaml
```

---

## Task 2: 统一 test.yml Python 版本并修复 lint 门禁

**Files:**
- Modify: `.github/workflows/test.yml:35,53`

- [ ] **Step 1: 修改 test.yml 第35行 Python 版本**

将 `python-version` 从 `3.11` 改为 `3.13`，与 ci.yml 保持一致：

```yaml
# test.yml 第34-35行
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.13'
```

- [ ] **Step 2: 修改 test.yml 第53行移除 --exit-zero**

将 `ruff check app/ --select=E,F --exit-zero` 改为 `ruff check app/`，让 lint 错误阻断 CI 构建。同时移除 `--select=E,F` 以使用 pyproject.toml 中的完整规则配置：

```yaml
# test.yml 第52-53行
      - name: Lint check
        run: |
          pip install ruff
          ruff check app/
```

- [ ] **Step 3: 验证 YAML 语法**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/test.yml'))"`
Expected: 无报错

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/test.yml
git commit -m "chore(ci): unify Python 3.13 and enforce lint in test.yml"
```

---

## Task 3: 统一 update-books.yml Python 版本

**Files:**
- Modify: `.github/workflows/update-books.yml:29`

- [ ] **Step 1: 修改 update-books.yml 第29行 Python 版本**

将 `python-version` 从 `3.10` 改为 `3.13`：

```yaml
# update-books.yml 第28-29行
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.13'
```

- [ ] **Step 2: 验证 YAML 语法**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/update-books.yml'))"`
Expected: 无报错

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/update-books.yml
git commit -m "chore(ci): unify Python 3.13 in update-books workflow"
```

---

## Task 4: 更新版本信息和变更日志

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `VERSION.md`

- [ ] **Step 1: 在 CHANGELOG.md 顶部添加 v0.9.28 条目**

在 `## v0.9.27` 之前插入：

```markdown
## v0.9.28 - 2026-05-27

### chore: 地基修复 — 统一 Python 版本与 CI 门禁

**render.yaml**：
- `PYTHON_VERSION` 3.11.0 → 3.13.0
- 构建命令改用 `requirements-prod.txt`（减少生产环境内存占用）

**CI 工作流统一**：
- `test.yml`：Python 3.11 → 3.13；移除 `--exit-zero`，lint 错误阻断构建
- `update-books.yml`：Python 3.10 → 3.13
- `ci.yml`：已为 3.13，无需修改

**验证**：ruff 0 错误 | mypy 0 错误 | pytest 953 passed
```

- [ ] **Step 2: 更新 VERSION.md**

将当前版本更新为 v0.9.28，添加版本记录：

```markdown
# BookRank 版本信息

**当前版本**：v0.9.28
**发布日期**：2026-05-27
**Python 版本**：3.13
**Flask 版本**：3.1.3

## 版本亮点

### v0.9.28 (2026-05-27) — 地基修复
- **render.yaml**：Python 3.11→3.13，构建改用 requirements-prod.txt
- **CI 统一**：test.yml Python 3.11→3.13 + 移除 --exit-zero；update-books.yml Python 3.10→3.13
- **Ruff**: 0 错误 | **mypy**: 0 错误 | **pytest**: 953 passed

### v0.9.27 (2026-05-27) — 服务注入标准化
（保留现有内容...）
```

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md VERSION.md
git commit -m "docs: update CHANGELOG and VERSION to v0.9.28"
```

---

## Task 5: 本地验证与推送

- [ ] **Step 1: 运行 Ruff 检查**

Run: `.venv_dbg\Scripts\python.exe -m ruff check app/ tests/`
Expected: All checks passed

- [ ] **Step 2: 运行 mypy 类型检查**

Run: `.venv_dbg\Scripts\python.exe -m mypy app/ --ignore-missing-imports`
Expected: Success: no issues found

- [ ] **Step 3: 运行全量测试**

Run: `.venv_dbg\Scripts\python.exe -m pytest tests/ --timeout=30 -x -q`
Expected: 953 passed

- [ ] **Step 4: 推送到 GitHub**

Run:
```powershell
$env:PATH = "D:\Program Files\Git\cmd;$env:PATH"
git push origin main
```

Expected: Push successful

---

## 验收标准

- [ ] `render.yaml` 中 Python 版本为 3.13.0
- [ ] `render.yaml` 构建命令使用 `requirements-prod.txt`
- [ ] 所有3个 CI 工作流 Python 版本统一为 3.13
- [ ] `test.yml` lint 检查无 `--exit-zero`
- [ ] CHANGELOG.md 和 VERSION.md 已更新至 v0.9.28
- [ ] ruff 0 错误 | mypy 0 错误 | pytest 953 passed
- [ ] 已推送到 GitHub
