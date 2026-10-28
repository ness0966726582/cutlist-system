"""拆單專案管理系統 API (FastAPI + PostgreSQL)。

路由分組：
  /api/master/*                 基礎資料 (色號 / 單價 / 零件目錄 / 標記 / 下拉清單 / 五金 / 廠商)
  /api/customers                客戶
  /api/projects                 專案 (料單表頭)；/import-xlsx 從既有 Excel 料單匯入
  /api/cabinets                 櫃體 (duplicate / apply-color / drawing)
  /api/parts                    板材 (自動欄位可逐格覆寫，manual_fields 記錄覆寫過的欄位)
  /api/projects/{id}/attachments  圖面附件 (PDF/圖片)，PDF 逐頁縮圖
  /api/projects/{id}/summary | quote | labels | serials | material   報表
"""
import json
import os
import re
import shutil
from contextlib import asynccontextmanager
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

CENT = Decimal("0.01")


def money(v: Decimal) -> Decimal:
    """四捨五入到分，採 Excel 的「五入」(ROUND_HALF_UP)。"""
    return v.quantize(CENT, rounding=ROUND_HALF_UP)

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from urllib.parse import quote

from . import exporter, importer, migrate, rules
from .db import conn, pool, q1, qa

FILES_DIR = os.environ.get("FILES_DIR", "./data/files")


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool.open()
    migrate.run()
    os.makedirs(FILES_DIR, exist_ok=True)
    yield
    pool.close()


app = FastAPI(title="拆單專案管理系統", version="0.3.0", lifespan=lifespan)

from .extras import router as extras_router, edge_spec_for  # noqa: E402

app.include_router(extras_router)


def _json(v):
    return json.dumps(v, ensure_ascii=False)


@app.get("/api/health")
def health():
    with conn() as c:
        q1(c, "SELECT 1")
    return {"ok": True}


# ───────────────────────── 基礎資料 ─────────────────────────
@app.get("/api/master/colors")
def list_colors(q: Optional[str] = None, vendor: Optional[str] = None, limit: int = 100, with_prices: bool = False):
    with conn() as c:
        sql = "SELECT cc.*"
        if with_prices:
            sql += ", (SELECT coalesce(json_object_agg(pr.thickness::text, pr.price), '{}'::json) FROM price_table pr WHERE pr.code=cc.code) AS prices"
        sql += " FROM color_codes cc WHERE 1=1"
        params: list = []
        if q:
            sql += " AND (cc.code ILIKE %s OR cc.board_name ILIKE %s OR cc.edge_code ILIKE %s)"
            params += [f"%{q}%", f"%{q}%", f"%{q}%"]
        if vendor:
            sql += " AND cc.vendor = %s"
            params.append(vendor)
        sql += " ORDER BY cc.code LIMIT %s"
        params.append(limit)
        rows = qa(c, sql, params)
    if with_prices:
        for r in rows:   # numeric 鍵 '18.00' → '18'，前端與 CSV 都用這個寫法
            r["prices"] = {f"{float(k):g}": float(v) for k, v in (r.get("prices") or {}).items()}
    return rows


@app.get("/api/master/thicknesses")
def list_thicknesses():
    """單價表用到的板厚欄 (對應 Excel 單價表 E2:M2)。"""
    with conn() as c:
        return [float(r["thickness"]) for r in qa(c, "SELECT DISTINCT thickness FROM price_table ORDER BY thickness")]


@app.get("/api/master/vendors-list")
def vendor_names():
    with conn() as c:
        return [r["vendor"] for r in qa(c, "SELECT DISTINCT vendor FROM color_codes WHERE vendor IS NOT NULL ORDER BY vendor")]


@app.get("/api/master/colors/{code}")
def get_color(code: str):
    with conn() as c:
        row = q1(c, "SELECT * FROM color_codes WHERE code=%s", (code,))
        if not row:
            raise HTTPException(404, "色號不存在")
        row["prices"] = qa(c, "SELECT thickness, price FROM price_table WHERE code=%s ORDER BY thickness", (code,))
        return row


class ColorIn(BaseModel):
    code: str = Field(min_length=1)
    board_name: Optional[str] = None
    vendor: Optional[str] = None
    edge_code: Optional[str] = None
    series: Optional[str] = None
    prices: dict[str, Optional[float]] = Field(default_factory=dict)   # {"18": 131, "4": null} null = 刪除該板厚單價


def _save_color(c, code: str, body: ColorIn):
    code = code.strip()
    c.execute(
        """INSERT INTO color_codes(code, board_name, vendor, edge_code, series) VALUES (%s,%s,%s,%s,%s)
           ON CONFLICT (code) DO UPDATE SET board_name=EXCLUDED.board_name, vendor=EXCLUDED.vendor,
           edge_code=EXCLUDED.edge_code, series=EXCLUDED.series""",
        (code, (body.board_name or "").strip() or None, (body.vendor or "").strip() or None,
         (body.edge_code or "").strip() or None, (body.series or "").strip() or None))
    for t, p in body.prices.items():
        try:
            th = Decimal(str(t))
        except Exception:  # noqa: BLE001
            raise HTTPException(400, f"板厚「{t}」不是數字")
        if p is None:
            c.execute("DELETE FROM price_table WHERE code=%s AND thickness=%s", (code, th))
        else:
            c.execute("""INSERT INTO price_table(code, thickness, price) VALUES (%s,%s,%s)
                         ON CONFLICT (code, thickness) DO UPDATE SET price=EXCLUDED.price""", (code, th, p))
    return code


@app.put("/api/master/colors/{code}")
def upsert_color(code: str, body: ColorIn):
    with conn() as c:
        code = _save_color(c, code, body)
        c.commit()
    return get_color(code)


@app.post("/api/master/colors", status_code=201)
def create_color(body: ColorIn):
    with conn() as c:
        if q1(c, "SELECT 1 FROM color_codes WHERE code=%s", (body.code.strip(),)):
            raise HTTPException(409, f"色號「{body.code}」已存在")
        code = _save_color(c, body.code, body)
        c.commit()
    return get_color(code)


@app.delete("/api/master/colors/{code}", status_code=204)
def delete_color(code: str):
    with conn() as c:
        used = q1(c, "SELECT count(*) AS n FROM parts WHERE color_code=%s", (code,))["n"]
        if used:
            raise HTTPException(400, f"色號「{code}」仍有 {used} 列板材在使用，不能刪除")
        c.execute("DELETE FROM color_codes WHERE code=%s", (code,))
        c.commit()


@app.get("/api/master/colors-export.csv")
def export_colors_csv():
    """色號 + 各板厚單價，UTF-8 BOM CSV (可用 Excel 開啟修改後再匯入)。"""
    import csv
    import io as _io
    with conn() as c:
        ths = list_thicknesses()
        rows = list_colors(limit=100000, with_prices=True)
    buf = _io.StringIO()
    w = csv.writer(buf)
    w.writerow(["色號", "板名", "廠商", "封邊色號", "系列"] + [f"{t:g}" for t in ths])
    for r in rows:
        pr = r["prices"] or {}
        w.writerow([r["code"], r["board_name"] or "", r["vendor"] or "", r["edge_code"] or "", r["series"] or ""]
                   + [("" if pr.get(f"{t:g}") is None else f"{pr[f'{t:g}']:g}") for t in ths])
    data = ("﻿" + buf.getvalue()).encode("utf-8")
    return Response(data, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=\"colors.csv\"; filename*=UTF-8''%E8%89%B2%E8%99%9F%E5%96%AE%E5%83%B9.csv"})


