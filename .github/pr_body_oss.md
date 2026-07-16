Fixes #8

## 变更摘要

本次 PR 补齐 BookRank 作为开源项目的社区标准文件、仓库展示、Docker 一键运行能力，并修复 Issue #8 的根因。

### 社区标准文件
- 新增 MIT `LICENSE`，版权人 `gongyijie85`。
- 新增 `CONTRIBUTING.md`：开发环境、提交规范、代码质量门禁、Issue/PR 流程。
- 新增 `SECURITY.md`：支持版本、GitHub Private Vulnerability Reporting 报告方式、安全联系邮箱。
- 新增 `CODE_OF_CONDUCT.md`：Contributor Covenant 2.1 中文版，举报邮箱 `gongyijie@gmail.com`。
- 新增 `ROADMAP.md`：明确 v0.9.84 社区基础目标与 v1.0 技术债务目标。

### GitHub 社区配置
- 新增 Bug / Feature Issue Forms 与 PR 模板。
- 新增 `.github/ISSUE_TEMPLATE/config.yml`，将 Question 引导至 Discussions。
- 新增 `.github/dependabot.yml`，每周检查 pip 与 GitHub Actions 依赖更新。
- 仓库 Settings 中启用 CodeQL 默认配置与 Dependabot Security Updates（PR 合并后人工确认）。

### Docker 一键运行
- 修复 `Dockerfile`：删除已失效的 `RUN python build.py`。
- 新增 `compose.yaml`：单服务、SQLite 持久卷、端口 8000，支持 `docker compose up` 一键启动。

### Issue #8 修复
- 更新 `.github/workflows/update-books.yml` 的 `check-nyt-frequencies` job：先安装完整 `requirements.txt` 再执行频率检查脚本。
- 保留三种退出语义：
  - `0`：频率一致，关闭漂移 issue。
  - `1`：频率漂移，创建/更新 issue 并添加标签 `needs-triage`、`data-drift`。
  - `2`：运行错误，创建/更新 issue 并添加标签 `needs-triage`、`operational-error`。

### README / CHANGELOG / VERSION
- 修正 README CI badge 路径为 `ci.yml`，新增 v0.9.84 最近更新条目。
- 更新 `CHANGELOG.md` 与 `VERSION.md` 到 v0.9.84。

## 验证步骤

- [x] `ruff check app/ tests/` 通过
- [x] `ruff format --check app/ tests/` 通过
- [x] `mypy app/` 通过（90 source files 无类型问题）
- [x] `pytest tests/test_nyt_frequency_check.py -q --no-cov`：8 passed
- [x] `pytest --cov=app`：2125 passed，覆盖率 81.34%
- [x] `docker compose config` 输出合法配置

## 检查清单

- [x] 只修改了与本次 PR 直接相关的文件
- [x] 新增/修改的代码包含必要的注释或文档
- [x] 没有引入未使用的依赖或死代码
- [x] PR 描述包含 `Fixes #8`
