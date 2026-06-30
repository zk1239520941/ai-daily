# digest_wecom（备用）

早晚报企微 **news 图文** 默认由代码从 `digest.md` 生成的正文 + frontmatter 自动解析，**通常无需单独调用本 prompt**。

若将来需要 LLM 直接输出企微 news JSON，可启用本模板。输出格式：

```json
{
  "articles": [
    {
      "title": "栏目标题，≤128字",
      "description": "摘要，≤128字",
      "url": "https://..."
    }
  ]
}
```

最多 8 条。第一条建议为日报总览（title=日报标题，description=lead，url=完整版 Pages 链接）。
