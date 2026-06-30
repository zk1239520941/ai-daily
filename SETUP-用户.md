# AI Daily 上线前准备清单

本目录为 [YeeKal/ai-daily](https://github.com/YeeKal/ai-daily) 的独立部署副本，与同级目录 `ai-digest` **并行存在、互不影响**。

按下列顺序完成配置，即可在本地验证后推送到 GitHub，由 Actions 定时抓取、推送，并通过 GitHub Pages 托管日报全文。

---

## 与 ai-digest 的关系

| 项目 | 路径 | 定位 |
|------|------|------|
| **ai-digest** | `../ai-digest` | 自研轻量漏斗：YAML 配置、单次日报、结构简单 |
| **ai-daily**（本项目） | `./` | 上游成熟方案：400+ RSS、即时热点推送、GitHub/HN 早报段、跨板块洞察 |

**建议**：日常推送以 **ai-daily** 为主；`ai-digest` 保留作对照或备用，无需改动。

---

## A. 本地密钥（`.env`）

### A1. 安装依赖

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)（推荐）

```powershell
cd D:\Code\技术委员会\ai-daily
uv sync
```

### A2. 复制配置模板

```powershell
copy .env.example .env
copy config.user.json.example config.json
```

### A3. 填写 `.env`

编辑 `.env`（**切勿提交到 Git**，已在 `.gitignore` 中忽略）：

| 变量 | 必填 | 说明 |
|------|------|------|
| `DEEPSEEK_API_KEY` | ✅ | DeepSeek API Key，用于 RSS 评分、日报生成、洞察等 LLM 调用 |
| `WECOM_WEBHOOK_URL` | ✅ | 企业微信群机器人 Webhook，用于即时热点与早晚报推送 |
| `GITHUB_TOKEN` | 可选 | GitHub Personal Access Token，提高 GitHub Trending 板块 API 限额（匿名仅 60 次/小时） |
| `JINA_API_KEY` | 可选 | Jina Reader API Key，用于 Hacker News 外链正文抓取 |
| `PAGES_BASE_URL` | 可选 | GitHub Pages 站点根 URL，用于企微早晚报中的「完整版」链接 |

#### `DEEPSEEK_API_KEY`

