# 第一次在這台電腦啟動拆單系統 (Windows + Docker Desktop)
# 用法：在專案資料夾執行  .\scripts\install.ps1 [-WebPort 8100] [-DbPort 15434]
param([int]$WebPort = 8100, [int]$DbPort = 15434)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Write-Host "請先安裝 Docker Desktop：https://www.docker.com/products/docker-desktop/" -ForegroundColor Red; exit 1 }
docker info *> $null; if ($LASTEXITCODE -ne 0) { Write-Host "Docker Desktop 尚未啟動，請先打開它再執行。" -ForegroundColor Red; exit 1 }

# 檢查 port 是否被占用
foreach ($p in @($WebPort, $DbPort)) {
  if (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue) { Write-Host "Port $p 已被使用，請改用 -WebPort / -DbPort 指定別的。" -ForegroundColor Red; exit 1 }
}
if (-not (Test-Path .env)) {
  $pw = -join ((48..57 + 97..122) | Get-Random -Count 16 | ForEach-Object { [char]$_ })
  Set-Content -Encoding ascii .env "POSTGRES_PASSWORD=$pw`nWEB_PORT=$WebPort`nDB_PORT=$DbPort`n"
  Write-Host "已建立 .env（資料庫密碼隨機產生，請勿刪除此檔）"
}
docker compose up -d --build
Write-Host ""
Write-Host "啟動完成：http://localhost:$WebPort   （API 文件 http://localhost:$WebPort/docs）" -ForegroundColor Green
Write-Host "同網路其他電腦：http://<這台的IP>:$WebPort"
Write-Host "之後更新：.\scripts\update.ps1   備份：.\scripts\backup.ps1"
