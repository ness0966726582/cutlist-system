# 備份資料庫 + 圖面檔到 backups\<日期時間>\ （資料庫 .sql 與 files.tgz）
# 用法：.\scripts\backup.ps1 [-Keep 30]   保留最近 N 份
param([int]$Keep = 30)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$dir = Join-Path "backups" $stamp
New-Item -ItemType Directory -Force $dir | Out-Null

# 資料庫：pg_dump 在容器內執行，輸出到容器 /tmp 再 docker cp 出來（避免 PowerShell 轉碼）
docker exec cutlist-db pg_dump -U cutlist -d cutlist -F c -f /tmp/db.dump
if ($LASTEXITCODE -ne 0) { throw "pg_dump 失敗" }
docker cp cutlist-db:/tmp/db.dump (Join-Path $dir "db.dump")
docker exec cutlist-db rm -f /tmp/db.dump
# 圖面 volume
$abs = (Resolve-Path $dir).Path
docker run --rm -v cutlist-system_cutlist_files:/data -v "${abs}:/backup" alpine tar czf /backup/files.tgz -C /data .
Copy-Item .env (Join-Path $dir ".env") -ErrorAction SilentlyContinue
$size = [math]::Round(((Get-ChildItem $dir | Measure-Object Length -Sum).Sum / 1MB), 1)
Write-Host "備份完成：$dir  ($size MB)" -ForegroundColor Green

# 清掉舊備份
Get-ChildItem backups -Directory | Sort-Object Name -Descending | Select-Object -Skip $Keep | Remove-Item -Recurse -Force
