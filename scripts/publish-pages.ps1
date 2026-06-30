# 本地 push 后：把 news-data/push-*.md 提交到 GitHub，触发 Pages 更新（解决全文链接 404）
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

python scripts/build_pages_index.py
git add news-data/push-*.md index.html static/
$staged = git diff --staged --name-only
if (-not $staged) {
    Write-Host "[publish-pages] 无新日报，跳过 commit"
    exit 0
}
git commit -m "chore(data): 更新日报 push 文件"
git push
Write-Host "[publish-pages] 已推送，Pages 约 1-3 分钟后更新"
