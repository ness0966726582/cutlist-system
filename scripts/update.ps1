# 更新到 GitHub 上的最新版：先備份 → git pull → 重建容器 → 顯示版本
# 用法：.\scripts\update.ps1        （加 -NoBackup 跳過備份；加 -Tag v1.2.0 更新到指定版本）
param([switch]$NoBackup, [string]$Tag = "")
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$git = if (Get-Command git -ErrorAction SilentlyContinue) { "git" } else { "C:\Program Files\Git\cmd\git.exe" }

if (-not $NoBackup) { & "$PSScriptRoot\backup.ps1" }
& $git fetch --tags origin
if ($Tag) { & $git checkout -q $Tag } else { & $git checkout -q main; & $git pull --ff-only origin main }
docker compose up -d --build
Start-Sleep 5
$ver = (Get-Content VERSION -ErrorAction SilentlyContinue | Select-Object -First 1)
Write-Host ""
Write-Host "更新完成，目前版本 v$ver。請操作者在瀏覽器按 Ctrl+F5 重新整理。" -ForegroundColor Green
docker compose ps --format "{{.Name}} {{.Status}}"