@app.post("/api/master/colors-import-csv")
async def import_colors_csv(file: UploadFile = File(...)):
    """匯入 colors-export.csv 同格式：前五欄固定，之後每欄標題是板厚。空白單價 = 不變；'-' = 刪除該單價。"""
    import csv
    import io as _io
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.reader(_io.StringIO(raw))
    header = next(reader, None)
    if not header or len(header) < 5:
        raise HTTPException(400, "CSV 第一列需為：色號, 板名, 廠商, 封邊色號, 系列, 板厚…")
    ths = []
    for h in header[5:]:
        try:
            ths.append(Decimal(h.strip()))
        except Exception:  # noqa: BLE001
            raise HTTPException(400, f"板厚欄標題「{h}」不是數字")
    n_rows, n_prices, errors = 0, 0, []
    with conn() as c:
        for i, row in enumerate(reader, start=2):
            if not row or not row[0].strip():
                continue
            row += [""] * (5 + len(ths) - len(row))
            prices: dict[str, Optional[float]] = {}
            for t, v in zip(ths, row[5:]):
                v = v.strip()
                if v == "":
                    continue
                if v == "-":
                    prices[str(t)] = None
                else:
                    try:
                        prices[str(t)] = float(v)
                    except ValueError:
                        errors.append(f"第 {i} 列 板厚 {t} 的單價「{v}」不是數字")
                        continue
                n_prices += 1
            _save_color(c, row[0], ColorIn(code=row[0], board_name=row[1], vendor=row[2], edge_code=row[3], series=row[4], prices=prices))
            n_rows += 1
        c.commit()
    return {"rows": n_rows, "prices": n_prices, "errors": errors[:20]}


def _catalog(c) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for r in qa(c, "SELECT category, name FROM part_catalog ORDER BY category, sort"):
        out.setdefault(r["category"], []).append(r["name"])
    return out


CATEGORY_PRIORITY = ["桶身", "內部", "外部", "抽屜", "抽箱", "抽盤_不見軌道", "床架_臥塌",
                     "內部五金", "外部五金", "抽屜五金", "衣廚五金", "其它五金"]


def _infer_category(catalog: dict[str, list[str]], name: str) -> Optional[str]:
    """類別留空時依板材名稱反查零件目錄；同名出現在多類別時依拆單順序 (桶身 > 內部 > 外部 > 抽屜 …) 取第一個。"""
    hits = [cat for cat, names in catalog.items() if name in names]
    if not hits:
        return None
    hits.sort(key=lambda x: (CATEGORY_PRIORITY.index(x) if x in CATEGORY_PRIORITY else 99, x))
    return hits[0]


def _is_hw_cat(cat) -> bool:
    return (cat or "").endswith("五金")


@app.get("/api/master/parts-catalog")
def parts_catalog():
    with conn() as c:
        return _catalog(c)


class CatalogIn(BaseModel):
    category: str
    name: str


@app.post("/api/master/parts-catalog", status_code=201)
def add_catalog(body: CatalogIn):
    name = body.name.strip()
    with conn() as c:
        cat = _catalog(c)
        if body.category not in cat:
            raise HTTPException(400, f"類別「{body.category}」不存在")
        if name in cat[body.category]:
            raise HTTPException(409, f"「{name}」已在「{body.category}」目錄中")
        c.execute("""INSERT INTO part_catalog(category, name, sort)
                     VALUES (%s,%s,(SELECT coalesce(max(sort),0)+1 FROM part_catalog WHERE category=%s))""",
                  (body.category, name, body.category))
        c.commit()
        return _catalog(c)


@app.get("/api/master/parts-catalog/full")
def parts_catalog_full():
    """含 id 的零件目錄 (維護用)。"""
    with conn() as c:
        rows = qa(c, "SELECT id, category, name, sort FROM part_catalog ORDER BY category, sort")
    out: dict[str, list] = {}
    for r in rows:
        out.setdefault(r["category"], []).append({"id": r["id"], "name": r["name"]})
    return out


@app.delete("/api/master/parts-catalog/{item_id}", status_code=204)
def delete_catalog(item_id: int):
    with conn() as c:
        c.execute("DELETE FROM part_catalog WHERE id=%s", (item_id,))
        c.commit()


