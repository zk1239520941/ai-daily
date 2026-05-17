
<h1 align="center">AI Daily 每日资讯推送系统</h1>

![AI Daily Banner](https://cdn.yeekal.com/yee/blog/2026-03/ai-daily-cover-wide-ultra.webp)

<p align="center">AI 驱动的 RSS 新闻聚合与推送系统 | 支持 400+ 信息源 | LLM 智能评分 | 推送到 Discord/飞书</p>



## 核心功能

- **即时推送** —— 热点新闻（≥90分）立即推送到手机
- **定时汇总** —— 每天早 8 点、晚 5 点自动推送 AI 资讯日报
- **400+ RSS 源** —— 聚合全球主流 AI 媒体、博客、Twitter 账号（源自 [BestBlogs](https://github.com/ginobefun/BestBlogs)）
- **LLM 智能筛选** —— 自动评分过滤，低质量内容不推送

## 两大优势

### 1. 即时推送 —— 避免错过重要信息

当系统检测到评分极高（≥90分）的热点新闻时，会立即推送到指定平台，确保重要信息不过时。

**适用场景：** 重大发布、突破性技术进展、行业重磅新闻

### 2. 每日汇总 —— 把握 AI 全局近况

每天定时（如早8点、晚5点）汇总近期高评分资讯，帮助用户快速了解 AI 领域整体动态。

**适用场景：** 碎片化时间回顾、行业趋势把握

---

## 快速开始

### 环境要求

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python 包管理器)
- Linux + systemd（推荐使用一键部署）

### 1. 配置环境变量

在项目根目录创建 `.env` 文件，添加以下配置：

```bash
# LLM API（ OpenAI API 兼容接口）
OPENROUTER_API_KEY=your_api_key_here

# GitHub API token (可选，提升 API 限额到 5000 req/hr；不设时匿名调用 60 req/hr)
GITHUB_TOKEN=your_github_token_here

# 飞书 Webhook
FEISHU_WEBHOOK_URL=your_feishu_webhook_url_here

# Or Discord Webhook
# DISCORD_WEBHOOK_URL=your_webhook_url_here
```

从模板拷贝一份本地配置（`config.json` 已加入 `.gitignore`，不会提交）：

```bash
cp config.json.example config.json
```

然后在 `config.json` 中修改 `llm` 和 `push`

```json
{
    "llm": {
        "provider": "<whatever>",  # openai compatiable 
        "model": "<model id>",
        "baseUrl": "<base url>",
        "apiKeyName": "OPENROUTER_API_KEY", #your api key name in .env>
    },
    "push": {
        "feishu": {
            "enabled": true,
            "apiKeyName": "FEISHU_WEBHOOK_URL"
        }
    },

}

```

**获取飞书群机器人 Webhook**

详细教程参考：[我用 RSS + LLM 搭建了一个 AI 热点追踪系统](https://yeekal.com//ai/ai-daily-news-tracker)


1. 群组右上角设置 → 群机器人 → 添加机器人
2. 选择 自定义机器人 → 点击 添加 → 复制 Webhook URL

**获取 Discord Webhook：**
1. 进入 Discord 服务器设置 → 
2. 整合 → Webhooks
2. 创建新 Webhook，复制 URL


### 2. 一键部署（推荐）

将程序作为 systemd timer 部署，由系统负责定时触发、故障重启、开机自启。

```bash
./scripts/install.sh
```

脚本会自动同步依赖、安装 systemd 服务并按 `config.json` 中的调度配置启动定时任务，**机器重启后自动恢复**。安装成功后无需额外操作。

### 3. 手动运行（可选）

若不使用 systemd，也可以手动运行程序。先同步依赖（uv 会自动创建 `.venv`）：

```bash
uv sync
```

程序提供 4 个子命令：

```bash
uv run python -m src.main check    # 校验 LLM 接口可达性（部署期使用）
uv run python -m src.main fetch    # 单次抓取后退出（systemd timer 调用）
uv run python -m src.main push     # 单次推送后退出（systemd timer 调用）
uv run python -m src.main loop     # 长跑模式（本地开发/调试用）
uv run python -m src.main github       # 单跑 GitHub Trending 板块,打印不推送
uv run python -m src.main hackernews   # 单跑 Hacker News 板块,打印不推送
```

首次运行会自动创建 `news-data/` 目录并开始抓取数据。

> 若未配置推送渠道，则可以在 news-data 目录查看生成的push信息

---

## 系统服务管理

部署完成后，使用以下命令管理服务。

### 常用命令

安装后 `daily-news` 进入系统 PATH，可在任意目录调用：

```bash
daily-news status [N]      # 查看 timer/service 状态 + 最近 N 行日志（默认 15）
daily-news logs            # 实时跟随日志（Ctrl+C 退出）
daily-news start           # 启动两个 timer
daily-news stop            # 停止两个 timer
daily-news restart         # 重启两个 timer（仅重置调度，不立即触发任务）
daily-news help            # 用法说明
```

手动立即触发一次任务（不影响下次调度）：

```bash
sudo systemctl start dnews-fetch.service
sudo systemctl start dnews-push.service
```

### 修改配置后

```bash
./scripts/install.sh   # 重新跑一次即可，幂等（重新渲染单元 + restart timer）
```

修改 `config.json` 中的 `schedule`、`log.retention_days` 等需要重装；修改 `.env` 只需 `daily-news restart`。

### 卸载

```bash
./scripts/uninstall.sh
```

卸载会移除 systemd 单元、`/usr/local/bin/daily-news` 和日志保留 drop-in；**不会**删除 `news-data/` 数据。

### 日志保留

日志通过 systemd journald 命名空间 `dnews` 隔离，保留天数由 `config.json` 中的 `log.retention_days` 控制（默认 7 天）。不影响系统其他服务的日志。

### 日志查询

```bash
daily-news logs                                     # 实时跟随两个 service 的日志
daily-news status [N]                               # 查看状态 + 最近 N 行日志（默认 15）

journalctl --namespace=dnews -f                     # 实时跟随命名空间内全部日志
journalctl --namespace=dnews -u dnews-fetch -f      # 仅跟随 fetch service
journalctl --namespace=dnews -u dnews-push -f       # 仅跟随 push service
journalctl --namespace=dnews --since "1 hour ago"   # 查询近 1 小时日志
journalctl --namespace=dnews --since today          # 查询今日日志
journalctl --namespace=dnews -p err                 # 仅查询 error 级别及以上
journalctl --namespace=dnews --vacuum-time=1s       # 手动清空命名空间日志
```

---

## 配置详解（config.json）

完整的配置文件结构如下，每个字段都有详细说明：

```json
{
    // 订阅源管理
    "sources": {
        "base_opml": "resources/rss.opml",  // 基础OPML文件，包含400+预设源
        "add": [  // 自定义添加的RSS源
            {
                "title": "OpenAI News",
                "xmlUrl": "https://openai.com/news/rss.xml",
                "category": "AI"
            }
        ],
        "block": [  // 手动屏蔽的源，精确匹配xmlUrl
            {
                "title": "Google Developers Blog",
                "xmlUrl": "https://developers.googleblog.com/feeds/posts/default"
            }
        ],
        "block_domains": ["*.substack.com", "*.youtube.com"]  // 域名屏蔽，支持通配符
    },

    // 内容过滤
    "filter": {
        "min_score": 60,  // 最低评分阈值，低于此分不推送
        "hot_threshold": 90,  // 热点阈值，达到立即即时推送
        "context_days": 3,  // 汇总时参考的历史天数
        "keep_days": 7,  // 数据保留天数
        "push_context_days": 5,  // 汇总推送去重的上下文有效天数
        "no_content_marker": "[NO_NEW_CONTENT]"  // LLM返回的无内容标记，用于判断是否跳过推送
    },

    // 日志配置（仅对 systemd 部署生效）
    "log": {
        "retention_days": 7  // journald 命名空间 dnews 的日志保留天数
    },

    // 调度配置
    "schedule": {
        "fetch_interval_minutes": 30,  // RSS抓取间隔（分钟）
        "fetch_lookback_minutes": 120,  // RSS冗余缓存时间（分钟），必须大于fetch_interval_minutes，用于防止RSS延迟导致漏读
        "push_cron": ["0 8 * * *", "0 17 * * *"],  // 定时推送cron表达式
        "timezone_hours": 8  // 时区偏移（8=北京时间）
    },

    // 抓取配置
    "fetch": {
        "max_workers": 10,  // 最大并发数
        "timeout": 10  // 单请求超时（秒）
    },

    // LLM配置
    "llm": {
        "provider": "openai",  // 提供商类型，openai只是知名该api接口时openai接口兼容，代码中并无实际使用
        "model": "x-ai/grok-4.1-fast",  // 模型名称
        "baseUrl": "https://openrouter.ai/api/v1",  // API端点
        "apiKeyName": "OPENROUTER_API_KEY",  // 环境变量名
        "max_prompt_chars": 128000,  // 单次prompt最大字符数
        "max_concurrent_batches": 3,  // 最大并发批次数
        "prompts": {  // prompt文件路径
            "score": "prompts/score.txt",
            "score_batch": "prompts/score_batch.txt",
            "immediate_push": "prompts/immediate_push.txt",
            "digest": "prompts/digest.txt"
        }
    },

    // 推送配置
    "push": {
        "discord": {
            "enabled": true,  // 是否启用
            "apiKeyName": "DISCORD_WEBHOOK_URL"  // Webhook环境变量名
        },
        "feishu": {
            "enabled": false,
            "apiKeyName": "FEISHU_WEBHOOK_URL"
        }
    }
}
```

### sources —— 订阅源管理

| 字段 | 类型 | 说明 |
|------|------|------|
| `base_opml` | string | 基础 OPML 文件路径，包含 400+ 预设 RSS 源 |
| `add` | array | 自定义添加的 RSS 源，结构为 `{title, xmlUrl, category}` |
| `block` | array | 手动屏蔽的 RSS 源，精确匹配 `xmlUrl` |
| `block_domains` | array | 域名级别屏蔽，支持通配符（如 `*.substack.com`） |

### filter —— 内容过滤

| 字段 | 类型 | 说明 |
|------|------|------|
| `min_score` | number | 最低评分阈值，低于此分数的内容不参与推送（默认60） |
| `hot_threshold` | number | 热点阈值，达到此分数立即触发即时推送（默认90） |
| `context_days` | number | 上下文天数，汇总推送时参考的fetch数据历史天数（默认3天） |
| `keep_days` | number | 数据保留天数，超过天数的 JSON 文件会被清理 |
| `push_context_days` | number | 汇总推送去重的历史push文件有效天数（默认5天） |
| `no_content_marker` | string | LLM 返回的无内容标记，当推送内容包含此字符串时跳过推送（默认"[NO_NEW_CONTENT]"） |

### log —— 日志配置

仅对 `scripts/install.sh` 部署的 systemd 服务生效。

| 字段 | 类型 | 说明 |
|------|------|------|
| `retention_days` | number | journald 命名空间 `dnews` 的日志保留天数（默认 7 天）。修改后需要重跑 `./scripts/install.sh` |

### schedule —— 调度配置

| 字段 | 类型 | 说明 |
|------|------|------|
| `fetch_interval_minutes` | number | RSS 抓取间隔，单位分钟（默认30分钟） |
| `fetch_lookback_minutes` | number | RSS 冗余缓存时间（分钟），必须大于 `fetch_interval_minutes`，用于防止 RSS 延迟导致漏读（默认120分钟） |
| `push_cron` | array | 定时推送的 cron 表达式数组，支持多个时间点 |
| `morning_cron` (可选) | string | 早报 cron 表达式 (例: `"0 8 * * *"`)。命中时启用三个额外板块(GitHub / HN / 洞察)。缺失则全程纯 RSS。 |
| `morning_match_tolerance_minutes` (可选,默认 5) | number | 早报判定容差(分钟)。 |
| `timezone_hours` | number | 时区偏移小时数，用于时间显示（8 = UTC+8 北京时间） |

**cron 表达式说明：**

| 表达式 | 含义 |
|--------|------|
| `0 8 * * *` | 每天早上 8:00 |
| `0 17 * * *` | 每天下午 5:00 |
| `0 9,17 * * *` | 每天早上 9:00 和下午 5:00 |

格式：`minute hour day month weekday`

### fetch —— 抓取配置

| 字段 | 类型 | 说明 |
|------|------|------|
| `max_workers` | number | 最大并发数，同时抓取的 RSS 源数量 |
| `timeout` | number | 单个请求超时时间，单位秒 |

### llm —— 大语言模型配置

| 字段 | 类型 | 说明 |
|------|------|------|
| `provider` | string | LLM 提供商（支持 openai 兼容接口） |
| `model` | string | 模型名称，如 `x-ai/grok-4.1-fast` |
| `baseUrl` | string | API 端点，如 `https://openrouter.ai/api/v1` |
| `apiKeyName` | string | 环境变量名称，系统会自动读取其值 |
| `max_prompt_chars` | number | 单次 prompt 最大字符数，用于分批控制 |
| `max_concurrent_batches` | number | 最大并发批次数 |
| `prompts` | object | prompt 文件路径配置 |

### push —— 推送平台配置

| 字段 | 类型 | 说明 |
|------|------|------|
| `discord.enabled` | boolean | 是否启用 Discord 推送 |
| `discord.apiKeyName` | string | Discord Webhook 的环境变量名 |
| `feishu.enabled` | boolean | 是否启用飞书推送 |
| `feishu.apiKeyName` | string | 飞书 Webhook 的环境变量名 |

### sections (早报扩展板块)

仅在 `schedule.morning_cron` 命中时生效。详细设计见 `docs/extra-sections-design.md`。

#### sections.github_trending
- `enabled`: 是否启用
- `max_items`: LLM 最终选出的项目数上限(默认 3)
- `max_deep_dive`: 单次最多 deep-dive 的候选 repo 数(默认 10)
- `readme_max_chars`: README 截断长度(默认 5000)
- `history_file`: trending 去重索引文件路径
- `request_timeout`: HTTP 超时秒
- `tokenName`: GitHub token 环境变量名;不设时匿名调用(限 60 req/hr)

#### sections.hackernews
- `enabled`: 是否启用
- `select_k`: 轻 LLM 从首页 30 条中挑出的故事数(默认 1)
- `top_comments`: 每个故事抓取的顶层评论数(默认 20)
- `comment_max_chars`: 单条评论截断长度(默认 800)
- `link_content_max_chars`: 外链正文截断长度(默认 6000)
- `request_timeout`: HTTP 超时秒
- `algolia_base`: Algolia API 基址

#### sections.insights
- `enabled`: 是否启用跨板块洞察段


## 扩展指南

### 添加新的 RSS 源

在 `config.json` 的 `sources.add` 中添加：

```json
"add": [
    {
        "title": "我的自定义源",
        "xmlUrl": "https://example.com/feed.xml",
        "category": "AI"
    }
]
```

### 添加新的推送平台

1. 在 `src/push/` 目录下创建新文件，继承 `PushPlatform` 基类
2. 实现 `validate_config()` 和 `send()` 方法
3. 在 `src/push/__init__.py` 中注册

### 修改评分逻辑

编辑 `prompts/score.txt`，调整评分标准和权重。

### 自定义 LLM 模型

修改 `config.json` 中的 `llm` 配置：

```json
"llm": {
    "model": "anthropic/claude-3-opus",
    "baseUrl": "https://openrouter.ai/api/v1",
    "apiKeyName": "OPENROUTER_API_KEY"
}
```

## RSS 源说明


RSS 订阅源文件位于 `resources/rss.opml`，目前包含约 420 个订阅源。

RSS 订阅源初始整理自 [ginobefun/BestBlogs](https://github.com/ginobefun/BestBlogs)，包含约 420 个 AI 领域优质信息源。

用户可自行配置 RSS 源文件，只需遵循 OPML 格，在 `config.json` 的 `sources.base_opml` 修改文件路径即可。 同时用户可修改 `sources.add`或者  `sources.block`以在不破换OMPL文件的前提下对rss源进行增加或者删除。格式示例：

```json
"sources": {
    "base_opml": "resources/rss.opml",
    "add": [
        {
            "title": "OpenAI News",
            "xmlUrl": "https://openai.com/news/rss.xml",
            "category": "AI"
        },
        {
            "title": "Chrome for Developers",
            "xmlUrl": "https://developer.chrome.com/static/blog/feed.xml",
            "category": "Chrome"
        }
    ],
    "block": [
        {
            "title": "Google Developers Blog",
            "xmlUrl": "https://developers.googleblog.com/feeds/posts/default"
        },
        {
            "title": "Microsoft for Developers",
            "xmlUrl": "https://devblogs.microsoft.com/landing"
        },
        {
            "title": "ElevenLabs Blog",
            "xmlUrl": "https://api.bestblogs.dev/feed/elevenLabsBlog"
        }
    ],
    "block_domains": ["*.substack.com", "*.youtube.com"]
}
```
## License

MIT License - see [LICENSE](LICENSE) file for details.
