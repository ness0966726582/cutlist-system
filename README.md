# 拆單專案管理系統 (Docker: Nginx + FastAPI + PostgreSQL)

> 專案資料夾：`C:\Users\MTK_d\projects\cutlist-system`（2026-10-28 起獨立，之前在 ness 底下）。
> 版本號在 `VERSION`，每次更新寫 `CHANGELOG.md`（系統內「更新紀錄」頁直接顯示）。
> 主機 DB port 改為 **15434**（15433 被 ness_db 使用），在 `.env` 設定。

## 部署到 Synology NAS（DS723+）

不用 Git、不用原始碼：打版本 tag 後 GitHub Actions 會把三個映像推到 GHCR，NAS 只放 `deploy/nas/docker-compose.yml` 拉映像。完整步驟見 [deploy/nas/README.md](deploy/nas/README.md)。
發版方式：`VERSION` 進號、`CHANGELOG.md` 加段落、`git tag v1.0.1 && git push origin v1.0.1` → Release 工作流程自動建映像與 GitHub Release。

## 換一台電腦部署（Windows / Linux / NAS，原始碼方式）

需要：Docker（Windows 裝 Docker Desktop；Linux 裝 Docker Engine + compose plugin）、能登入 GitHub 的方式（repo 是私有的）。

```bash
git clone https://github.com/ness0966726582/cutlist-system.git
```

```bash
cd cutlist-system; .\scripts\install.ps1
```

Linux / NAS 改成 `bash scripts/install.sh`。第一次會自動建 `.env`（隨機資料庫密碼、port 8100 / 15434），建映像、載入基礎資料，約 2～3 分鐘，完成後開 `http://<那台IP>:8100`。
沒有 Git 的電腦：到 GitHub 頁面 Code → Download ZIP 解壓縮後一樣跑 install；但之後更新就要重新下載，建議裝 Git 或 GitHub Desktop。

把舊電腦的資料搬過去：舊電腦跑 `.\scripts\backup.ps1`，把 `backups\<時間>\` 整個資料夾複製到新電腦專案底下，新電腦跑 `.\scripts\restore.ps1 -From backups\<時間>`。

| 腳本 | 做什麼 |
|------|--------|
| `scripts/install.ps1` / `.sh` | 第一次啟動（檢查 Docker 與 port、建 .env、build、up） |
| `scripts/update.ps1` / `.sh` | 更新到 GitHub 最新版：先備份 → `git pull` → 重建 → 顯示版本（`-Tag v1.2.0` 可指定版本，也就是回退） |
| `scripts/backup.ps1` / `.sh` | 備份資料庫（pg_dump）與圖面檔到 `backups/<時間>/`，保留 30 份；建議用工作排程器每天跑 |
| `scripts/restore.ps1` | 從某份備份還原（會覆蓋） |

## GitHub 日常用法（你不需要打 git 指令）

- **看改了什麼**：repo 頁面 → Commits；每個 commit 說明對應 CHANGELOG。
- **CI 綠燈**：Actions 分頁，每次推送自動跑測試與建置，紅燈就不要更新現場。
- **版本**：Releases / Tags 對應 `VERSION`；現場用 `update.ps1 -Tag vX.Y.Z` 裝指定版，出問題退回上一個 tag。
- **回饋變 Issue**（可選）：回饋頁匯出的清單可以貼成 Issue，commit 訊息寫 `fixes #12` 會自動關閉。
- **GitHub Desktop**：想用視窗看差異或手動 commit 時裝它即可，和這裡的 CLI 共用同一組登入。
- 日常分工：操作者只碰系統畫面；你負責回饋頁、更新與備份；開發（我）負責 commit、CI、發版。

## 長期維護流程（操作者回饋 → 修改 → 發版）