class CatalogUpdateIn(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None


@app.put("/api/master/parts-catalog/{item_id}")
def update_catalog(item_id: int, body: CatalogUpdateIn):
    """改名或搬到別的類別。"""
    with conn() as c:
        row = q1(c, "SELECT * FROM part_catalog WHERE id=%s", (item_id,))
        if not row:
            raise HTTPException(404)
        name = (body.name or row["name"]).strip()
        cat = body.category or row["category"]
        if not name:
            raise HTTPException(400, "名稱不可空白")
        if q1(c, "SELECT 1 FROM part_catalog WHERE category=%s AND name=%s AND id<>%s", (cat, name, item_id)):
            raise HTTPException(409, f"「{name}」已在「{cat}」目錄中")
        if cat != row["category"]:
            c.execute("UPDATE part_catalog SET category=%s, name=%s, sort=(SELECT coalesce(max(sort),0)+1 FROM part_catalog WHERE category=%s) WHERE id=%s",
                      (cat, name, cat, item_id))
        else:
            c.execute("UPDATE part_catalog SET name=%s WHERE id=%s", (name, item_id))
        c.commit()
        return q1(c, "SELECT * FROM part_catalog WHERE id=%s", (item_id,))


class MoveIn(BaseModel):
    direction: str  # up | down


@app.post("/api/master/parts-catalog/{item_id}/move")
def move_catalog(item_id: int, body: MoveIn):
    """在同類別內上移 / 下移一格 (交換 sort)。"""
    with conn() as c:
        rows = qa(c, "SELECT id, sort FROM part_catalog WHERE category=(SELECT category FROM part_catalog WHERE id=%s) ORDER BY sort, id", (item_id,))
        ids = [r["id"] for r in rows]
        if item_id not in ids:
            raise HTTPException(404)
        i = ids.index(item_id)
        j = i - 1 if body.direction == "up" else i + 1
        if 0 <= j < len(ids):
            ids[i], ids[j] = ids[j], ids[i]
        for n, pid in enumerate(ids, start=1):   # 重新編 1..N，順便修掉重複的 sort
            c.execute("UPDATE part_catalog SET sort=%s WHERE id=%s", (n, pid))
        c.commit()
    return {"ok": True}


@app.get("/api/master/marks")
def marks():
    with conn() as c:
        return qa(c, "SELECT id, name, code, number FROM marks ORDER BY sort")


class MarkIn(BaseModel):
    name: str = Field(min_length=1)
    code: Optional[str] = None
    number: Optional[float] = None


@app.post("/api/master/marks", status_code=201)
def create_mark(body: MarkIn):
    with conn() as c:
        if q1(c, "SELECT 1 FROM marks WHERE name=%s", (body.name.strip(),)):
            raise HTTPException(409, f"標記「{body.name}」已存在")
        row = q1(c, "INSERT INTO marks(name, code, number, sort) VALUES (%s,%s,%s,(SELECT coalesce(max(sort),0)+1 FROM marks)) RETURNING *",
                 (body.name.strip(), body.code, body.number))
        c.commit()
        return row


@app.put("/api/master/marks/{mid}")
def update_mark(mid: int, body: MarkIn):
    with conn() as c:
        row = q1(c, "UPDATE marks SET name=%s, code=%s, number=%s WHERE id=%s RETURNING *", (body.name.strip(), body.code, body.number, mid))
        if not row:
            raise HTTPException(404)
        c.commit()
        return row


@app.delete("/api/master/marks/{mid}", status_code=204)
def delete_mark(mid: int):
    with conn() as c:
        c.execute("DELETE FROM marks WHERE id=%s", (mid,))
        c.commit()


@app.get("/api/master/lookups")
def lookups():
    with conn() as c:
        rows = qa(c, "SELECT kind, value FROM lookup_values ORDER BY kind, sort")
        status = qa(c, "SELECT code, name FROM status_codes ORDER BY code")
    out: dict[str, list] = {}
    for r in rows:
        out.setdefault(r["kind"], []).append(r["value"])
    out["狀態"] = status
    return out


class LookupIn(BaseModel):
    kind: str = Field(min_length=1)
    value: str = Field(min_length=1)


@app.post("/api/master/lookups", status_code=201)
def add_lookup(body: LookupIn):
    """新增下拉清單值 (板厚 / 設計師 / 基材 / 板材廠商 / 計價單位)。板厚必須是數字。"""
    value = body.value.strip()
    if body.kind == "板厚":
        try:
            f = float(value)
        except ValueError:
            raise HTTPException(400, "板厚必須是數字，例如 18 或 17.5")
        if f <= 0 or f > 200:
            raise HTTPException(400, "板厚範圍 0.1 ~ 200 mm")
        value = str(int(f)) if f.is_integer() else str(f)
    with conn() as c:
        if q1(c, "SELECT 1 FROM lookup_values WHERE kind=%s AND value=%s", (body.kind, value)):
            raise HTTPException(409, f"「{value}」已在清單中")
        c.execute("INSERT INTO lookup_values(kind, value, sort) VALUES (%s,%s,(SELECT coalesce(max(sort),0)+1 FROM lookup_values WHERE kind=%s))",
                  (body.kind, value, body.kind))
        c.commit()
    return lookups()


@app.delete("/api/master/lookups/{kind}/{value}")
def delete_lookup(kind: str, value: str):
    with conn() as c:
        c.execute("DELETE FROM lookup_values WHERE kind=%s AND value=%s", (kind, value))
        c.commit()
    return lookups()


class LookupRenameIn(BaseModel):
    value: str = Field(min_length=1)


@app.put("/api/master/lookups/{kind}/{value}")
def rename_lookup(kind: str, value: str, body: LookupRenameIn):
    new = body.value.strip()
    with conn() as c:
        if not q1(c, "SELECT 1 FROM lookup_values WHERE kind=%s AND value=%s", (kind, value)):
            raise HTTPException(404)
        if new != value and q1(c, "SELECT 1 FROM lookup_values WHERE kind=%s AND value=%s", (kind, new)):
            raise HTTPException(409, f"「{new}」已在清單中")
        c.execute("UPDATE lookup_values SET value=%s WHERE kind=%s AND value=%s", (new, kind, value))
        c.commit()
    return lookups()


class LookupMoveIn(BaseModel):
    kind: str
    value: str
    direction: str


@app.post("/api/master/lookups/move")
def move_lookup(body: LookupMoveIn):
    with conn() as c:
        vals = [r["value"] for r in qa(c, "SELECT value FROM lookup_values WHERE kind=%s ORDER BY sort, value", (body.kind,))]
        if body.value not in vals:
            raise HTTPException(404)
        i = vals.index(body.value)
        j = i - 1 if body.direction == "up" else i + 1
        if 0 <= j < len(vals):
            vals[i], vals[j] = vals[j], vals[i]
        for n, v in enumerate(vals, start=1):
            c.execute("UPDATE lookup_values SET sort=%s WHERE kind=%s AND value=%s", (n, body.kind, v))
        c.commit()
    return lookups()


@app.get("/api/master/hardware")
def hardware(q: Optional[str] = None):
    with conn() as c:
        if q:
            return qa(c, "SELECT * FROM hardware_catalog WHERE product_name ILIKE %s OR model ILIKE %s OR vendor ILIKE %s ORDER BY id", (f"%{q}%", f"%{q}%", f"%{q}%"))
        return qa(c, "SELECT * FROM hardware_catalog ORDER BY id")


class HardwareIn(BaseModel):
    vendor: Optional[str] = None
    product_name: str = Field(min_length=1)
    model: Optional[str] = None
    spec: Optional[str] = None
    purchase_unit: Optional[str] = None
    sales_unit: Optional[str] = None
    list_price: Optional[float] = None
    note: Optional[str] = None


@app.post("/api/master/hardware", status_code=201)
def create_hardware(body: HardwareIn):
    with conn() as c:
        row = q1(c, """INSERT INTO hardware_catalog(vendor,product_name,model,spec,purchase_unit,sales_unit,list_price,note)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                 (body.vendor, body.product_name.strip(), body.model, body.spec, body.purchase_unit, body.sales_unit, body.list_price, body.note))
        c.commit()
        return row


@app.put("/api/master/hardware/{hid}")
def update_hardware(hid: int, body: HardwareIn):
    with conn() as c:
        row = q1(c, """UPDATE hardware_catalog SET vendor=%s,product_name=%s,model=%s,spec=%s,purchase_unit=%s,sales_unit=%s,list_price=%s,note=%s
                       WHERE id=%s RETURNING *""",
                 (body.vendor, body.product_name.strip(), body.model, body.spec, body.purchase_unit, body.sales_unit, body.list_price, body.note, hid))
        if not row:
            raise HTTPException(404)
        c.commit()
        return row


@app.delete("/api/master/hardware/{hid}", status_code=204)
def delete_hardware(hid: int):
    with conn() as c:
        c.execute("DELETE FROM hardware_catalog WHERE id=%s", (hid,))
        c.commit()


@app.get("/api/master/vendors")
def vendors():
    with conn() as c:
        return qa(c, "SELECT * FROM vendors ORDER BY id")


class VendorIn(BaseModel):
    name: str = Field(min_length=1)
    company_name: Optional[str] = None
    tax_id: Optional[str] = None
    address: Optional[str] = None
    factory_address: Optional[str] = None
    phone: Optional[str] = None


@app.post("/api/master/vendors", status_code=201)
def create_vendor(body: VendorIn):
    with conn() as c:
        if q1(c, "SELECT 1 FROM vendors WHERE name=%s", (body.name.strip(),)):
            raise HTTPException(409, f"廠商「{body.name}」已存在")
        row = q1(c, "INSERT INTO vendors(name,company_name,tax_id,address,factory_address,phone) VALUES (%s,%s,%s,%s,%s,%s) RETURNING *",
                 (body.name.strip(), body.company_name, body.tax_id, body.address, body.factory_address, body.phone))
        c.commit()
        return row


@app.put("/api/master/vendors/{vid}")
def update_vendor(vid: int, body: VendorIn):
    with conn() as c:
        row = q1(c, "UPDATE vendors SET name=%s,company_name=%s,tax_id=%s,address=%s,factory_address=%s,phone=%s WHERE id=%s RETURNING *",
                 (body.name.strip(), body.company_name, body.tax_id, body.address, body.factory_address, body.phone, vid))
        if not row:
            raise HTTPException(404)
        c.commit()
        return row


@app.delete("/api/master/vendors/{vid}", status_code=204)
def delete_vendor(vid: int):
    with conn() as c:
        c.execute("DELETE FROM vendors WHERE id=%s", (vid,))
        c.commit()


# ───────────────────────── 客戶 ─────────────────────────
class CustomerIn(BaseModel):
    code: Optional[str] = None
    name: str
    contact_phone: Optional[str] = None
    company_name: Optional[str] = None
    tax_id: Optional[str] = None
    address: Optional[str] = None
    company_phone: Optional[str] = None
    board_discount: Optional[float] = None
    install_discount: Optional[float] = None


@app.get("/api/customers")
def list_customers():
    with conn() as c:
        return qa(c, "SELECT * FROM customers ORDER BY code NULLS LAST, id")


@app.post("/api/customers", status_code=201)
def create_customer(body: CustomerIn):
    with conn() as c:
        row = q1(c, """INSERT INTO customers(code,name,contact_phone,company_name,tax_id,address,company_phone,board_discount,install_discount)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                 (body.code, body.name, body.contact_phone, body.company_name, body.tax_id, body.address,
                  body.company_phone, body.board_discount, body.install_discount))
        c.commit()
        return row


@app.put("/api/customers/{cid}")
def update_customer(cid: int, body: CustomerIn):
    with conn() as c:
        row = q1(c, """UPDATE customers SET code=%s,name=%s,contact_phone=%s,company_name=%s,tax_id=%s,address=%s,
                       company_phone=%s,board_discount=%s,install_discount=%s WHERE id=%s RETURNING *""",
                 (body.code, body.name, body.contact_phone, body.company_name, body.tax_id, body.address,
                  body.company_phone, body.board_discount, body.install_discount, cid))
        if not row:
            raise HTTPException(404)
        c.commit()
        return row


@app.delete("/api/customers/{cid}", status_code=204)
def delete_customer(cid: int):
    with conn() as c:
        n = q1(c, "SELECT count(*) AS n FROM projects WHERE customer_id=%s", (cid,))["n"]
        if n:
            raise HTTPException(400, f"此客戶仍有 {n} 個專案，不能刪除")
        c.execute("DELETE FROM customers WHERE id=%s", (cid,))
        c.commit()


# ───────────────────────── 專案 ─────────────────────────
class ProjectIn(BaseModel):
    site_name: str = Field(min_length=1)
    customer_id: Optional[int] = None
    designer: Optional[str] = None
    order_date: Optional[date] = None
    delivery_date: Optional[date] = None
    delivery_address: Optional[str] = None
    board_thickness: float = 18
    joint_type: Optional[str] = None
    status: str = "draft"
    revision_dates: list[str] = Field(default_factory=list)
    note: Optional[str] = None


def _next_order_no(c, d: date) -> str:
    """料單!C1 = TEXT(訂貨日期,"yyyymmdd") & 流水號(01)。"""
    prefix = d.strftime("%Y%m%d")
    n = q1(c, "SELECT count(*) AS n FROM projects WHERE order_no LIKE %s", (prefix + "%",))["n"]
    while True:
        n += 1
        cand = f"{prefix}{n:02d}"
        if not q1(c, "SELECT 1 FROM projects WHERE order_no=%s", (cand,)):
            return cand


@app.get("/api/projects")
def list_projects(status: Optional[str] = None, q: Optional[str] = None):
    with conn() as c:
        sql = """SELECT p.*, cu.name AS customer_name,
                        (SELECT count(*) FROM cabinets cb WHERE cb.project_id=p.id) AS cabinet_count,
                        (SELECT coalesce(sum(pt.qty),0) FROM parts pt JOIN cabinets cb ON cb.id=pt.cabinet_id
                          WHERE cb.project_id=p.id AND pt.name<>'' AND coalesce(pt.category,'') NOT LIKE '%%五金') AS piece_count,
                        (SELECT count(*) FROM attachments a WHERE a.project_id=p.id) AS attachment_count
                 FROM projects p LEFT JOIN customers cu ON cu.id=p.customer_id WHERE 1=1"""
        params: list = []
        if status:
            sql += " AND p.status=%s"
            params.append(status)
        if q:
            sql += " AND (p.site_name ILIKE %s OR p.order_no ILIKE %s)"
            params += [f"%{q}%", f"%{q}%"]
        sql += " ORDER BY p.order_date DESC, p.id DESC"
        return qa(c, sql, params)


@app.post("/api/projects", status_code=201)
def create_project(body: ProjectIn):
    d = body.order_date or date.today()
    if not body.site_name.strip():
        raise HTTPException(400, "案場名稱不可空白")
    with conn() as c:
        row = q1(c, """INSERT INTO projects(order_no,site_name,customer_id,designer,order_date,delivery_date,delivery_address,
                       board_thickness,joint_type,status,revision_dates,note) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s) RETURNING *""",
                 (_next_order_no(c, d), body.site_name.strip(), body.customer_id, body.designer, d, body.delivery_date, body.delivery_address,
                  body.board_thickness, body.joint_type, body.status, _json(body.revision_dates), body.note))
        c.commit()
        return row


@app.get("/api/projects/{pid}")
def get_project(pid: int):
    with conn() as c:
        p = q1(c, "SELECT p.*, cu.name AS customer_name FROM projects p LEFT JOIN customers cu ON cu.id=p.customer_id WHERE p.id=%s", (pid,))
        if not p:
            raise HTTPException(404, "專案不存在")
        p["cabinets"] = qa(c, "SELECT * FROM cabinets WHERE project_id=%s ORDER BY sort, cabinet_no", (pid,))
        for cb in p["cabinets"]:
            cb["parts"] = _parts_with_calc(c, cb["id"])
        p["attachments"] = qa(c, "SELECT * FROM attachments WHERE project_id=%s ORDER BY id", (pid,))
        return p


@app.put("/api/projects/{pid}")
def update_project(pid: int, body: ProjectIn):
    with conn() as c:
        row = q1(c, """UPDATE projects SET site_name=%s,customer_id=%s,designer=%s,order_date=coalesce(%s,order_date),delivery_date=%s,
                       delivery_address=%s,board_thickness=%s,joint_type=%s,status=%s,revision_dates=%s::jsonb,note=%s WHERE id=%s RETURNING *""",
                 (body.site_name, body.customer_id, body.designer, body.order_date, body.delivery_date, body.delivery_address,
                  body.board_thickness, body.joint_type, body.status, _json(body.revision_dates), body.note, pid))
        if not row:
            raise HTTPException(404)
        c.commit()
        return row


@app.delete("/api/projects/{pid}", status_code=204)
def delete_project(pid: int):
    with conn() as c:
        c.execute("DELETE FROM projects WHERE id=%s", (pid,))
        c.commit()
    shutil.rmtree(os.path.join(FILES_DIR, str(pid)), ignore_errors=True)


@app.post("/api/projects/import-xlsx", status_code=201)
async def import_xlsx(file: UploadFile = File(...)):
    """上傳既有 Excel 料單，建立新專案 (保留 Excel 內手動填寫的封邊/備註)。"""
    data = await file.read()
    try:
        parsed = importer.parse_workbook(data)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"無法解析 Excel：{e}")
    h = parsed["header"]
    with conn() as c:
        catalog = _catalog(c)
        d = h["order_date"] or date.today()
        order_no = h["order_no"] if h["order_no"] and not q1(c, "SELECT 1 FROM projects WHERE order_no=%s", (h["order_no"],)) else _next_order_no(c, d)
        p = q1(c, """INSERT INTO projects(order_no,site_name,designer,order_date,delivery_date,delivery_address,board_thickness,joint_type,note)
                     VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
               (order_no, h["site_name"], h["designer"], d, h["delivery_date"], h["delivery_address"], h["board_thickness"], h["joint_type"],
                f"由 Excel 匯入：{file.filename}"))
        n_parts, n_cabs = 0, 0
        for i, cab in enumerate(parsed["cabinets"], start=1):
            colors = [x["color_code"] for x in cab["parts"] if x["color_code"]]
            default_color = max(set(colors), key=colors.count) if colors else None
            cb = q1(c, """INSERT INTO cabinets(project_id,cabinet_no,name,height,depth,width,batch,note,sort,color_code)
                          VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                    (p["id"], cab["cabinet_no"], cab["name"], cab["height"], cab["depth"], cab["width"], cab["batch"],
                     rules.cabinet_note(cab["name"]), i, default_color))
            n_cabs += 1
            names = [x["name"] for x in cab["parts"]]
            for seq, x in enumerate(cab["parts"], start=1):   # 序號依列順序重編，不信任 Excel C 欄
                cat = x["category"] or _infer_category(catalog, x["name"])
                auto = {
                    "edge_l": rules.edge_l(x["name"]), "edge_w": rules.edge_w(x["name"]),
                    "mark_p": rules.mark_p(x["name"], x["length"], names), "mark_q": rules.mark_q(x["name"]),
                    "mark_r": rules.mark_r(x["name"]), "reminder": rules.reminder(x["name"]),
                }
                manual = [f for f in rules.AUTO_FIELDS if (x[f] or "") != auto[f]]
                c.execute("""INSERT INTO parts(cabinet_id,part_no,seq,category,name,length,edge_l,width,edge_w,thickness,qty,color_code,
                             mark_p,mark_q,mark_r,remark,reminder,manual_fields)
                             VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                          (cb["id"], cab["cabinet_no"] * 1000 + seq, seq, cat, x["name"], x["length"], x["edge_l"], x["width"], x["edge_w"],
                           x["thickness"], x["qty"], x["color_code"], x["mark_p"], x["mark_q"], x["mark_r"], x["remark"], x["reminder"], manual))
                n_parts += 1
        c.commit()
    return {"project_id": p["id"], "order_no": order_no, "cabinets": n_cabs, "parts": n_parts, "warnings": parsed["warnings"]}


@app.get("/api/projects/{pid}/export-xlsx")
def export_xlsx(pid: int):
    """匯出成原 Excel 料單格式 (以空白範本回填，其他分頁公式保留)。"""
    with conn() as c:
        p = q1(c, "SELECT * FROM projects WHERE id=%s", (pid,))
        if not p:
            raise HTTPException(404, "專案不存在")
        cabinets = qa(c, "SELECT * FROM cabinets WHERE project_id=%s ORDER BY sort, cabinet_no", (pid,))
        for cb in cabinets:
            cb["parts"] = [x for x in _parts_with_calc(c, cb["id"]) if x["name"]]
    try:
        data = exporter.build_xlsx(p, cabinets)
    except ValueError as e:
        raise HTTPException(400, str(e))
    fname = f"{p['order_no']} {p['site_name']}.xlsx"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename=\"export.xlsx\"; filename*=UTF-8''{quote(fname)}"})


# ───────────────────────── 櫃體 ─────────────────────────
class CabinetIn(BaseModel):
    name: str = Field(min_length=1)
    cabinet_no: Optional[int] = Field(default=None, ge=1)
    height: Optional[float] = None
    depth: Optional[float] = None
    width: Optional[float] = None
    batch: int = 1
    note: Optional[str] = None
    color_code: Optional[str] = None
    drawing_attachment_id: Optional[int] = None
    drawing_page: Optional[int] = None
    drawing_label: Optional[str] = None
    generate_default_parts: bool = True


@app.post("/api/projects/{pid}/cabinets", status_code=201)
def create_cabinet(pid: int, body: CabinetIn):
    with conn() as c:
        p = q1(c, "SELECT * FROM projects WHERE id=%s", (pid,))
        if not p:
            raise HTTPException(404, "專案不存在")
        mx = q1(c, "SELECT coalesce(max(cabinet_no),0) AS m, coalesce(max(sort),0) AS s FROM cabinets WHERE project_id=%s", (pid,))
        no = body.cabinet_no if body.cabinet_no is not None else mx["m"] + 1
        if q1(c, "SELECT 1 FROM cabinets WHERE project_id=%s AND cabinet_no=%s", (pid, no)):
            raise HTTPException(400, f"櫃號 {no} 已存在，請改用其他櫃號")
        note = body.note if body.note else rules.cabinet_note(body.name)
        cb = q1(c, """INSERT INTO cabinets(project_id,cabinet_no,name,height,depth,width,batch,note,sort,color_code,drawing_attachment_id,drawing_page,drawing_label)
                      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                (pid, no, body.name, body.height, body.depth, body.width, body.batch, note, mx["s"] + 1, body.color_code,
                 body.drawing_attachment_id, body.drawing_page, body.drawing_label))
        if body.generate_default_parts:
            for i, (cat, name, L, W, T) in enumerate(rules.default_parts(body.height, body.depth, body.width, p["board_thickness"]), start=1):
                _insert_part(c, cb["id"], no, i, cat, name, L, W, T, 1, body.color_code, None, "A")
            _recalc_cabinet(c, cb["id"])
        c.commit()
        cb["parts"] = _parts_with_calc(c, cb["id"])
        return cb


