# 贡献指南

感谢你对 BookRank 的关注！本文件说明如何参与项目、提交 Issue 与 Pull Request。

## 开发环境

1. 克隆仓库：
   ```bash
   git clone https://github.com/gongyijie85/bookrank.git
   cd bookrank
   ```
2. 创建并激活虚拟环境：
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   # source .venv/bin/activate  # macOS/Linux
   ```
3. 安装依赖：
   ```bash
   pip install -r requirements.txt
   pre-commit install
   ```
4. 复制环境变量并填写：
   ```bash
   cp .env.example .env
   ```
5. 启动开发服务器：
   ```bash
   python run.py
   ```

## 提交规范

使用 conventional commits 格式：

```
<type>(<scope>): <subject>
```

常见类型：`feat`、`fix`、`docs`、`style`、`refactor`、`perf`、`test`、`chore`。

示例：

```
fix(docker): remove obsolete build.py call
feat(github): add issue forms and dependabot config
```

## 代码质量门禁

提交前请确保以下命令通过：

```bash
make check
```

该命令会依次运行：

- `ruff check app/ tests/`
- `ruff format --check app/ tests/`
- `mypy app/`
- `pytest --cov=app --cov-fail-under=70`

## Issue 与 PR 流程

- 发现 bug 请使用 [Bug Report](/.github/ISSUE_TEMPLATE/bug_report.yml) 模板。
- 新功能请使用 [Feature Request](/.github/ISSUE_TEMPLATE/feature_request.yml) 模板。
- 使用问题请到 [Discussions](https://github.com/gongyijie85/bookrank/discussions) 发帖。
- PR 请关联相关 Issue，填写变更摘要与验证步骤。

## 行为准则

参与本项目即表示你同意遵守我们的 [行为准则](./CODE_OF_CONDUCT.md)。
