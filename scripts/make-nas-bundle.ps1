# 產生 NAS 離線安裝包：dist\cutlist-nas-<版本>\  （含映像 tar、compose、腳本、目前資料備份）
# 用法：.\scripts\make-nas-bundle.ps1 [-NoData]   -NoData = 不附目前資料（全新空系統）
param([switch]$NoData, [ValidateSet("amd64","arm64")][string]$Arch = "amd64")   # DS223 等 ARM 機種用 -Arch arm64
# 注意：docker 會把進度印到 stderr，PowerShell 5.1 在 Stop 模式會當成錯誤，所以這裡用 Continue + 檢查 $LASTEXITCODE
$ErrorActionPreference = "Continue"
Set-Location (Split-Path $PSScriptRoot -Parent)
function Check($what) { if ($LASTEXITCODE -ne 0) { Write-Host "$what 失敗" -ForegroundColor Red; exit 1 } }
$ver = (Get-Content VERSION | Select-Object -First 1).Trim()
$owner = "ness0966726582"
$suffix = if ($Arch -eq "arm64") { "-arm64" } else { "" }
$out = "dist\cutlist-nas-$ver$suffix"
if (Test-Path $out) { Remove-Item $out -Recurse -Force }
New-Item -ItemType Directory -Force $out | Out-Null

# 1. 確保本機映像是最新程式碼，標成 GHCR 名稱 (與 NAS compose 一致)
if ($Arch -eq "amd64") {
  docker compose build --quiet 2>&1 | Out-Null; Check "docker compose build"
  foreach ($s in "api", "web", "db") { docker tag "cutlist-system-$s" "ghcr.io/$owner/cutlist-${s}:$ver" 2>&1 | Out-Null; Check "docker tag $s" }
} else {
  # ARM：用 buildx + QEMU 交叉建置 (約 5~10 分鐘)，tag 帶 -arm64，setup.sh 會依檔名把 CUTLIST_VERSION 設成 1.0.0-arm64
  docker buildx build --platform linux/arm64 --load -f api/Dockerfile -t "ghcr.io/$owner/cutlist-api:$ver$suffix" . 2>&1 | Out-Null; Check "buildx api"
  docker buildx build --platform linux/arm64 --load -t "ghcr.io/$owner/cutlist-web:$ver$suffix" web 2>&1 | Out-Null; Check "buildx web"
  docker buildx build --platform linux/arm64 --load -t "ghcr.io/$owner/cutlist-db:$ver$suffix" db 2>&1 | Out-Null; Check "buildx db"
}
Write-Host "匯出映像 (約 1~2 分鐘)..."
docker save -o "$out\images-$ver$suffix.tar" "ghcr.io/$owner/cutlist-api:$ver$suffix" "ghcr.io/$owner/cutlist-web:$ver$suffix" "ghcr.io/$owner/cutlist-db:$ver$suffix" 2>&1 | Out-Null; Check "docker save"

# 2. NAS 檔案
Copy-Item deploy\nas\docker-compose.yml, deploy\nas\setup.sh, deploy\nas\update.sh, deploy\nas\backup.sh, deploy\nas\restore.sh, deploy\nas\README.md $out
# 腳本改成 LF 行尾，NAS 的 sh 才讀得懂
foreach ($f in Get-ChildItem "$out\*.sh") { $t = [IO.File]::ReadAllText($f.FullName) -replace "`r`n", "`n"; [IO.File]::WriteAllText($f.FullName, $t, (New-Object Text.UTF8Encoding $false)) }

# 3. 目前資料
if (-not $NoData) {
  & "$PSScriptRoot\backup.ps1" | Out-Null
  $latest = Get-ChildItem backups -Directory | Sort-Object Name -Descending | Select-Object -First 1
  New-Item -ItemType Directory -Force "$out\backups\$($latest.Name)" | Out-Null
  Copy-Item "$($latest.FullName)\db.dump", "$($latest.FullName)\files.tgz" "$out\backups\$($latest.Name)"
  Write-Host "已附上資料備份 $($latest.Name)"
}

$size = [math]::Round(((Get-ChildItem $out -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 0)
Write-Host ""
Write-Host "完成：$out  ($size MB)" -ForegroundColor Green
Write-Host "把整個資料夾上傳到 NAS 的 /volume1/docker/cutlist，SSH 進去跑：sudo sh setup.sh"
