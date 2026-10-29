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
-- 1.1.0：回饋可附截圖/檔案；完成時記錄修正版本 (更新通知看板用)
ALTER TABLE feedback ADD COLUMN IF NOT EXISTS resolved_version text;
-- 1.1.0 回饋 #2：櫃身 / 門片分色
ALTER TABLE cabinets ADD COLUMN IF NOT EXISTS door_color_code text;
-- 1.1.0 回饋 #3：櫃體範本 (新增櫃體時依類型產生標準板件；尺寸公式用 H 櫃高 / D 櫃深 / W 櫃寬 / t 板厚)
CREATE TABLE IF NOT EXISTS cabinet_templates (
    id    serial PRIMARY KEY,
    name  text NOT NULL UNIQUE,
    sort  int NOT NULL DEFAULT 0,
    note  text
);
CREATE TABLE IF NOT EXISTS cabinet_template_parts (
    id             serial PRIMARY KEY,
    template_id    int NOT NULL REFERENCES cabinet_templates(id) ON DELETE CASCADE,
    sort           int NOT NULL DEFAULT 0,
    grp            text NOT NULL DEFAULT 'base',   -- base 基本 / inner 內部隔板 (可勾選) / door 門片 (可勾選)
    category       text,
    name           text NOT NULL,
    length_expr    text,
    width_expr     text,
    thickness_expr text DEFAULT 't',
    qty            int NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS feedback_files (
    id           serial PRIMARY KEY,
    feedback_id  int NOT NULL REFERENCES feedback(id) ON DELETE CASCADE,
    filename     text NOT NULL,
    stored_name  text NOT NULL,
    content_type text,
    size         int,
    created_at   timestamptz NOT NULL DEFAULT now()
);
"""


# 預設櫃體範本 (回饋 #3)：基本料 + 依業主可勾選的內部隔板 + 門片；水槽櫃 / 油機吊櫃 結構不同
_BASE = [("base", "桶身", "頂板", "W-2*t", "D"), ("base", "桶身", "底板", "W-2*t", "D"), ("base", "桶身", "左側板", "H", "D"), ("base", "桶身", "右側板", "H", "D"),
         ("base", "桶身", "背板", "H-22", "W-22", "4"), ("base", "桶身", "背拉桿", "W-2*t", "120")]
_INNER = [("inner", "內部", "中立板", "W-2*t", "D-22"), ("inner", "內部", "活隔", "", "D-32"), ("inner", "內部", "固隔", "", "D-22")]
_DOOR = [("door", "外部", "左門板", "", "W/2-4"), ("door", "外部", "右門板", "", "W/2-4")]
DEFAULT_TEMPLATES = [
    ("標準櫃", "頂板、底板、左右側板、背板、背拉桿；勾選內部隔板 (中立板/活隔/固隔) 與門片", _BASE + _INNER + _DOOR),
    ("水槽櫃", "無頂板、無背板，多一片上前立板", [r for r in _BASE if r[2] not in ("頂板", "背板")] + [("base", "桶身", "上前立板", "W-2*t", "100")] + _INNER + _DOOR),
    ("油機吊櫃", "抽油煙機櫃：無底板，上前立板 + 下前立板", [r for r in _BASE if r[2] != "底板"] + [("base", "桶身", "上前立板", "W-2*t", "100"), ("base", "桶身", "下前立板", "W-2*t", "100")] + _INNER + _DOOR),
]


def _seed_templates(c):
    if c.execute("SELECT 1 FROM cabinet_templates LIMIT 1").fetchone():
        return
    for i, (name, note, rows) in enumerate(DEFAULT_TEMPLATES, start=1):
        tid = c.execute("INSERT INTO cabinet_templates(name, sort, note) VALUES (%s,%s,%s) RETURNING id", (name, i, note)).fetchone()["id"]
        for j, r in enumerate(rows, start=1):
            grp, cat, pname, L, W = r[:5]
            T = r[5] if len(r) > 5 else "t"
            c.execute("INSERT INTO cabinet_template_parts(template_id, sort, grp, category, name, length_expr, width_expr, thickness_expr) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                      (tid, j, grp, cat, pname, L or None, W or None, T))


def _seed_lookups(c):
    # 回饋 #5：備註 4 做下拉 (基礎資料 → 下拉清單 → 備註4 可自行增減)
    if not c.execute("SELECT 1 FROM lookup_values WHERE kind='備註4' LIMIT 1").fetchone():
        for i, v in enumerate(["把手", "特殊", "拉門", "玻璃"], start=1):
            c.execute("INSERT INTO lookup_values(kind, value, sort) VALUES ('備註4', %s, %s) ON CONFLICT DO NOTHING", (v, i))


def run():
    with conn() as c:
        c.execute(MIGRATIONS)
        _seed_templates(c)
        _seed_lookups(c)
        c.commit()