1. 登录 [DeepSeek 开放平台](https://platform.deepseek.com/)
2. 创建 API Key，写入 `.env`
3. `config.json` 中 `llm.baseUrl` 应为 `https://api.deepseek.com/v1`，`llm.model` 推荐 `deepseek-chat`

#### `WECOM_WEBHOOK_URL`

1. 企业微信群 → 群设置 → 群机器人 → 添加
2. 复制 Webhook 地址，形如：`https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...`
3. 写入 `.env` 的 `WECOM_WEBHOOK_URL`

#### `GITHUB_TOKEN`（免费创建）

1. 登录 GitHub → 右上角头像 → **Settings**
2. 左侧最底部 **Developer settings** → **Personal access tokens** → **Tokens (classic)** 或 **Fine-grained tokens**
3. 点击 **Generate new token**
4. 权限勾选：
   - **Classic token**：勾选 `public_repo`（公开仓库）或 `repo`（私有仓库）；若仅读公开 API，勾选 `read:packages` 以外的只读 repo 权限即可
   - **Fine-grained token**：Repository access 选目标仓库，Permissions → Repository → Contents: Read-only
5. 生成后复制 token（形如 `ghp_...` 或 `github_pat_...`），写入 `.env` 的 `GITHUB_TOKEN`

**用途**：早报中的 GitHub Trending 板块需调用 GitHub REST API 获取仓库详情；无 token 时匿名限额 60 req/hr，易触发限流。

#### `JINA_API_KEY`（免费额度）

1. 打开 [jina.ai](https://jina.ai/) 注册账号
2. 在控制台创建 API Key（免费档有每日调用额度）
3. 写入 `.env` 的 `JINA_API_KEY`

**用途**：Hacker News 板块通过 [Jina Reader](https://jina.ai/reader/) 抓取外链正文；未配置时使用匿名调用，额度受限。

#### `PAGES_BASE_URL`（推送后填写）

完成 **D. GitHub Pages 开启** 并首次部署成功后填写，格式：

```
https://<你的GitHub用户名>.github.io/<仓库名>/
```

示例：用户 `zhangsan`、仓库 `ai-daily` 时：

```
PAGES_BASE_URL=https://zhangsan.github.io/ai-daily/
```

**注意**：

- 末尾建议保留 `/`
- 也可在 `config.json` 的 `push.wecom.pages_base_url` 填写（`.env` 优先）
- GitHub Actions 中若未设置，workflow 会尝试从 `GITHUB_REPOSITORY` 自动推断

---

## B. 创建 GitHub 仓库并首次 push

### B1. 在 GitHub 创建空仓库

1. 打开 [github.com/new](https://github.com/new)
2. **Repository name**：例如 `ai-daily`
3. 选 **Public** 或 **Private**（Pages 均可用；私有仓库 Pages 需 GitHub Pro 或组织计划）
4. **不要**勾选 "Add a README" / ".gitignore" / "license"（本地已有代码）
5. 点击 **Create repository**

### B2. 本地初始化并推送

在项目目录执行（将 `YOUR_USER` 和 `ai-daily` 替换为你的用户名与仓库名）：

```powershell
cd D:\Code\技术委员会\ai-daily

# 若尚未 init（已有 .git 可跳过）
git init
git branch -M main

# 确认 .env 不会被提交
git status
# 若看到 .env，切勿 git add；应已被 .gitignore 忽略

git add .
git commit -m "chore: 初始化 ai-daily 部署"
git remote add origin https://github.com/YOUR_USER/ai-daily.git
git push -u origin main
```

### B3. 确认 `.gitignore` 已保护敏感文件

`.gitignore` 已包含：

- `.env`（密钥）
- `config.json`（本地配置）
- `news-data/*`（fetch、notify 等运行时数据，**不提交**）
- `!news-data/push-*.md`（**例外**：日报全文需提交，供 GitHub Pages 托管）

推送前务必执行 `git status`，确认 **没有** `.env` 出现在待提交列表中。

### B4. 可选：上线前检查脚本

```powershell
.\scripts\prepare-github.ps1
```

---

## C. GitHub Repository Secrets（Actions 用）

仓库 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Secret | 必填 | 说明 |
|--------|------|------|
| `DEEPSEEK_API_KEY` | ✅ | 同 `.env`，供 LLM 调用 |
| `WECOM_WEBHOOK_URL` | ✅ | 同 `.env`，供企微推送 |
| `WECOM_WEBHOOK_URL` 相关 | — | 飞书 / Discord 若启用，可另设 `FEISHU_WEBHOOK_URL`、`DISCORD_WEBHOOK_URL`（见 `.env.example`） |
| `GITHUB_TOKEN` | 可选 | 见下方说明 |
| `JINA_API_KEY` | 可选 | 同 `.env`，HN 外链抓取 |
| `PAGES_BASE_URL` | 可选 | 同 `.env`；未设时 workflow 尝试自动推断 |

#### Actions 自带 `GITHUB_TOKEN` 与用户 PAT 的区别

| 类型 | 来源 | 说明 |
|------|------|------|
| **`github.token`（内置）** | Actions 自动注入 | 权限限于当前仓库，用于 checkout、Pages 部署等；**不能**用于调用 GitHub REST API 查 Trending |
| **用户 PAT（Secrets 中的 `GITHUB_TOKEN`）** | 你在 Developer settings 创建的 token | workflow 中 `env: GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}` 会覆盖内置 token 名称；用于 **GitHub Trending API** 提高限额 |

若早报 GitHub 板块频繁 403/限流，请在 Secrets 中添加名为 `GITHUB_TOKEN` 的用户 PAT（Classic 勾选 `public_repo` 即可）。

---

## D. GitHub Pages 开启

> **重要**：**Pages workflow（`pages.yml`）只负责部署站点**，不会抓取 RSS、不会生成日报、**不会推送企微**。  
> 企微消息与 `news-data/push-*.md` 由 **`daily.yml`（AI Daily 定时任务）** 或本地 `python -m src.main daily` 产生。  
> **digest 企微**在 **Pages 全文 URL 可访问（HTTP 200）之后**才发送，避免「完整版」链接先 404。

1. 仓库 **Settings** → **Pages**
2. **Build and deployment** → **Source** 选 **GitHub Actions**（不要选 "Deploy from a branch"）
3. 保存后无需手动上传文件

### 两个 Workflow 的分工

| Workflow | 文件 | 作用 | 企微 | Pages 全文 |
|----------|------|------|------|------------|
| **AI Daily 定时任务** | `daily.yml` | fetch → 生成 push md → publish → **等待 URL** → digest 企微 | ✅（URL 就绪后） | 先 publish 再推链接 |
| **GitHub Pages 日报全站** | `pages.yml` | 从仓库检出 `news-data/push-*.md` 并部署 | ❌ | ✅ |

**仅手动运行 Pages workflow 而仓库里没有 `push-*.md` 时**，首页会显示「暂无日报」——这是预期行为，不是 Pages 部署失败。

### `pages.yml` 工作流说明

文件：`.github/workflows/pages.yml`

**触发条件**：

- `main`/`master` 分支 push 且变更了 `news-data/push-*.md`、`scripts/build_pages_index.py` 或 workflow 本身
- 手动 **Run workflow**

**执行步骤**：

1. 运行 `scripts/build_pages_index.py` 生成 `index.html` 索引页
2. 将 `index.html` + `news-data/` 打包为 Pages 站点
3. 部署到 `https://<user>.github.io/<repo>/`

日报全文 URL 示例：

```
https://YOUR_USER.github.io/ai-daily/news-data/push-2026-06-30-17-00-30.html
```

首次 push 后若 `news-data/` 为空，请任选其一：

1. **推荐**：Actions → **AI Daily 定时任务** → Run workflow → Job 选 `all`（fetch → publish → 等待 Pages → digest 企微）
2. 本地一键：`uv run python -m src.main daily`（同上顺序；需已配置 git push 权限）
3. 仅重新部署（**不含新日报**）：Actions → **GitHub Pages 日报全站** → Run workflow

---

## E. 验证清单

按顺序逐项确认：

### E1. 本地验证

```powershell
cd D:\Code\技术委员会\ai-daily

# 子命令帮助（Windows GBK 终端亦应正常显示）
uv run python -m src.main --help

# LLM 连通性
uv run python -m src.main check

# 抓取（热点 ≥90 分会即时推送到企微）
uv run python -m src.main fetch

# 一键：fetch → publish → 等待 Pages → digest 企微（推荐）
uv run python -m src.main daily --dry-run
uv run python -m src.main daily

# 分步（与 CI 一致）
uv run python -m src.main push --defer-wecom   # 仅生成 push md
uv run python -m src.main publish              # commit + push，触发 Pages
uv run python -m src.main wecom                # 轮询 URL 后推 digest
```

可选：单板块调试（不推送）

```powershell
uv run python -m src.main github
uv run python -m src.main hackernews
uv run python -m src.main rss
```

### E2. GitHub Actions 手动触发

1. 仓库 **Actions** → **AI Daily 定时任务**（**不是**「GitHub Pages 日报全站」）
2. **Run workflow** → Job 选 `all`（或 `check` / `fetch` / `push`）
3. 查看日志无报错；`all` 任务末尾应有 publish、URL 轮询成功、digest 企微推送步骤

> 只跑 Pages workflow 不会发企微，也不会凭空产生 `push-*.md`。

定时规则（`.github/workflows/daily.yml`，UTC）：

- `0 0 * * *` → 北京时间 **08:00** 早报（含 GitHub / HN / 洞察）
- `0 9 * * *` → 北京时间 **17:00** 晚报（RSS digest）

### E3. 企微与 Pages 验收

- [ ] 企微 news：**有 RSS 封面的条目显示真实缩略图**；无封面条目及「完整版」卡片**不出现蓝色占位图**
- [ ] 同条或后续 **text 消息** 含「完整版」链接（需已配置 `PAGES_BASE_URL` 或 GHA 自动推断）
- [ ] 点击「完整版」链接**立即可**打开排版后的 HTML 全文（不应先 404）
- [ ] 站点首页 `https://YOUR_USER.github.io/ai-daily/` 列出历史日报索引

---

## 核心架构（简述）

```
RSS / GitHub Trending / Hacker News
        ↓ fetch（定时抓取 + LLM 评分）
   news-data/fetch-*.json
        ↓ push（digest / 即时推送）
   news-data/push-*.md  →  渲染 HTML + index  →  publish（GitHub Pages）
                              ↓ URL 200
                    digest 企微（news + 完整版链接）
```

- **fetch**：轮询 RSS，LLM 批量打分；≥90 分热点即时推送
- **push**：按 `push_cron` 生成中文日报；当天最早一次为「早报」（含 GitHub、HN、洞察三段）
- **配置**：`config.json`（调度、源、LLM、推送）+ `.env`（密钥）
- **Prompt**：已内置中文模板（`prompts/*.md`）

## 已做的本地适配

1. **企业微信 B+C 推送**：即时热点短消息 + 早晚报 news 图文 + text 完整版链接
2. **DeepSeek LLM**：`config.user.json.example` 已指向 `deepseek-chat`
3. **中文日报**：时区 `timezone_hours: 8`
4. **GitHub Actions**：`daily.yml`（抓取、企微推送、commit push 文件）+ `pages.yml`（仅部署 Pages）
5. **Windows 终端**：入口自动配置 stdout/stderr UTF-8，避免 GBK 下 emoji 报错

## 与 ai-digest 的主要差异

| 维度 | ai-digest | ai-daily |
|------|-----------|----------|
| RSS 源 | `config/sources.yaml` 少量源 | OPML 400+ 源，可 block/add |
| 推送节奏 | 每日一次 | fetch 轮询 + 热点即时推 + 早晚报 |
| 扩展板块 | 无 | GitHub Trending、HN 评论树、跨板块洞察 |
| 配置格式 | YAML + .env | JSON + .env |
| 部署 | 自带 GHA workflow | 本目录 GHA + 上游 systemd |

## 常见问题

**Q：能否只用企业微信、不用飞书？**  
A：可以。`config.user.json.example` 已 `wecom.enabled: true`，飞书/Discord 为 `false`。

**Q：LLM 费用？**  
A：DeepSeek 按 token 计费；可通过 `filter.min_score`、`llm.max_concurrent_batches` 控制调用量。

**Q：修改推送时间？**  
A：编辑 `config.json` 的 `schedule.push_cron`（cron 表达式；GHA 使用 UTC，workflow 已换算）。

**Q：Windows 终端乱码？**  
A：程序已自动 UTF-8 输出；若仍乱码可在 PowerShell 执行 `chcp 65001`，或使用 Windows Terminal。

---

上游文档详见 [README.md](./README.md)。排查顺序：`uv run python -m src.main check` → 检查 `WECOM_WEBHOOK_URL` → 查看 Actions 日志。


## GitHub 仓库上线（网页需手动完成）

仓库地址：https://github.com/zk1239520941/ai-daily  
Pages 地址：https://zk1239520941.github.io/ai-daily/

本地已配置 push.wecom.pages_base_url / PAGES_BASE_URL 指向上述 Pages 根路径；.env 与 config.json 不会提交到 Git，请在仓库与本地分别维护。

### Settings → Secrets and variables → Actions

在 Repository secrets 中新增（名称须与 workflow 一致）：

| Secret 名称 | 说明 |
|-------------|------|
| DEEPSEEK_API_KEY | DeepSeek API 密钥 |
| WECOM_WEBHOOK_URL | 企业微信群机器人 Webhook 完整 URL |
| GITHUB_TOKEN | 可选；GitHub Trending 等扩展源 |
| JINA_API_KEY | 可选；Jina 阅读/抓取相关能力 |

勿在 Issue、PR 或日志中粘贴上述值。

### Settings → Pages

1. Build and deployment → Source 选择 GitHub Actions（不要选 Deploy from a branch）。
2. 首次有内容需先跑 **AI Daily 定时任务**（或本地 push 后 `git push news-data/push-*.md`），再等待 **GitHub Pages 日报全站** 自动或手动部署。

### 推荐操作顺序（上线后）

1. 在仓库 **Secrets** 配置 `DEEPSEEK_API_KEY`、`WECOM_WEBHOOK_URL`（及可选 `GITHUB_TOKEN`、`JINA_API_KEY`、`PAGES_BASE_URL`）
2. **Settings → Pages** → Source 选 **GitHub Actions**
3. **Actions → AI Daily 定时任务 → Run workflow → `all`**
4. 确认日志中 fetch、push、企微发送、**提交 push 日报** 均成功
5. 等待 **GitHub Pages 日报全站** 被 push 触发并完成（约 1～2 分钟）
6. 打开 https://zk1239520941.github.io/ai-daily/ 应能看到日报链接；企微群应收到消息

若第 3 步未跑 Daily 而只跑了 Pages，站点会显示「暂无日报」且企微无消息。

### 推送失败（认证）

Windows 下可任选其一：执行 gh auth login 后 git push -u origin main；或使用 PAT（Classic，勾选 repo）配合 git config credential.helper manager 再 push。勿把 PAT 写入仓库文件。
