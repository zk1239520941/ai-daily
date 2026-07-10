# AGENTS.md

面向 AI 编码代理的仓库操作说明。项目概览见 [README.md](./README.md)，开发约定见 [CLAUDE.md](./CLAUDE.md)。

## Cursor Cloud specific instructions

本节为在 Cloud Agent 环境（依赖已由启动脚本 `uv sync` 安装完毕）中工作的后续代理提供非显而易见的运行须知。标准命令见 [CLAUDE.md](./CLAUDE.md) 与 [README.md](./README.md) 的「本地调试命令」。

### 服务与运行形态

- 本项目**没有常驻服务/数据库**。所谓「服务」即一次性 CLI 调用（`uv run python -m src.main <子命令>`）加外部网络 API。
- 生产环境由 GitHub Actions 调度，本地/Cloud 仅用于调试与验证。

### 本地配置（每次新环境需自行准备，均被 .gitignore 忽略）

- `load_config()` 硬编码读取 `config.json`（缺失即 `FileNotFoundError`）。新环境需 `cp config.user.json.example config.json`。
- 密钥只从环境变量读取，不写入 JSON。`cp .env.example .env` 后填入真实值；`config.json` 里的 `apiKeyName`/`tokenName` 只是**指向**环境变量名。

### 密钥要求（决定哪些流程可跑）

- **LLM 相关流程**（`check` / `fetch` / `push` / `daily` / `loop` / `rss` / `github` / `hackernews`）**必须**有真实 `LLM_API_KEY`（兼容旧名 `DEEPSEEK_API_KEY`）。`.env.example` 内为占位 key，`check` 会以 401 认证失败。
- 无密钥时可跑：`uv run pytest tests/pytest/`（全程 mock，无需任何 key）与 **Pages 静态站点构建**（见下）。
- 企微推送需 `WECOM_WEBHOOK_URL`；`push --dry-run` / `--defer-wecom` 可跳过真实发送。
- **危险坑**：`fetch` **没有** dry-run,且热点分 ≥ `filter.hot_threshold`（默认 90）会**真往企微群即时推送**。在已配置 `WECOM_WEBHOOK_URL` 的环境里想验证 LLM 流水线又不打扰群,**不要跑 `fetch`**;改用 `uv run python -m src.main push --dry-run --defer-wecom --force`——它只调 LLM 从当日已抓取数据生成 digest,`--dry-run` 全局禁用 webhook 发送、也不 git push,`--force` 忽略当日已存在的 digest 以强制重新生成。

### Pages 静态站点（无需任何密钥即可端到端验证核心功能）

- 构建：`uv run python scripts/build_pages_index.py`（从 `news-data/push-*.md` 生成 `index.html`、`archive/`、`search.html` 与各期 `push-*.html`）。
- **注意**：本地构建会依据当前 `news-data/` **重新生成并裁剪** `archive/*.html`、`search.html` 等已提交产物，产生 git diff。这些是构建输出，CI 会重新生成，**本地运行产生的这类改动不要提交**。
- 本地预览：将 `index.html`/`search.html`/`news-data`/`archive`/`static` 组装到一个目录后 `python3 -m http.server`（参考 `.github/workflows/pages.yml` 的 `_site` 组装步骤）。

### 测试注意

- `tests/pytest/` 为自包含单元测试。`tests/` 根目录下的 `*.py` 是会打真实 API 的手动/集成脚本，勿在无密钥环境当作单测跑。
- 已知与日期/数据相关的 flaky：`test_storage.py::TestLoadExistingLinks` 的 3 个用例假设「昨天」的 `news-data/fetch-<昨天>.json` 不存在；当仓库已提交对应日期数据且系统时间为其次日时会失败，与环境设置无关。