@app.get("/api/cabinets/{cid}")
def get_cabinet(cid: int):
    """單一櫃體 + 板材 (前端只重畫這一櫃用)。"""
    with conn() as c:
        cb = q1(c, "SELECT * FROM cabinets WHERE id=%s", (cid,))
        if not cb:
            raise HTTPException(404)
        cb["parts"] = _parts_with_calc(c, cid)
        return cb


@app.put("/api/cabinets/{cid}")
def update_cabinet(cid: int, body: CabinetIn):
    with conn() as c:
        cb = q1(c, "SELECT * FROM cabinets WHERE id=%s", (cid,))
        if not cb:
            raise HTTPException(404)
        no = body.cabinet_no if body.cabinet_no is not None else cb["cabinet_no"]
        if no != cb["cabinet_no"] and q1(c, "SELECT 1 FROM cabinets WHERE project_id=%s AND cabinet_no=%s AND id<>%s", (cb["project_id"], no, cid)):
            raise HTTPException(400, f"櫃號 {no} 已被其他櫃體使用；要對調櫃號請先把另一櫃改成暫時號碼")
        # 備註：使用者留空且櫃名有規則 (水槽櫃/爐台櫃/油機吊櫃) 時自動帶入
        note = body.note if body.note else rules.cabinet_note(body.name)
        row = q1(c, """UPDATE cabinets SET name=%s,cabinet_no=%s,height=%s,depth=%s,width=%s,batch=%s,note=%s,color_code=%s,
                       drawing_attachment_id=%s,drawing_page=%s,drawing_label=%s WHERE id=%s RETURNING *""",
                 (body.name, no, body.height, body.depth, body.width, body.batch, note, body.color_code,
                  body.drawing_attachment_id, body.drawing_page, body.drawing_label, cid))
        if no != cb["cabinet_no"]:
            c.execute("UPDATE parts SET part_no=%s*1000+seq WHERE cabinet_id=%s", (no, cid))
        c.commit()
        row["parts"] = _parts_with_calc(c, cid)
        return row


