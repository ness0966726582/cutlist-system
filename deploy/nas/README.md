# 在 Synology DS723+ 部署拆單系統

不需要在 NAS 裝 Git、不需要原始碼。GitHub 每次發版會把映像推到 GitHub Container Registry（GHCR），NAS 只拉映像。

## 第一次安裝（約 15 分鐘）

**1. NAS 準備**
- 套件中心 → 安裝「Container Manager」。
- 控制台 → 終端機 & SNMP → 啟動 SSH 服務（做完可以關掉）。
- File Station → 在 `docker` 共用資料夾建 `cutlist` 資料夾（路徑 `/volume1/docker/cutlist`）。

**2. 放檔案**：把這個資料夾（deploy/nas）的 5 個檔案上傳到 `/volume1/docker/cutlist`：
`docker-compose.yml`、`.env.example`、`update.sh`、`backup.sh`、`restore.sh`（GitHub Releases 頁每個版本都附這些檔）。
把 `.env.example` 改名成 `.env`，`POSTGRES_PASSWORD` 改成一串隨機密碼（之後不要再改）。

**3. 讓 NAS 能拉私有映像**（只做一次）
- GitHub → 右上頭像 → Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token：名稱 `nas-pull`，勾 `read:packages`，到期可選 No expiration。複製 token。
- SSH 進 NAS（Windows 用 PowerShell：`ssh 你的NAS帳號@NAS的IP`），執行：

```bash
sudo docker login ghcr.io -u ness0966726582
```

密碼貼上剛才的 token。之後 Container Manager 與指令都能拉映像。

**4. 啟動**（SSH 內）

```bash
cd /volume1/docker/cutlist && sudo docker compose up -d
```

或用 Container Manager → 專案 → 新增 → 專案名稱 `cutlist` → 路徑選 `/docker/cutlist` → 來源選「使用現有的 docker-compose.yml」→ 下一步到完成。第一次拉映像約 1～3 分鐘。

**5. 開啟**：`http://NAS的IP:8100`。廠內電腦、平板都用這個網址。

## 搬資料（從目前的 Windows 電腦）
Windows 電腦跑 `.\scripts\backup.ps1`，把 `backups\<時間>` 資料夾上傳到 `/volume1/docker/cutlist/backups/`，SSH 內：

```bash
cd /volume1/docker/cutlist && sudo sh restore.sh backups/<時間>
```

## 日常

| 事情 | 做法 |
|------|------|
| 更新到新版 | SSH：`cd /volume1/docker/cutlist && sudo sh update.sh`（自動先備份；`sudo sh update.sh 1.0.1` 指定版本，也可退回舊版） |
| 每日備份 | 控制台 → 任務排程器 → 新增 → 排程的任務 → 使用者定義的指令碼：使用者 root，每天 02:00，指令 `sh /volume1/docker/cutlist/backup.sh`。備份在 `backups/`，再用 Hyper Backup 整個 `/volume1/docker/cutlist` 備到外接碟或雲端 |
| 看狀態 | Container Manager → 容器，三個 cutlist-* 都是執行中；或 `sudo docker compose ps` |
| 看版本 | 系統右上角版本號；或 `cat data/../.env` 的 CUTLIST_VERSION |

## 注意
- `data/` 是資料庫與圖面的本體，不要手動改。資料庫密碼存在 `.env`，遺失就打不開資料庫。
- 系統沒有登入機制，只開在內網；不要把 8100 port 對外轉發。
- NAS 上的 DB 不對外開 port（只有容器內可連）；要用工具看資料請在 compose 的 db 加 ports。