1. 操作者在系統任何頁面按右下角「💬 意見回饋」，選類型（問題／需求／疑問）寫內容送出；系統自動記下頁面與專案。
2. 管理者到「回饋」頁看清單，改狀態（新 → 已排程 → 已完成／不處理）、寫處理備註。
3. 要請開發者改的：按「匯出待處理清單」下載 Markdown，整段貼給 Claude（在這個專案資料夾開 session），Claude 依 `#編號` 逐項處理。
4. 改完：`VERSION` 進號、`CHANGELOG.md` 加一段、`docker compose up -d --build`，回到「回饋」頁把對應項目改「已完成」。操作者在「更新紀錄」頁看得到改了什麼。
5. 回饋相關 API：`POST /api/feedback`、`GET /api/feedback?status=&category=`、`PUT/DELETE /api/feedback/{id}`、`GET /api/feedback-export.md?status=new,planned`、`GET /api/version`、`GET /api/changelog`。

由「拆單系統 2026年6.0版」Excel 重構而來的網頁版專案管理系統。
料單公式（封邊、標記、提醒、才數、單價）已移植到後端 `api/app/rules.py`，
Excel 的基礎資料分頁（色號、單價表、拆單用、標記、資料庫、五金配件、廠商資料）已匯出為 `db/init/02_seed.sql`。

## 架構

```
瀏覽器 ──► Nginx (:8100) ──► /api/*  ──► FastAPI (api:8000) ──► PostgreSQL 16 (db:5432, 主機 :15433)
                 └── 靜態頁面 web/html (index.html / app.js / style.css)
```

| 服務 | 容器名稱 | 主機 Port | 說明 |
|------|----------|-----------|------|
| web  | cutlist-web | **8100** | Nginx，靜態頁 + 反向代理 `/api/`、`/docs` |
| api  | cutlist-api | （僅內部 8000） | FastAPI，Swagger 文件在 `/docs` |
| db   | cutlist-db  | **15434** | PostgreSQL 16，資料存在 volume `cutlist-system_cutlist_db_data` |

Port 選擇依據：本機已佔用 80 / 443 / 8080 / 8086 / 8090 / 8091 / 5050 / 15432 / 15433 等。
要改 port 修改 `.env` 的 `WEB_PORT` / `DB_PORT`（範本在 `.env.example`）。

## 專案結構

```
cutlist-system/
  docker-compose.yml  .env  VERSION  CHANGELOG.md  README.md  docs_ANALYSIS.md
  api/        FastAPI (app/main.py 主要 API、extras.py 補充分頁、rules.py 料單規則、importer/exporter.py Excel)
  web/        Nginx + 靜態前端 (html/app.js、tour.js、style.css)
  db/init/    01_schema.sql、02_seed.sql (基礎資料)、03_seed_extra.sql (牌價/成本)
  samples/    空白範本 17.5 / 18、新竹金山街案例 xlsx + PDF (測試與示範用)
  tools/      匯種子、回歸測試 (smoke_test*.py)、分析腳本
```

## 啟動

```bash
cd cutlist-system
docker compose up -d --build
```

- 前台：http://localhost:8100
- API 文件：http://localhost:8100/docs
- 資料庫：`postgresql://cutlist:cutlist_dev@localhost:15433/cutlist`

第一次啟動時 PostgreSQL 會自動執行 `db/init/01_schema.sql` 與 `02_seed.sql`。
若要重建資料庫（會清除資料）：`docker compose down -v` 再 `up -d --build`。

## 圖面 / 附件怎麼存

- 設計師的 PDF（一頁一區域）或照片，在專案的「圖面」分頁整份上傳；檔案存在 docker volume `cutlist_files`（容器內 `/data/files/{專案id}/`），資料庫只存中繼資料（`attachments` 表）。
- PDF 會自動算頁數，每頁有縮圖（PyMuPDF 轉 PNG，依 dpi 快取），點縮圖開大圖，可翻頁、開原尺寸、下載原檔。
- 每個櫃體可指定「圖面頁」與「圖上編號 ①②③」，料單打單時按「看圖」直接對照該頁；圖面頁縮圖下方也會列出對應的櫃號。
- 備份：`docker run --rm -v cutlist-system_cutlist_files:/data -v %cd%:/backup alpine tar czf /backup/files.tgz /data`。

