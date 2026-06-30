# AI Daily pre-push checks (does not read .env contents)
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "=== AI Daily GitHub Check ===" -ForegroundColor Cyan

if (Test-Path ".env") {
    Write-Host "OK  .env exists" -ForegroundColor Green
} else {
    Write-Host "WARN  missing .env  ->  copy .env.example .env" -ForegroundColor Yellow
}

if (Test-Path "config.json") {
    Write-Host "OK  config.json exists" -ForegroundColor Green
} else {
    Write-Host "WARN  missing config.json  ->  copy config.user.json.example config.json" -ForegroundColor Yellow
}

if (-not (Test-Path ".git")) {
    Write-Host "WARN  git not initialized" -ForegroundColor Yellow
} else {
    $status = git status --porcelain 2>$null
    if ($status) {
        Write-Host ""
        Write-Host "git status --porcelain:" -ForegroundColor DarkGray
        Write-Host $status
    } else {
        Write-Host "OK  clean working tree" -ForegroundColor Green
    }

    $trackedEnv = git ls-files .env 2>$null
    if ($trackedEnv) {
        Write-Host "ERR  .env is tracked!  run: git rm --cached .env" -ForegroundColor Red
    } else {
        Write-Host "OK  .env not tracked" -ForegroundColor Green
    }

    $remote = git remote get-url origin 2>$null
    if ($LASTEXITCODE -eq 0 -and $remote) {
        Write-Host "OK  remote origin = $remote" -ForegroundColor Green
    } else {
        Write-Host "WARN  no remote  ->  git remote add origin https://github.com/USER/REPO.git" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Next:  python -m src.main check" -ForegroundColor Cyan
