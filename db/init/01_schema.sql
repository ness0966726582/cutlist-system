-- 拆單專案管理系統 schema (PostgreSQL 16)
-- 對應 Excel 分頁：色號 / 單價表 / 拆單用 / 標記 / 資料庫 / 五金配件 / 廠商資料 / 客戶資料 / 料單

CREATE TABLE IF NOT EXISTS vendors (
    id              serial PRIMARY KEY,
    name            text NOT NULL UNIQUE,
    company_name    text,
    tax_id          text,
    address         text,
    factory_address text,
    phone           text
);

-- 色號：板材色號 → 色號板名 / 板材廠商 / 封邊色號
CREATE TABLE IF NOT EXISTS color_codes (
    code        text PRIMARY KEY,
    board_name  text,
    vendor      text,
    edge_code   text,
    series      text
);

-- 單價表：色號 × 板厚 → 每才單價
CREATE TABLE IF NOT EXISTS price_table (
    code        text NOT NULL REFERENCES color_codes(code) ON DELETE CASCADE,
    thickness   numeric(5,2) NOT NULL,
    price       numeric(12,2) NOT NULL,
    PRIMARY KEY (code, thickness)
);

-- 拆單用：類別 (桶身/內部/外部/抽屜/...) → 板材名稱清單 (料單 E 欄下拉來源 INDIRECT($D14))
CREATE TABLE IF NOT EXISTS part_catalog (
    id        serial PRIMARY KEY,
    category  text NOT NULL,
    name      text NOT NULL,
    sort      int  NOT NULL DEFAULT 0,
    UNIQUE (category, name)
);

-- 標記：加工標記代碼
CREATE TABLE IF NOT EXISTS marks (
    id      serial PRIMARY KEY,
    name    text NOT NULL UNIQUE,
    code    text,
    number  numeric,
    sort    int NOT NULL DEFAULT 0
);

-- 資料庫!AM:AN 狀態 / 狀態代碼 (標籤列印版 U 欄)
CREATE TABLE IF NOT EXISTS status_codes (
    code  text PRIMARY KEY,
    name  text NOT NULL
);

-- 其他下拉清單 (基材 / 板材廠商 / 計價單位 / 設計師)
CREATE TABLE IF NOT EXISTS lookup_values (
    kind   text NOT NULL,
    value  text NOT NULL,
    sort   int  NOT NULL DEFAULT 0,
    PRIMARY KEY (kind, value)
);

CREATE TABLE IF NOT EXISTS hardware_catalog (
    id             serial PRIMARY KEY,
    vendor         text,
    product_name   text NOT NULL,
    model          text,
    spec           text,
    purchase_unit  text,
    sales_unit     text,
    list_price     numeric(12,2),
    note           text
);

CREATE TABLE IF NOT EXISTS customers (
    id               serial PRIMARY KEY,
    code             text UNIQUE,            -- 客戶編號 (AA0B001)
    name             text NOT NULL,          -- 設計師/業務
    contact_phone    text,
    company_name     text,
    tax_id           text,
    address          text,
    company_phone    text,
    board_discount   numeric(5,3),           -- 板材折數
    install_discount numeric(5,3),           -- 安裝折數
    created_at       timestamptz NOT NULL DEFAULT now()
);

-- 專案 = 料單表頭 (一張料單 = 一個案場訂單)
CREATE TABLE IF NOT EXISTS projects (
    id               serial PRIMARY KEY,
    order_no         text NOT NULL UNIQUE,   -- 訂單編號 = yyyymmdd + 流水號 (料單!C1)
    site_name        text NOT NULL,          -- 案場
    customer_id      int REFERENCES customers(id),
    designer         text,                   -- 業務/設計師
    order_date       date NOT NULL DEFAULT CURRENT_DATE,
    delivery_date    date,
    delivery_address text,
    board_thickness  numeric(5,2) NOT NULL DEFAULT 18,  -- 17.5 版 / 18 版 差異即在此
    status           text NOT NULL DEFAULT 'draft',     -- draft / confirmed / producing / done
    revision_dates   jsonb NOT NULL DEFAULT '[]',        -- 1~3 修改日期
    note             text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);