@app.delete("/api/cabinets/{cid}", status_code=204)
def delete_cabinet(cid: int):
    with conn() as c:
        c.execute("DELETE FROM cabinets WHERE id=%s", (cid,))
        c.commit()


@app.post("/api/cabinets/{cid}/duplicate", status_code=201)
def duplicate_cabinet(cid: int):
    """複製櫃體 (含全部板材與手動覆寫)，櫃號取下一號。"""
    with conn() as c:
        cb = q1(c, "SELECT * FROM cabinets WHERE id=%s", (cid,))
        if not cb:
            raise HTTPException(404)
        mx = q1(c, "SELECT coalesce(max(cabinet_no),0) AS m, coalesce(max(sort),0) AS s FROM cabinets WHERE project_id=%s", (cb["project_id"],))
        no = mx["m"] + 1
        new = q1(c, """INSERT INTO cabinets(project_id,cabinet_no,name,height,depth,width,batch,note,sort,color_code,drawing_attachment_id,drawing_page,drawing_label)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL) RETURNING *""",
                 (cb["project_id"], no, cb["name"], cb["height"], cb["depth"], cb["width"], cb["batch"], cb["note"], mx["s"] + 1, cb["color_code"],
                  cb["drawing_attachment_id"], cb["drawing_page"]))
        c.execute("""INSERT INTO parts(cabinet_id,part_no,seq,category,name,length,edge_l,width,edge_w,thickness,qty,color_code,
                                       mark_p,mark_q,mark_r,remark,reminder,status_code,manual_fields)
                     SELECT %s, %s*1000+seq, seq, category,name,length,edge_l,width,edge_w,thickness,qty,color_code,
                            mark_p,mark_q,mark_r,remark,reminder,status_code,manual_fields FROM parts WHERE cabinet_id=%s""",
                  (new["id"], no, cid))
        c.commit()
        new["parts"] = _parts_with_calc(c, new["id"])
        return new


class ApplyColorIn(BaseModel):
    color_code: Optional[str] = None
    only_empty: bool = False
    skip_backboard: bool = False  # true = 背板 / 抽底 (4mm) 不套用


@app.post("/api/cabinets/{cid}/apply-color")
def apply_color(cid: int, body: ApplyColorIn):
    with conn() as c:
        sql = "UPDATE parts SET color_code=%s WHERE cabinet_id=%s AND coalesce(category,'') NOT LIKE '%%五金'"
        params: list = [body.color_code, cid]
        if body.only_empty:
            sql += " AND color_code IS NULL"
        if body.skip_backboard:
            sql += " AND name <> '背板' AND name <> '抽底'"
        c.execute(sql, params)
        c.execute("UPDATE cabinets SET color_code=%s WHERE id=%s", (body.color_code, cid))
        c.commit()
        return _parts_with_calc(c, cid)


# ───────────────────────── 板材 ─────────────────────────
class PartIn(BaseModel):
    category: Optional[str] = None
    name: str = ""                 # 空字串 = 草稿列 (不進報表 / 匯出 / 流水號)
    length: Optional[float] = None
    width: Optional[float] = None
    thickness: Optional[float] = None
    qty: int = Field(default=1, ge=0)
    color_code: Optional[str] = None
    remark: Optional[str] = None
    status_code: str = "A"
    # 自動欄位：值 + 哪些欄位是手動覆寫 (不在 manual_fields 內的會被規則重算覆蓋)
    edge_l: Optional[str] = None
    edge_w: Optional[str] = None
    mark_p: Optional[str] = None
    mark_q: Optional[str] = None
    mark_r: Optional[str] = None
    reminder: Optional[str] = None
    manual_fields: list[str] = Field(default_factory=list)