## 從既有 Excel 料單匯入

專案列表右上「從既有 Excel 料單匯入」選 .xlsx（需有「料單」分頁）。會：
- 讀表頭（訂單編號、案場、業務/設計師、訂貨/交貨日期、拉/KD、送貨地址）與每個櫃體區塊；板厚取桶身最常見值（17.5 或 18）。
- 跳過未使用的空白範本區塊（沒櫃名也沒尺寸）與範本預填列（長/寬/數量都空）。
- Excel 內手動改過的封邊（含 `A`）、備註 1~3、提醒會原樣保留，並標成「手動覆寫」（黃底，↺ 可恢復自動值）。
- 類別留空的列依板材名稱反查零件目錄自動補上。

## 匯出成原 Excel 料單格式

專案頁右上「匯出 Excel 料單」（或專案列表的 ⬇ Excel）。做法：

- 依專案板厚選空白範本 `api/templates/blank_17.5.xlsx` / `blank_18.xlsx`（即原「拆單系統 2026年6.0版空白」檔），只回填「料單」分頁：表頭 + 每個櫃體區塊（名稱、櫃號、高深寬、批次、明細 30 列）。
- 明細列的封邊、備註 1~3、提醒、色號名稱/板商/封邊色號直接寫系統的值（含手動覆寫），不靠範本公式。
- 其他分頁（板材才數分析、標籤列印版、計價清價、流水號、叫料計算…）公式保留，檔案設定為開啟時全部重算，所以在 Excel 打開後數字會自己出來。
- 一個櫃體超過 30 列會自動接到下一個區塊（名稱加「(續)」、櫃號相同）；範本最多 45 個區塊。
- 已知限制：openpyxl 不保留範本裡的圖形物件與部分進階資料驗證，匯出檔的下拉選單可能較少；外部連結公式（計價清價 (2) 的 `[1]`）仍指向原本的桌面檔。

## Excel 其餘分頁的對應（第二階段補齊）

| Excel 分頁 | 系統 |
|------------|------|
| 計價清價 (2)、計價清價 | 專案 → 計價/報價：板材牌價 × 板材折數（專案覆寫 > 客戶設定）＋ 加工費 ＋ 安裝（手填或 折後板材 × 客戶安裝折數）＋ 運費 → 5% 稅。四捨五入採 ROUND_HALF_UP 與 Excel 相同 |
| 資料庫 AC~AL（五金配件牌價、門板加工牌價、特殊加工板材） | 基礎資料 → 加工/封邊；計價頁「加工費」可從牌價選、或「依料單備註帶入」（斜把/打型/Z把/崁把手，數量依單位推算：公分＝板寬/10、才＝才數、孔＝片數） |
| 報價單 | 計價/報價 → 列印報價單（公司資料的抬頭、匯款資訊、條款；逐櫃列項目） |
| 零件單 | 專案 → 零件單（五金彙總 + 五金配件目錄比對規格），可列印 |
| 色號1~4 的封邊條規格欄 | 叫料計算 → 封邊條（依色號 × 規格），規格依板厚分組，在 加工/封邊 頁可調 |
| 標籤列印版 W/X/Y/Z、結合器 | 標籤 CSV 新增 長封邊首碼/長封邊A/寬封邊首碼/寬封邊尾碼/結合器 欄 |
| 五金配件 進銷貨紀錄 | 基礎資料 → 五金配件 → 每列「進銷貨」：進貨/銷貨/退回 紀錄、傳票、案場；庫存＝進 − 銷 + 銷退 − 進退 |
| 客戶對帳單 | 客戶頁 → 客戶對帳單：選客戶與月份（依交貨日或訂貨日），列出該月訂單的計價總額，可列印 |
| 牌價表(對公司內部)、對外賣價表 | 基礎資料 → 牌價表：底價 × 係數 → 賣價 → × 折數 → 業務/員工實價，× 1.2 含安裝；「列印對外賣價表」 |
| 20230916成本分析 | 基礎資料 → 成本分析：進貨成本 ×1.05 → 每材 / 含損料每材 → + 封邊 → 製成成本 → + 毛利 → 實價（未稅/完稅）、毛利率 |
| 報價單抬頭、匯款資訊 | 基礎資料 → 公司資料 |

