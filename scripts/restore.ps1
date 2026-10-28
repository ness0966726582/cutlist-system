# 從備份還原（會覆蓋目前資料！）
# 用法：.\scripts\restore.ps1 -From backups\20261028_221500
param([Parameter(Mandatory = $true)][string]$From)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path (Join-Path $From "db.dump"))) { Write-Host "找不到 $From\db.dump" -ForegroundColor Red; exit 1 }
$ans = Read-Host "這會清掉目前資料庫與圖面，改成 $From 的內容。確定？(yes/no)"
if ($ans -ne "yes") { exit 0 }

docker compose up -d db
Start-Sleep 5
docker cp (Join-Path $From "db.dump") cutlist-db:/tmp/db.dump
docker exec cutlist-db sh -c "psql -U cutlist -d postgres -c 'DROP DATABASE IF EXISTS cutlist WITH (FORCE)' && psql -U cutlist -d postgres -c 'CREATE DATABASE cutlist' && pg_restore -U cutlist -d cutlist /tmp/db.dump && rm -f /tmp/db.dump"
if (Test-Path (Join-Path $From "files.tgz")) {
  $abs = (Resolve-Path $From).Path
  docker run --rm -v cutlist-system_cutlist_files:/data -v "${abs}:/backup" alpine sh -c "rm -rf /data/* && tar xzf /backup/files.tgz -C /data"
}
docker compose up -d
Write-Host "還原完成。" -ForegroundColor Green