def _insert_part(c, cabinet_id, cabinet_no, seq, cat, name, L, W, T, qty, color, remark, status):
    return q1(c, """INSERT INTO parts(cabinet_id,part_no,seq,category,name,length,width,thickness,qty,color_code,remark,status_code)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
              (cabinet_id, cabinet_no * 1000 + seq, seq, cat, name, L, W, T, qty, color, remark, status or "A"))


def _recalc_cabinet(c, cabinet_id):
    """重新套用 G/I/P/Q/R/T 規則；manual_fields 內的欄位保留使用者的值。"""
    parts = qa(c, "SELECT * FROM parts WHERE cabinet_id=%s ORDER BY seq", (cabinet_id,))
    names = [p["name"] for p in parts]
    for p in parts:
        auto = {
            "edge_l": rules.edge_l(p["name"]), "edge_w": rules.edge_w(p["name"]),
            "mark_p": rules.mark_p(p["name"], p["length"], names), "mark_q": rules.mark_q(p["name"]),
            "mark_r": rules.mark_r(p["name"]), "reminder": rules.reminder(p["name"]),
        }
        manual = set(p["manual_fields"] or [])
        sets = {k: v for k, v in auto.items() if k not in manual}
        if sets:
            c.execute("UPDATE parts SET " + ", ".join(f"{k}=%s" for k in sets) + " WHERE id=%s", (*sets.values(), p["id"]))


def _parts_with_calc(c, cabinet_id):
    rows = qa(c, """SELECT pt.*, cc.board_name AS color_name, cc.vendor AS board_vendor, cc.edge_code,
                           pr.price AS unit_price
                    FROM parts pt
                    LEFT JOIN color_codes cc ON cc.code = pt.color_code
                    LEFT JOIN price_table pr ON pr.code = pt.color_code AND pr.thickness = pt.thickness
                    WHERE pt.cabinet_id=%s ORDER BY pt.seq""", (cabinet_id,))
    for r in rows:
        r["area_cai"] = rules.area_cai(r["length"], r["width"], r["qty"])
        r["amount"] = money(r["area_cai"] * r["unit_price"]) if r["area_cai"] is not None and r["unit_price"] is not None else None
    return rows


def _write_part_fields(c, part_id, body: PartIn, catalog, old=None):
    name = body.name.strip()
    cat = body.category
    # 類別：留空 → 反查；名稱改了且舊類別裡沒有這個名稱、但目錄其他類別有 → 重新判斷 (例：桶身列改名成 活隔粒 → 內部五金)
    if not cat or (old and old["name"] != name and name not in catalog.get(cat, []) and _infer_category(catalog, name)):
        cat = _infer_category(catalog, name) or cat
    if body.status_code and not q1(c, "SELECT 1 FROM status_codes WHERE code=%s", (body.status_code,)):
        raise HTTPException(400, f"狀態代碼「{body.status_code}」不存在")
    manual = [f for f in body.manual_fields if f in rules.AUTO_FIELDS]
    c.execute("""UPDATE parts SET category=%s,name=%s,length=%s,width=%s,thickness=%s,qty=%s,color_code=%s,remark=%s,status_code=%s,
                 manual_fields=%s WHERE id=%s""",
              (cat, name, body.length, body.width, body.thickness, body.qty, (body.color_code or "").strip() or None, body.remark,
               body.status_code or "A", manual, part_id))
    for f in manual:
        v = getattr(body, f)
        if f.startswith("edge"):
            v = rules.norm_edge(v)
        c.execute(f"UPDATE parts SET {f}=%s WHERE id=%s", (v or "", part_id))


@app.post("/api/cabinets/{cid}/parts", status_code=201)
def create_part(cid: int, body: PartIn):
    with conn() as c:
        cb = q1(c, "SELECT cb.*, p.board_thickness FROM cabinets cb JOIN projects p ON p.id=cb.project_id WHERE cb.id=%s", (cid,))
        if not cb:
            raise HTTPException(404, "櫃體不存在")
        seq = (q1(c, "SELECT coalesce(max(seq),0) AS m FROM parts WHERE cabinet_id=%s", (cid,))["m"] or 0) + 1
        catalog = _catalog(c)
        cat = body.category or (_infer_category(catalog, body.name.strip()) if body.name.strip() else None)
        hw = _is_hw_cat(cat)
        # 板材列預設：專案板厚、櫃體色號；五金列不給厚度與色號
        if body.thickness is None and not hw:
            body.thickness = float(cb["board_thickness"])
        if not body.color_code and not hw:
            body.color_code = cb["color_code"]
        body.category = cat
        p = _insert_part(c, cid, cb["cabinet_no"], seq, cat, "", None, None, None, body.qty, None, None, "A")
        _write_part_fields(c, p["id"], body, catalog)
        _recalc_cabinet(c, cid)
        c.commit()
        return next(x for x in _parts_with_calc(c, cid) if x["id"] == p["id"])


@app.put("/api/parts/{part_id}")
def update_part(part_id: int, body: PartIn):
    with conn() as c:
        p = q1(c, "SELECT * FROM parts WHERE id=%s", (part_id,))
        if not p:
            raise HTTPException(404)
        _write_part_fields(c, part_id, body, _catalog(c), old=p)
        _recalc_cabinet(c, p["cabinet_id"])
        c.commit()
        return next(x for x in _parts_with_calc(c, p["cabinet_id"]) if x["id"] == part_id)


@app.post("/api/parts/{part_id}/reset-auto")
def reset_auto(part_id: int):
    """清除手動覆寫，恢復規則計算值。"""
    with conn() as c:
        p = q1(c, "UPDATE parts SET manual_fields='{}' WHERE id=%s RETURNING cabinet_id", (part_id,))
        if not p:
            raise HTTPException(404)
        _recalc_cabinet(c, p["cabinet_id"])
        c.commit()
        return next(x for x in _parts_with_calc(c, p["cabinet_id"]) if x["id"] == part_id)


@app.delete("/api/parts/{part_id}", status_code=204)
def delete_part(part_id: int):
    with conn() as c:
        p = q1(c, "DELETE FROM parts WHERE id=%s RETURNING cabinet_id", (part_id,))
        if p:
            _recalc_cabinet(c, p["cabinet_id"])
        c.commit()


# ───────────────────────── 圖面 / 附件 ─────────────────────────
_SAFE = re.compile(r"[^\w.\-一-鿿()（）]+")


def _attachment_path(a) -> str:
    return os.path.join(FILES_DIR, str(a["project_id"]), a["stored_name"])


def _cache_dir(a) -> str:
    d = os.path.join(FILES_DIR, str(a["project_id"]), "cache")
    os.makedirs(d, exist_ok=True)
    return d


@app.get("/api/projects/{pid}/attachments")
def list_attachments(pid: int):
    with conn() as c:
        return qa(c, "SELECT * FROM attachments WHERE project_id=%s ORDER BY id", (pid,))


@app.post("/api/projects/{pid}/attachments", status_code=201)
async def upload_attachment(pid: int, file: UploadFile = File(...), kind: str = "drawing", note: Optional[str] = None):
    """上傳圖面 (PDF / PNG / JPG)。PDF 會記錄頁數，之後可逐頁取得縮圖並把櫃體對應到某一頁。"""
    data = await file.read()
    if not data:
        raise HTTPException(400, "空檔案")
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif"):
        raise HTTPException(400, "只接受 PDF / PNG / JPG / WEBP / GIF")
    page_count = None
    if ext == ".pdf":
        import pymupdf
        try:
            with pymupdf.open(stream=data, filetype="pdf") as doc:
                page_count = len(doc)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(400, f"PDF 無法開啟：{e}")
    else:
        page_count = 1
    with conn() as c:
        if not q1(c, "SELECT 1 FROM projects WHERE id=%s", (pid,)):
            raise HTTPException(404, "專案不存在")
        safe = _SAFE.sub("_", file.filename or f"file{ext}")[:120]
        a = q1(c, """INSERT INTO attachments(project_id, filename, stored_name, content_type, size, page_count, kind, note)
                     VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
               (pid, file.filename, "pending", file.content_type, len(data), page_count, kind, note))
        stored = f"{a['id']}_{safe}"
        c.execute("UPDATE attachments SET stored_name=%s WHERE id=%s", (stored, a["id"]))
        c.commit()
        a["stored_name"] = stored
    os.makedirs(os.path.join(FILES_DIR, str(pid)), exist_ok=True)
    with open(_attachment_path(a), "wb") as f:
        f.write(data)
    return a


@app.get("/api/attachments/{aid}")
def get_attachment(aid: int):
    with conn() as c:
        a = q1(c, "SELECT * FROM attachments WHERE id=%s", (aid,))
    if not a:
        raise HTTPException(404)
    return a


@app.get("/api/attachments/{aid}/file")
def attachment_file(aid: int):
    with conn() as c:
        a = q1(c, "SELECT * FROM attachments WHERE id=%s", (aid,))
    if not a or not os.path.exists(_attachment_path(a)):
        raise HTTPException(404)
    return FileResponse(_attachment_path(a), media_type=a["content_type"] or "application/octet-stream", filename=a["filename"])