這些資料的種子在 `db/init/03_seed_extra.sql`（由 `tools/export_seed_extra.py` 從範本匯出）；既有資料庫可用 `docker cp 03_seed_extra.sql cutlist-db:/tmp/ && docker exec cutlist-db psql -U cutlist -d cutlist -f /tmp/03_seed_extra.sql` 載入。

## 基礎資料維護（前台可直接改）

- 色號 / 單價：「色號 × 板厚」單價矩陣，格子改完即存、清空即刪該單價；最上面綠色列新增色號；可依廠商篩選、搜尋色號/板名/封邊色號。「下載 CSV」→ Excel 改 →「匯入 CSV」整批更新（同格式；空白＝不變、`-`＝刪除）。仍被板材使用的色號不能刪。
- 零件目錄：左側類別（依拆單順序 桶身 → 內部 → 外部 → 抽屜 … → 五金），右側該類別項目：搜尋全部類別、改名、↑↓ 排序、搬到別的類別、移除、新增（已在料單裡的板材不受影響）。
- 下拉清單：同樣版面，板厚 / 設計師 / 基材 / 板材廠商 / 計價單位可新增、改名、排序、移除；狀態代碼只讀。
- 前端檔案帶 build 時間戳（`app.js?v=…`）且 `Cache-Control: no-store`，重建後瀏覽器不會再用到舊檔。
- 標記、五金配件、廠商：表格內直接改、最上列新增、✕ 刪除。
- 下拉清單：板厚、設計師、基材、板材廠商、計價單位可新增／移除。
- API：`GET/POST /api/master/colors`、`PUT/DELETE /api/master/colors/{code}`、`GET /api/master/colors-export.csv`、`POST /api/master/colors-import-csv`、`GET /api/master/thicknesses`、`POST/PUT/DELETE /api/master/marks|hardware|vendors`、`DELETE /api/master/parts-catalog/{id}`。

## 新手導覽與快速開始

- 右上角「？ 導覽」：逐步高亮說明目前頁面；每一頁與專案的每個分頁都有（專案列表、客戶、基礎資料、料單、圖面、統計、計價、標籤、流水號、叫料）。第一次進入該頁會自動詢問，記錄在瀏覽器 localStorage。步驟定義在 `web/html/tour.js` 的 `TOURS`，改文字不需動其他程式。
- 板厚：專案的板厚從「常用板厚」下拉選（預設 18 / 17.5），旁邊 ＋ 可直接新增；完整維護在 基礎資料 → 下拉清單（板厚、設計師、基材、板材廠商、計價單位 都可新增／移除）。
- 專案頁頂端「快速開始」七個圓點：圖面、櫃體、對圖、尺寸、色號、草稿列、匯出，依目前資料即時計算，橘色＝未完成，點了跳到對應分頁。

## 料單操作重點（依實際料單用法調整）

- 板材名稱可直接打字（有建議清單），不用先選類別；類別會自動判斷。
- 封邊下拉：`AA`（兩邊）/ `A`（一邊）/ 空；備註 1~3、提醒都可直接改，改過的格子變黃底，按 ↺ 恢復自動。
- 櫃體列：「複製櫃體」（同款不同寬最快）、「櫃體色號 → 套用色號」（背板/抽底除外）、「圖面頁 / 圖上編號 / 看圖」。
- 左側櫃體導覽可跳到任一櫃，「收合/展開」讓 20 幾櫃的案子好捲動。
- 表格內欄位改完按 Enter 或點別處即儲存，游標會跳到同列下一格。

