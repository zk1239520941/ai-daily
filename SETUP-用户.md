# AI Daily 上线前准备清单

本目录为 [YeeKal/ai-daily](https://github.com/YeeKal/ai-daily) 的独立部署副本（当前实例：[zk1239520941/ai-daily](https://github.com/zk1239520941/ai-daily)），与同级目录 `ai-digest` **并行存在、互不影响**。

按下列顺序完成配置，推送到 GitHub 后由 **GitHub Actions 全自动** 抓取、生成 digest、部署 Pages、推送企微。

> 项目概览见 [README.md](./README.md)。

---

## 与 ai-digest 的关系

| 项目 | 路径 | 定位 |
|------|------|------|
| **ai-digest** | `../ai-digest` | 自研轻量漏斗：YAML 配置、单次日报、结构简单 |
| **ai-daily**（本项目） | `./` | 400+ RSS、即时热点、GitHub/HN/洞察早报、企微 + Pages |

**建议**：日常推送以 **ai-daily** 为主；`ai-digest` 保留作对照或备用。

---

## A. 本地密钥（`.env`）

### A1. 安装依赖

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

```powershell
cd D:\Code\技术委员会\ai-daily
uv sync
```

### A2. 复制配置模板

```powershell
copy .env.example .env
copy config.user.json.example config.json   # 本地调试用；线上用 config.user.json
```

### A3. 填写 `.env`

编辑 `.env`（**切勿提交**，已在 `.gitignore` 中）：

| 变量 | 必填 | 说明 |
|------|------|------|
| `LLM_API_KEY` | ✅ | LLM 评分与 digest（兼容旧名 `DEEPSEEK_API_KEY`） |
| `WECOM_WEBHOOK_URL` | ✅ | 企微群机器人 Webhook |
| `PAGES_BASE_URL` | 推荐 | 如 `https://<user>.github.io/ai-daily/` |
| `GITHUB_TOKEN` | 可选 | 提高 GitHub Trending API 限额 |
| `JINA_API_KEY` | 可选 | HN 外链正文（Jina Reader） |

#### `LLM_API_KEY`

支持任意 **OpenAI 兼容** 接口的大模型。在 `.env` 或 Secrets 中配置 Key，并在 `config.user.json` 中设置对应的 `llm.baseUrl` 与 `llm.model`。

**示例（DeepSeek，低成本选项之一）：**

1. [DeepSeek 开放平台](https://platform.deepseek.com/) 创建 Key
2. `llm.baseUrl`: `https://api.deepseek.com/v1`，`model`: `deepseek-chat`

**示例（OpenAI）：** `baseUrl`: `https://api.openai.com/v1`，`model`: `gpt-4o-mini`

> 向后兼容：若仍使用旧环境变量名 `DEEPSEEK_API_KEY`，程序会自动读取（`LLM_API_KEY` 优先）。

#### `WECOM_WEBHOOK_URL`

企业微信群 → 群机器人 → 添加 → 复制 Webhook URL。

#### `GITHUB_TOKEN`（可选 PAT）

Developer settings → Personal access tokens → Classic 勾选 `public_repo`（公开库）或 `repo`（私有库）。  
用于 GitHub Trending 板块；Actions 内置 token **不能**替代此用途。

#### `PAGES_BASE_URL`

```
https://<GitHub用户名>.github.io/<仓库名>/
```

示例：`https://zk1239520941.github.io/ai-daily/`（末尾建议保留 `/`）。  
Secrets 或 `.env` 均可；未设时程序尝试从 `GITHUB_REPOSITORY` 推断。

---

## B. 创建 GitHub 仓库并首次 push

### B1. 创建空仓库

[github.com/new](https://github.com/new) → 仓库名 `ai-daily` → **Public**（推荐，Actions 分钟数宽裕）→ 不要勾选 README。

### B2. 推送代码

```powershell
git remote add origin https://github.com/YOUR_USER/ai-daily.git
git push -u origin main
```

推送前 `git status` 确认 **无 `.env`**、**无 `config.json`**。

### B3. `.gitignore` 要点

| 忽略 | 例外（会提交） |
|------|----------------|
| `.env`、`config.json` | `config.user.json` |
| `news-data/*` | `fetch-*.json`、`notify-*.md`、`push-*.md/html`、`run-state.json`、`push-skip-*.json` |

---

## C. GitHub Repository Secrets

**Settings → Secrets and variables → Actions**

| Secret | 必填 | 说明 |
|--------|------|------|
| `LLM_API_KEY` | ✅ | 同 `.env`（兼容旧名 `DEEPSEEK_API_KEY`） |
| `WECOM_WEBHOOK_URL` | ✅ | 同 `.env` |
| `PAGES_BASE_URL` | 推荐 | 同 `.env` |
| `GITHUB_TOKEN` | 可选 | 用户 PAT，非 Actions 内置 token |
| `JINA_API_KEY` | 可选 | 同 `.env` |

**线上配置真源**：仓库内 [`config.user.json`](./config.user.json)（workflow 执行 `cp config.user.json config.json`）。

---

## D. GitHub Pages 开启

1. **Settings → Pages → Source：GitHub Actions**
2. 不要选 "Deploy from a branch"

### Workflow 分工（当前架构）

| Workflow | 文件 | 触发 | 作用 |
|----------|------|------|------|
| **AI Daily 抓取** | `fetch.yml` | 每小时 | RSS 抓取 + 评分 + 热点企微 + commit-fetch |
| **AI Daily 早报** | `daily.yml` | 每天 ~08:05 北京 | 补抓 → digest → git publish → **同 job 内 deploy Pages** → URL 200 后企微 |
| **AI Daily 健康检查** | `health-check.yml` | 每天 ~09:00 北京 | 检查当日 digest/skip，异常企微告警 |
| **AI Daily LLM 校验** | `check.yml` | 手动 | `main check` |
| **GitHub Pages 日报全文** | `pages.yml` | push 触发 / 手动 | **备用**全站部署（主路径已在 `daily.yml` 内联完成） |

> **digest 企微仅在 Pages 全文 URL 返回 HTTP 200 后发送**，不会先发链接再让你刷新。

### `daily.yml` 手动 Run workflow 参数

| 参数 | 说明 |
|------|------|
| `skip_fetch` | 跳过补抓，直接生成 digest |
| `force` | 忽略当日已有 digest/skip，强制重新生成 |
| `wecom_only` | Pages 已就绪时，仅重发企微（不跑 fetch/publish） |

### 日报全文 URL 格式

```
https://YOUR_USER.github.io/ai-daily/news-data/push-2026-07-01-08-00-00.html
```

---

## E. 验证清单

### E1. 本地验证

```powershell
uv run python -m src.main check
uv run python -m src.main fetch
uv run python -m src.main daily --dry-run
uv run python -m src.main daily

# 与 CI 一致的分步
uv run python -m src.main push --defer-wecom
uv run python -m src.main publish
uv run python -m src.main wecom
```

### E2. GitHub Actions 手动触发

1. **Actions → AI Daily 早报 → Run workflow**（首次全链路）
2. 或 **AI Daily 抓取 → Run workflow**（仅测 fetch）
3. 查看日志：`deploy-pages` 成功 → `wecom` 步骤成功

**定时规则（UTC）**：

| Cron | Workflow | 约北京时间 |
|------|----------|------------|
| `0 * * * *` | `fetch.yml` | 每小时整点 |
| `5 0 * * *` | `daily.yml` | ~08:05 |
| `0 1 * * *` | `health-check.yml` | ~09:00 |

### E3. 企微与 Pages 验收

- [ ] 热点即时推送正常（≥90 分）
- [ ] 早报企微含 news 卡片 + 完整版 text 链接
- [ ] 点击完整版链接 **立即可打开** HTML（非 404）
- [ ] 首页 https://zk1239520941.github.io/ai-daily/ 有索引
- [ ] Actions 中 `health-check` 为绿色（或有当日 skip 记录）

---

## 核心架构

```
RSS / GitHub Trending / Hacker News
        ↓ fetch.yml（每小时）
   news-data/fetch-*.json  +  热点 notify
        ↓ daily.yml（每日）
   push-*.md → git commit → deploy Pages（同 job）
        ↓ URL HTTP 200
   digest 企微
        ↓ health-check.yml（兜底）
   无 digest 则告警
```

- **配置**：`config.user.json`（线上）+ Secrets + 本地 `config.json`（调试）
- **状态**：`news-data/run-state.json`、`push-skip-*.json` 记录运行与静默日

---

## 已做的本地适配

1. **企微推送**：即时热点 + digest news + 完整版链接
2. **LLM 默认**：`config.user.json` 默认使用 DeepSeek（可改为其他 OpenAI 兼容模型）
3. **时区**：`timezone_hours: 8`
4. **GitHub Actions 多 workflow**：fetch / daily / health-check，daily **内联 Pages 部署**
5. **调度修复**：移除脆弱的 `date -u` detect；独立 concurrency
6. **Windows UTF-8**：`src/console.py` 避免 GBK emoji 报错

---

## 与 ai-digest 的主要差异

| 维度 | ai-digest | ai-daily（本实例） |
|------|-----------|-------------------|
| RSS 源 | YAML 少量源 | OPML 400+ |
| 推送 | 每日一次 | hourly 热点 + 每日 digest |
| 渠道 | 自建 | **企业微信** |
| 全文 | 无 / 自建 | **GitHub Pages** |
| 部署 | 自建 GHA | **fetch + daily + health-check** |
| 配置 | YAML | `config.user.json` + Secrets |

---

## 常见问题

**Q：只用企微、不用飞书/Discord？**  
A：可以。`config.user.json` 已 `wecom.enabled: true`，其余为 `false`。

**Q：LLM 费用？**  
A：按 token 计费，为主要成本来源，与 GitHub Actions 无关。DeepSeek 等为低成本选项之一。

**Q：公开库 Actions 会超 2000 分钟吗？**  
A：**公开仓库**标准 runner 基本不限分钟；**私有库** Free 约 2000 分钟/月，hourly fetch 易触顶。

**Q：收到企微但链接 404？**  
A：不应再出现（已改为 Pages deploy 完成 + URL 200 后才推）。若复现，查 `daily.yml` 的 `deploy-pages` 与 `wecom` 步骤日志。

**Q：修改推送时间？**  
A：改 `.github/workflows/daily.yml` 的 cron（UTC）；`config.json` 的 `push_cron` 主要影响收录窗口语义。

---

## 本仓库上线信息

| 项 | 值 |
|----|-----|
| 仓库 | https://github.com/zk1239520941/ai-daily |
| Pages | https://zk1239520941.github.io/ai-daily/ |
| 配置真源 | `config.user.json` + Actions Secrets |
| 本地密钥 | `.env` / `config.json`（不提交） |

### 推荐操作顺序（新环境）

1. 配置 Secrets：`LLM_API_KEY`、`WECOM_WEBHOOK_URL`、`PAGES_BASE_URL`
2. **Settings → Pages → GitHub Actions**
3. **Actions → AI Daily 早报 → Run workflow**
4. 确认日志：`deploy-pages` ✅ → `wecom` ✅
5. 打开 Pages 首页 + 检查企微

补发企微（Pages 已好、只想重发）：**AI Daily 早报 → Run workflow → 勾选 `wecom_only`**。

排查顺序：`main check` → Secrets → Actions 日志 → `news-data/run-state.json`。