@app.get("/api/attachments/{aid}/pages/{page}.png")
def attachment_page(aid: int, page: int, dpi: int = 72):
    """PDF 第 page 頁 (1 起算) 轉 PNG；圖片檔則直接回傳。結果快取在 files volume。"""
    dpi = max(30, min(dpi, 200))
    with conn() as c:
        a = q1(c, "SELECT * FROM attachments WHERE id=%s", (aid,))
    if not a:
        raise HTTPException(404)
    path = _attachment_path(a)
    if not path.lower().endswith(".pdf"):
        return FileResponse(path, media_type=a["content_type"] or "image/png")
    cache = os.path.join(_cache_dir(a), f"{aid}_p{page}_{dpi}.png")
    if not os.path.exists(cache):
        import pymupdf
        with pymupdf.open(path) as doc:
            if page < 1 or page > len(doc):
                raise HTTPException(404, "頁碼超出範圍")
            doc[page - 1].get_pixmap(dpi=dpi).save(cache)
    return FileResponse(cache, media_type="image/png")


class AttachmentIn(BaseModel):
    kind: Optional[str] = None
    note: Optional[str] = None


@app.put("/api/attachments/{aid}")
def update_attachment(aid: int, body: AttachmentIn):
    with conn() as c:
        a = q1(c, "UPDATE attachments SET kind=coalesce(%s,kind), note=%s WHERE id=%s RETURNING *", (body.kind, body.note, aid))
        if not a:
            raise HTTPException(404)
        c.commit()
        return a


@app.delete("/api/attachments/{aid}", status_code=204)
def delete_attachment(aid: int):
    with conn() as c:
        a = q1(c, "DELETE FROM attachments WHERE id=%s RETURNING *", (aid,))
        c.commit()
    if a:
        try:
            os.remove(_attachment_path(a))
        except OSError:
            pass
        cdir = os.path.join(FILES_DIR, str(a["project_id"]), "cache")
        if os.path.isdir(cdir):
            for f in os.listdir(cdir):
                if f.startswith(f"{aid}_p"):
                    os.remove(os.path.join(cdir, f))


# ───────────────────────── 報表 ─────────────────────────
def _all_parts(c, pid):
    """報表用：所有已命名的板材 (空名稱草稿列不算)。"""
    return qa(c, """SELECT pt.*, cb.cabinet_no, cb.name AS cabinet_name, cb.batch AS cabinet_batch,
                           cc.board_name AS color_name, cc.vendor AS board_vendor, cc.edge_code, pr.price AS unit_price
                    FROM parts pt JOIN cabinets cb ON cb.id=pt.cabinet_id
                    LEFT JOIN color_codes cc ON cc.code=pt.color_code
                    LEFT JOIN price_table pr ON pr.code=pt.color_code AND pr.thickness=pt.thickness
                    WHERE cb.project_id=%s AND pt.name<>'' ORDER BY cb.sort, cb.cabinet_no, pt.seq""", (pid,))


def _is_hw(r) -> bool:
    return (r["category"] or "").endswith("五金")


def _line_amount(r):
    """每列金額 = 才數 × 單價，統一四捨五入到分 (統計與計價清單用同一個數)。"""
    cai = rules.area_cai(r["length"], r["width"], r["qty"])
    if cai is None or r["unit_price"] is None:
        return cai, None
    return cai, money(cai * r["unit_price"])


def _sync_serials(c, pid):
    """每片板材固定一個流水號：新片配下一號，刪掉的片號碼作廢不重用，數量減少的多餘片移除。"""
    c.execute("""DELETE FROM piece_serials ps USING parts pt JOIN cabinets cb ON cb.id=pt.cabinet_id
                 WHERE ps.part_id=pt.id AND ps.project_id=%s
                   AND (ps.idx >= pt.qty OR pt.name='' OR coalesce(pt.category,'') LIKE '%%五金')""", (pid,))
    have = {(r["part_id"], r["idx"]) for r in qa(c, "SELECT part_id, idx FROM piece_serials WHERE project_id=%s", (pid,))}
    nxt = (q1(c, "SELECT coalesce(max(serial_no),0) AS m FROM piece_serials WHERE project_id=%s", (pid,))["m"] or 0) + 1
    for r in _all_parts(c, pid):
        if _is_hw(r):
            continue
        for idx in range(r["qty"]):
            if (r["id"], idx) not in have:
                c.execute("INSERT INTO piece_serials(project_id, serial_no, part_id, idx) VALUES (%s,%s,%s,%s)", (pid, nxt, r["id"], idx))
                nxt += 1
    c.commit()


@app.get("/api/projects/{pid}/summary")
def project_summary(pid: int):
    with conn() as c:
        p = q1(c, "SELECT * FROM projects WHERE id=%s", (pid,))
        if not p:
            raise HTTPException(404)
        parts = _all_parts(c, pid)
    per_cab: dict[int, dict] = {}
    total_pieces, total_cai, total_amount = 0, Decimal(0), Decimal(0)
    for r in parts:
        cab = per_cab.setdefault(r["cabinet_no"], {"cabinet_no": r["cabinet_no"], "name": r["cabinet_name"], "pieces": 0, "cai": Decimal(0), "amount": Decimal(0)})
        cai, amt = _line_amount(r)
        cai, amt = cai or Decimal(0), amt or Decimal(0)
        if not _is_hw(r):
            cab["pieces"] += r["qty"]
            total_pieces += r["qty"]
        cab["cai"] += cai
        cab["amount"] += amt
        total_cai += cai
        total_amount += amt
    return {"project": p, "total_pieces": total_pieces, "total_cai": round(total_cai, 2),
            "total_amount": total_amount, "cabinets": list(per_cab.values())}


def quote_calc(pid: int) -> dict:
    """計價清單 (對應 Excel 計價清價)：
    板材牌價小計 × 板材折數 (專案覆寫 > 客戶設定 > 1) = 折後板材金額
    + 加工費 (project_fees) + 安裝 (手填，或 折後板材 × 客戶安裝折數) + 運費 → 5% 稅 → 總金額。"""
    with conn() as c:
        p = q1(c, """SELECT p.*, cu.name AS customer_name, cu.code AS customer_code, cu.address AS customer_address,
                            cu.company_name AS customer_company, cu.tax_id AS customer_tax_id, cu.contact_phone AS customer_phone,
                            cu.board_discount AS customer_board_discount, cu.install_discount AS customer_install_discount
                     FROM projects p LEFT JOIN customers cu ON cu.id=p.customer_id WHERE p.id=%s""", (pid,))
        if not p:
            raise HTTPException(404)
        parts = _all_parts(c, pid)
        fees = qa(c, "SELECT * FROM project_fees WHERE project_id=%s ORDER BY sort, id", (pid,))
        cabs = qa(c, "SELECT * FROM cabinets WHERE project_id=%s ORDER BY sort, cabinet_no", (pid,))
    lines, subtotal = [], Decimal(0)
    per_cab: dict[int, dict] = {}
    for r in parts:
        cai, amt = _line_amount(r)
        if amt:
            subtotal += amt
        cab = per_cab.setdefault(r["cabinet_no"], {"cabinet_no": r["cabinet_no"], "name": r["cabinet_name"], "cai": Decimal(0), "amount": Decimal(0), "pieces": 0})
        cab["cai"] += cai or Decimal(0)
        cab["amount"] += amt or Decimal(0)
        if not _is_hw(r):
            cab["pieces"] += r["qty"]
        lines.append({"part_no": r["part_no"], "cabinet_no": r["cabinet_no"], "cabinet_name": r["cabinet_name"], "name": r["name"],
                      "color_code": r["color_code"], "color_name": r["color_name"], "length": r["length"], "edge_l": r["edge_l"],
                      "width": r["width"], "edge_w": r["edge_w"], "thickness": r["thickness"], "qty": r["qty"],
                      "cai": cai, "unit": "才" if not _is_hw(r) else "個", "unit_price": r["unit_price"], "amount": amt,
                      "marks": [r["mark_p"], r["mark_q"], r["mark_r"], r["remark"]]})
    for cb in cabs:
        if cb["cabinet_no"] in per_cab:
            per_cab[cb["cabinet_no"]]["spec"] = f"H{cb['height'] or '-'} × D{cb['depth'] or '-'} × W{cb['width'] or '-'}"
    disc = p["board_discount"] if p["board_discount"] is not None else p["customer_board_discount"]
    discount = Decimal(str(disc)) if disc not in (None, 0) else Decimal(1)
    boards_net = money(subtotal * discount)
    fee_lines = [{**f, "amount": money(Decimal(str(f["qty"])) * Decimal(str(f["unit_price"])))} for f in fees]
    fees_total = sum((f["amount"] for f in fee_lines), Decimal(0))
    inst_rate = p["customer_install_discount"]
    install = money(boards_net * Decimal(str(inst_rate))) if p["install_auto"] and inst_rate else Decimal(str(p["install"] or 0))
    freight = Decimal(str(p["freight"] or 0))
    taxable = boards_net + fees_total + install + freight
    tax = money(taxable * Decimal("0.05"))
    return {"project": p, "lines": lines, "cabinets": list(per_cab.values()), "subtotal": subtotal, "discount": discount,
            "discount_source": "專案覆寫" if p["board_discount"] is not None else ("客戶設定" if p["customer_board_discount"] else "無折扣"),
            "boards_net": boards_net, "fees": fee_lines, "fees_total": fees_total, "install": install,
            "install_auto": p["install_auto"], "install_rate": inst_rate, "freight": freight,
            "taxable": taxable, "tax": tax, "total": taxable + tax}


