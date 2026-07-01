# CLAUDE.md — 本仓库开发说明

AI 驱动的 RSS 新闻聚合与推送系统：400+ 信息源，LLM 评分，**企业微信**推送，**GitHub Pages** 全文。

## 本实例部署形态（与 upstream 不同）

| 环境 | 调度 | 配置 |
|------|------|------|
| **生产** | GitHub Actions：`fetch.yml` / `daily.yml` / `health-check.yml` | `config.user.json` + Secrets |
| **本地调试** | `uv run python -m src.main loop` 或子命令 | `config.json` + `.env` |

上游 YeeKal 默认 **systemd** 部署；本 fork **不用 systemd 跑生产**。

## 关键路径

```
fetch.yml (hourly) → news-data/fetch-*.json + 热点 notify
daily.yml → push md → publish (git) → deploy-pages (同 job) → URL 200 → wecom
health-check.yml → 当日无 digest/skip 则告警
```

## 技术栈

- Python 3.12+，`uv` 管理依赖
- feedparser, aiohttp, croniter, openai 兼容 LLM
- 数据目录 `news-data/`（git 真源）；`run-state.json` 记录运行状态

## 常用命令

```bash
uv run python -m src.main check
uv run python -m src.main fetch
uv run python -m src.main push --defer-wecom
uv run python -m src.main publish
uv run python -m src.main wecom
uv run python -m src.main daily
uv run pytest tests/pytest/
```

## 文档

- [README.md](./README.md) — 项目概览
- [SETUP-用户.md](./SETUP-用户.md) — 上线清单
- [docs/tech-spec.md](./docs/tech-spec.md) — 上游技术规格（systemd 章节为 upstream 路径）

## 注意

- digest 企微：**禁止**在 Pages URL 未 200 时推送（见 `cmd_wecom`）
- GHA 使用 `cp config.user.json config.json`，勿只改本地 `config.json` 指望线上生效
- 修改 workflow 后需 push 且 token 需 `workflow` scope（若用 PAT push）
