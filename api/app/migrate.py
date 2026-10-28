"""Idempotent schema updates applied at API startup (existing volumes don't re-run db/init)."""
from .db import conn

MIGRATIONS = """
CREATE TABLE IF NOT EXISTS attachments (
    id            serial PRIMARY KEY,
    project_id    int NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    filename      text NOT NULL,
    stored_name   text NOT NULL,
    content_type  text,
    size          bigint,
    page_count    int,
    kind          text NOT NULL DEFAULT 'drawing',   -- drawing / photo / other
    note          text,
    uploaded_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_attachments_project ON attachments(project_id);

ALTER TABLE projects ADD COLUMN IF NOT EXISTS joint_type text;                 -- 料單 L3 (拉 / KD)
ALTER TABLE cabinets ADD COLUMN IF NOT EXISTS color_code text;                 -- 櫃體預設色號
ALTER TABLE cabinets ADD COLUMN IF NOT EXISTS drawing_attachment_id int REFERENCES attachments(id) ON DELETE SET NULL;
ALTER TABLE cabinets ADD COLUMN IF NOT EXISTS drawing_page int;
ALTER TABLE cabinets ADD COLUMN IF NOT EXISTS drawing_label text;              -- 圖面上的編號 (①②…)
ALTER TABLE parts    ADD COLUMN IF NOT EXISTS manual_fields text[] NOT NULL DEFAULT '{}';  -- 使用者覆寫過的自動欄位

-- 流水號固定配給每一片 (part + 第幾片)，之後增刪板材不會讓既有流水號位移；掃描紀錄以此為準
CREATE TABLE IF NOT EXISTS piece_serials (
    project_id  int NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    serial_no   int NOT NULL,
    part_id     int NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
    idx         int NOT NULL,
    PRIMARY KEY (project_id, serial_no),
    UNIQUE (part_id, idx)
);

-- 常用板厚 (操作者可在基礎資料頁增減)
INSERT INTO lookup_values(kind, value, sort) VALUES ('板厚','18',1), ('板厚','17.5',2) ON CONFLICT DO NOTHING;

-- 加工 / 五金牌價 (資料庫 AC~AL)
CREATE TABLE IF NOT EXISTS process_prices (
    id     serial PRIMARY KEY,
    kind   text NOT NULL,            -- 門板加工 / 五金配件牌價 / 特殊加工板材
    name   text NOT NULL,
    spec   text,
    unit   text,
    price  numeric(12,2),
    note   text,
    sort   int NOT NULL DEFAULT 0,
    UNIQUE (kind, name)
);
-- 專案加工費 / 額外費用 (計價清單用)
CREATE TABLE IF NOT EXISTS project_fees (
    id          serial PRIMARY KEY,
    project_id  int NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name        text NOT NULL,
    unit        text,
    qty         numeric(12,2) NOT NULL DEFAULT 1,
    unit_price  numeric(12,2) NOT NULL DEFAULT 0,
    note        text,
    sort        int NOT NULL DEFAULT 0
);
-- 計價參數存在專案上
ALTER TABLE projects ADD COLUMN IF NOT EXISTS freight numeric(12,2) NOT NULL DEFAULT 0;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS install numeric(12,2) NOT NULL DEFAULT 0;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS install_auto boolean NOT NULL DEFAULT false;   -- true: 安裝 = 折後板材金額 × 客戶安裝折數
ALTER TABLE projects ADD COLUMN IF NOT EXISTS board_discount numeric(6,3);                    -- 覆寫客戶板材折數 (NULL = 用客戶的)
ALTER TABLE projects ADD COLUMN IF NOT EXISTS quote_meta jsonb NOT NULL DEFAULT '{}';         -- 報價單欄位 (聯絡人、電話、施工類別、進場日…)
-- 封邊條規格 (依板厚)
CREATE TABLE IF NOT EXISTS edge_band_specs (
    id             serial PRIMARY KEY,
    max_thickness  numeric(6,2) NOT NULL,
    spec           text NOT NULL,
    sort           int NOT NULL DEFAULT 0
);
INSERT INTO edge_band_specs(max_thickness, spec, sort)
SELECT * FROM (VALUES (6, '2分', 1), (19, '封邊條22*1', 2), (26, '封邊條29*1', 3), (999, '麻雙', 4)) v(m, s, o)
WHERE NOT EXISTS (SELECT 1 FROM edge_band_specs);
-- 五金進銷貨紀錄
CREATE TABLE IF NOT EXISTS hardware_txns (
    id           serial PRIMARY KEY,
    hardware_id  int NOT NULL REFERENCES hardware_catalog(id) ON DELETE CASCADE,
    kind         text NOT NULL CHECK (kind IN ('in','out','return_in','return_out')),  -- 進貨 / 銷貨 / 進貨退回 / 銷貨退回
    txn_date     date NOT NULL DEFAULT CURRENT_DATE,
    qty          numeric(12,2) NOT NULL,
    amount       numeric(12,2),
    voucher_no   text,
    site         text,
    note         text
);
-- 櫃體牌價表 (牌價表(對公司內部))
CREATE TABLE IF NOT EXISTS cabinet_prices (
    id                     serial PRIMARY KEY,
    seq                    numeric,
    name                   text NOT NULL,
    spec                   text,
    factor                 numeric(8,3),      -- D 係數 (1.05 = 含稅)
    base_price             numeric(12,2),     -- E 底價
    sell_price             numeric(12,2),     -- F 賣價(完稅)；NULL = 底價×係數
    designer_discount      numeric(6,3),      -- G 業務&設計師板材折數
    discount2              numeric(6,3),      -- H
    employee_discount_draw numeric(6,3),      -- I 員工自用(含製圖3%)
    employee_discount      numeric(6,3),      -- J 員工自用
    install_per_cm         numeric(12,2),     -- P 安裝單價/公分
    sort                   int NOT NULL DEFAULT 0
);
-- 板材成本分析 (20230916成本分析)
CREATE TABLE IF NOT EXISTS cost_analysis (
    id              serial PRIMARY KEY,
    vendor          text, series text, color_code text, spec text, base_material text, face text,
    list_cost       numeric(12,2),   -- K 進貨成本牌價
    net_cost        numeric(12,2),   -- L 進貨成本(未稅) NULL = 用牌價
    full_cai        numeric(8,2),    -- N 滿板材數
    usable_cai      numeric(8,2),    -- O 預估可用材數
    edge_m_per_cai  numeric(8,3),    -- R 每材封邊條公尺
    edge_cost       numeric(8,2),    -- S 封邊條成本/元
    margin          numeric(12,2),   -- V 毛利(元)
    sort            int NOT NULL DEFAULT 0
);
-- 公司資料 (報價單 / 對帳單表頭)
CREATE TABLE IF NOT EXISTS settings (key text PRIMARY KEY, value text);

-- 操作者意見回饋
CREATE TABLE IF NOT EXISTS feedback (
    id          serial PRIMARY KEY,
    category    text NOT NULL DEFAULT 'bug',        -- bug 問題 / feature 需求 / question 疑問 / other
    message     text NOT NULL,
    reporter    text,
    page        text,                               -- 送出時所在頁面 (hash)
    context     text,                               -- 專案編號 / 櫃號等自動帶入的脈絡
    version     text,
    status      text NOT NULL DEFAULT 'new',        -- new 新 / planned 已排程 / done 已完成 / rejected 不處理
    admin_note  text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
"""


def run():
    with conn() as c:
        c.execute(MIGRATIONS)
        c.commit()