## 資料規則（審查後定案）

- 板材名稱空白的列是「草稿列」（紅框），不進統計、計價、標籤、流水號、匯出。
- 類別留空依名稱反查零件目錄，同名多類別時依 桶身 > 內部 > 外部 > 抽屜 > … > 五金 取；改名後若舊類別沒有這個名稱會重新判斷。
- 五金類列不給預設厚度與色號；板材列預設專案板厚與櫃體色號（含背板）。
- 流水號固定配給每一片（`piece_serials` 表），增刪板材不會位移；刪掉的片號碼作廢不重用。掃描可在頁面取消。
- 櫃號不可重複、必須 ≥ 1；對調櫃號先改成暫時號碼。櫃體順序（sort）獨立於櫃號，複製的櫃體排在最後。
- 匯入 Excel：只認數量 > 0 的列；序號依列順序重編；同櫃號區塊（含「(續)」）合併；拉/KD 只認 L / KD / 拉。
- 匯出 Excel：沒有板材的櫃體不佔區塊；超過 45 區塊會以提示告知。
- 統計與計價清單用同一套每列金額（四捨五入到分）。

## 功能對應 Excel 分頁

| Excel 分頁 | 系統功能 |
|------------|----------|
| 料單 | 專案 → 櫃體 → 板材；新增櫃體可自動產生 桶身/內部/外部 標準板件（尺寸公式依板厚 17.5 / 18 自動計算） |
| 料單 G/I/P/Q/R/T 欄 | 封邊、備註 1~3、提醒 自動計算（可切換 `auto_rules=false` 手動覆寫） |
| 板材才數分析 | 每列才數 = 長×寬/90000×數量；統計分頁 |
| 計價清價 (2) | 「計價清單」分頁：單價表 (色號×板厚) × 才數，含運費/安裝/5% 稅 |
| 標籤列印版 | 「標籤列印」分頁，可下載 CSV 給標籤機 |
| 流水號 | 「流水號/掃描」分頁：依數量展開每片序號，開板/包裝掃描確認 |
| 叫料計算、色號1~4 | 「叫料計算」分頁：依色號×板厚彙總才數與封邊條長度 |
| 色號、單價表、拆單用、標記、資料庫、五金配件、廠商資料 | 「基礎資料」頁；資料來自 seed |
| 客戶資料 | 「客戶」頁（未匯入 Excel 內個資，請自行建檔） |

## 重新匯出基礎資料

```bash
python -I ../tools/export_seed.py "拆單系統 2026年6.0版空白 18.xlsx" db/init/02_seed.sql
```

## 主要 API

- `GET/POST /api/projects`、`GET/PUT/DELETE /api/projects/{id}`
- `POST /api/projects/{id}/cabinets`、`PUT/DELETE /api/cabinets/{id}`
- `POST /api/cabinets/{id}/parts`、`PUT/DELETE /api/parts/{id}`
- `POST /api/projects/import-xlsx`（multipart file）
- `POST /api/cabinets/{id}/duplicate`、`POST /api/cabinets/{id}/apply-color`、`POST /api/parts/{id}/reset-auto`
- `GET/POST /api/projects/{id}/attachments`、`GET /api/attachments/{id}/file`、`GET /api/attachments/{id}/pages/{n}.png?dpi=110`、`PUT/DELETE /api/attachments/{id}`
- `GET /api/projects/{id}/summary | quote | labels | serials | material`
- `POST /api/projects/{id}/scans`（開板 cut / 包裝 pack）
- `GET /api/master/colors?q=`、`GET /api/master/colors/{code}`、`PUT /api/master/colors/{code}`
- `GET /api/master/parts-catalog | marks | lookups | hardware | vendors`
- `GET/POST/PUT /api/customers`