-- 櫃體 (料單每 39 列一個區塊：櫃體名稱 / 櫃號 / 櫃高 / 櫃深 / 櫃寬 / 批次)
CREATE TABLE IF NOT EXISTS cabinets (
    id          serial PRIMARY KEY,
    project_id  int NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    cabinet_no  int NOT NULL,                -- 櫃號
    name        text NOT NULL,               -- 櫃體名稱
    height      numeric(8,1),                -- 櫃高 (mm)
    depth       numeric(8,1),                -- 櫃深 (不含門)
    width       numeric(8,1),                -- 櫃寬
    batch       int NOT NULL DEFAULT 1,      -- 批次
    note        text,                        -- 料單!D7 IFS: 水槽櫃/爐台櫃→無頂板, 油機吊櫃→無底板
    sort        int NOT NULL DEFAULT 0,
    UNIQUE (project_id, cabinet_no)
);

-- 板材 (料單明細列)
CREATE TABLE IF NOT EXISTS parts (
    id          serial PRIMARY KEY,
    cabinet_id  int NOT NULL REFERENCES cabinets(id) ON DELETE CASCADE,
    part_no     bigint NOT NULL,             -- 專案編號 = 櫃號*1000 + 序號
    seq         int NOT NULL,
    category    text,                        -- 類別 (桶身/內部/外部/抽屜/.../五金)
    name        text NOT NULL,               -- 板材名稱
    length      numeric(8,1),                -- 長 (同紋)
    edge_l      text,                        -- 封邊 (長邊) 自動: AA / 空
    width       numeric(8,1),                -- 寬
    edge_w      text,                        -- 封邊 (寬邊) 自動
    thickness   numeric(5,2),                -- 厚
    qty         int NOT NULL DEFAULT 1,      -- 生產數量
    color_code  text,                        -- 板材色號 → 色號表
    mark_p      text,                        -- 備註 P 欄 (鉸鏈數 / 背板溝 / 側 / 面)
    mark_q      text,                        -- 備註 Q 欄 (側 / 面 / 輪 / 固)
    mark_r      text,                        -- 備註 R 欄 (排)
    remark      text,                        -- 備註 S 欄 (人工)
    reminder    text,                        -- 提醒 T 欄
    status_code text NOT NULL DEFAULT 'A' REFERENCES status_codes(code),
    auto_rules  boolean NOT NULL DEFAULT true,  -- false = 使用者手動覆寫封邊/標記
    UNIQUE (cabinet_id, part_no)
);

CREATE INDEX IF NOT EXISTS idx_parts_cabinet ON parts(cabinet_id);
CREATE INDEX IF NOT EXISTS idx_cabinets_project ON cabinets(project_id);

-- 掃描紀錄 (流水號分頁: 開板掃描 / 包裝掃描)
CREATE TABLE IF NOT EXISTS scans (
    id          serial PRIMARY KEY,
    project_id  int NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    serial_no   int NOT NULL,                -- 流水號 (1..N 片)
    stage       text NOT NULL CHECK (stage IN ('cut','pack')),
    scanned_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, serial_no, stage)
);

-- 圖面 / 附件 (設計 PDF、照片)。檔案本體放 files volume，資料表只存中繼資料
CREATE TABLE IF NOT EXISTS attachments (
    id            serial PRIMARY KEY,
    project_id    int NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    filename      text NOT NULL,
    stored_name   text NOT NULL,
    content_type  text,
    size          bigint,
    page_count    int,
    kind          text NOT NULL DEFAULT 'drawing',
    note          text,
    uploaded_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_attachments_project ON attachments(project_id);

ALTER TABLE projects ADD COLUMN IF NOT EXISTS joint_type text;
ALTER TABLE cabinets ADD COLUMN IF NOT EXISTS color_code text;
ALTER TABLE cabinets ADD COLUMN IF NOT EXISTS drawing_attachment_id int REFERENCES attachments(id) ON DELETE SET NULL;
ALTER TABLE cabinets ADD COLUMN IF NOT EXISTS drawing_page int;
ALTER TABLE cabinets ADD COLUMN IF NOT EXISTS drawing_label text;
ALTER TABLE parts    ADD COLUMN IF NOT EXISTS manual_fields text[] NOT NULL DEFAULT '{}';

INSERT INTO status_codes(code, name) VALUES ('A','新增') ON CONFLICT DO NOTHING;

CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS trigger AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_projects_touch ON projects;
CREATE TRIGGER trg_projects_touch BEFORE UPDATE ON projects FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