@app.get("/api/projects/{pid}/quote")
def project_quote(pid: int):
    return quote_calc(pid)


class QuoteSettingsIn(BaseModel):
    freight: float = 0
    install: float = 0
    install_auto: bool = False
    board_discount: Optional[float] = None
    quote_meta: dict = Field(default_factory=dict)


@app.put("/api/projects/{pid}/quote-settings")
def put_quote_settings(pid: int, body: QuoteSettingsIn):
    with conn() as c:
        row = q1(c, "UPDATE projects SET freight=%s, install=%s, install_auto=%s, board_discount=%s, quote_meta=%s::jsonb WHERE id=%s RETURNING id",
                 (body.freight, body.install, body.install_auto, body.board_discount, _json(body.quote_meta), pid))
        if not row:
            raise HTTPException(404)
        c.commit()
    return quote_calc(pid)


@app.get("/api/projects/{pid}/labels")
def project_labels(pid: int, include_hardware: bool = False):
    with conn() as c:
        p = q1(c, "SELECT * FROM projects WHERE id=%s", (pid,))
        if not p:
            raise HTTPException(404)
        parts = _all_parts(c, pid)
    out, i = [], 0
    for r in parts:
        if _is_hw(r) and not include_hardware:
            continue
        i += 1
        w, x = rules.label_edge_fields(r["edge_l"])
        y, z = rules.label_edge_fields(r["edge_w"])
        out.append({"row": i, "order_no": p["order_no"], "site_name": p["site_name"], "cabinet_no": r["cabinet_no"],
                    "cabinet_name": r["cabinet_name"], "part_no": r["part_no"], "name": r["name"],
                    "length": r["length"], "edge_l": r["edge_l"], "width": r["width"], "edge_w": r["edge_w"],
                    "thickness": r["thickness"], "qty": r["qty"], "vendor": r["board_vendor"], "color_code": r["color_code"],
                    "edge_code": r["edge_code"], "marks": [r["mark_p"], r["mark_q"], r["mark_r"], r["remark"]],
                    "status": r["status_code"], "batch": r["cabinet_batch"], "delivery_date": p["delivery_date"],
                    "joint_type": p["joint_type"],   # 標籤列印版 AB 結合器 (料單 L3)
                    "edge_l_first": w, "edge_l_flag": x, "edge_w_first": y, "edge_w_last": z})
    return out


@app.get("/api/projects/{pid}/serials")
def project_serials(pid: int):
    with conn() as c:
        if not q1(c, "SELECT 1 FROM projects WHERE id=%s", (pid,)):
            raise HTTPException(404)
        _sync_serials(c, pid)
        rows = qa(c, """SELECT ps.serial_no, ps.idx, pt.part_no, pt.name, pt.qty, cb.cabinet_no
                        FROM piece_serials ps JOIN parts pt ON pt.id=ps.part_id JOIN cabinets cb ON cb.id=pt.cabinet_id
                        WHERE ps.project_id=%s ORDER BY ps.serial_no""", (pid,))
        scans = qa(c, "SELECT serial_no, stage FROM scans WHERE project_id=%s", (pid,))
    done = {(s["serial_no"], s["stage"]) for s in scans}
    return [{"serial_no": r["serial_no"], "label": f"{r['part_no']}{r['serial_no']:04d}", "part_no": r["part_no"], "name": r["name"],
             "piece": f"{r['idx'] + 1}/{r['qty']}", "cabinet_no": r["cabinet_no"],
             "cut": (r["serial_no"], "cut") in done, "pack": (r["serial_no"], "pack") in done} for r in rows]


class ScanIn(BaseModel):
    serial_no: int
    stage: str


@app.post("/api/projects/{pid}/scans", status_code=201)
def add_scan(pid: int, body: ScanIn):
    if body.stage not in ("cut", "pack"):
        raise HTTPException(400, "stage 必須是 cut 或 pack")
    with conn() as c:
        if not q1(c, "SELECT 1 FROM projects WHERE id=%s", (pid,)):
            raise HTTPException(404, "專案不存在")
        _sync_serials(c, pid)
        if not q1(c, "SELECT 1 FROM piece_serials WHERE project_id=%s AND serial_no=%s", (pid, body.serial_no)):
            raise HTTPException(400, f"流水號 {body.serial_no} 不存在於此專案")
        row = q1(c, "INSERT INTO scans(project_id, serial_no, stage) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id", (pid, body.serial_no, body.stage))
        c.commit()
    return {"ok": True, "duplicate": row is None}


@app.delete("/api/projects/{pid}/scans/{serial_no}/{stage}", status_code=204)
def delete_scan(pid: int, serial_no: int, stage: str):
    """掃錯了可取消。"""
    with conn() as c:
        c.execute("DELETE FROM scans WHERE project_id=%s AND serial_no=%s AND stage=%s", (pid, serial_no, stage))
        c.commit()


@app.get("/api/projects/{pid}/material")
def project_material(pid: int):
    with conn() as c:
        if not q1(c, "SELECT 1 FROM projects WHERE id=%s", (pid,)):
            raise HTTPException(404)
        parts = _all_parts(c, pid)
        specs = qa(c, "SELECT * FROM edge_band_specs ORDER BY max_thickness")
    agg: dict[str, dict] = {}
    hw: dict[tuple, dict] = {}
    by_color_spec: dict[tuple, dict] = {}   # 色號1~4：每色號 × 封邊條規格 的長度
    for r in parts:
        if _is_hw(r):
            h = hw.setdefault((r["category"], r["name"]), {"name": r["name"], "category": r["category"], "qty": 0})
            h["qty"] += r["qty"]
            continue
        key = f"{r['color_code'] or '-'}|{r['thickness'] or '-'}"
        a = agg.setdefault(key, {"color_code": r["color_code"], "color_name": r["color_name"], "thickness": r["thickness"],
                                 "edge_code": r["edge_code"], "pieces": 0, "cai": Decimal(0), "edge_band_mm": Decimal(0)})
        a["pieces"] += r["qty"]
        a["cai"] += rules.area_cai(r["length"], r["width"], r["qty"]) or Decimal(0)
        if r["length"] is not None and r["width"] is not None:
            # 封邊條長度：有封邊的邊才計 (AA = 兩邊, A = 一邊)
            n_l = len(rules.norm_edge(r["edge_l"]))
            n_w = len(rules.norm_edge(r["edge_w"]))
            mm = (Decimal(r["length"]) * n_l + Decimal(r["width"]) * n_w) * r["qty"]
            a["edge_band_mm"] += mm
            if mm:
                spec = edge_spec_for(specs, r["thickness"])
                k2 = (r["color_code"] or "-", spec)
                e = by_color_spec.setdefault(k2, {"color_code": r["color_code"], "color_name": r["color_name"], "edge_code": r["edge_code"], "spec": spec, "edge_band_mm": Decimal(0), "pieces": 0})
                e["edge_band_mm"] += mm
                e["pieces"] += r["qty"]
    return {"boards": list(agg.values()), "hardware": sorted(hw.values(), key=lambda x: (x["category"] or "", x["name"])),
            "edge_bands": sorted(by_color_spec.values(), key=lambda x: (x["color_code"] or "", x["spec"])),
            "edge_specs": specs}
