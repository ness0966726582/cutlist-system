"""補齊 Excel 其餘分頁：加工牌價、專案加工費、封邊條規格、五金進銷貨、客戶對帳單、牌價表、成本分析、公司資料、零件單。"""
import calendar
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .db import conn, q1, qa

router = APIRouter(prefix="/api")

D = Decimal


def dec(v, default=None):
    return D(str(v)) if v is not None else default


def r2(v):
    from decimal import ROUND_HALF_UP
    return v.quantize(D("0.01"), rounding=ROUND_HALF_UP) if isinstance(v, D) else v


# ───────────────────────── 加工 / 五金牌價 ─────────────────────────
class ProcessPriceIn(BaseModel):
    kind: str = Field(min_length=1)
    name: str = Field(min_length=1)
    spec: Optional[str] = None
    unit: Optional[str] = None
    price: Optional[float] = None
    note: Optional[str] = None


@router.get("/master/process-prices")
def list_process_prices(kind: Optional[str] = None):
    with conn() as c:
        if kind:
            return qa(c, "SELECT * FROM process_prices WHERE kind=%s ORDER BY sort, id", (kind,))
        return qa(c, "SELECT * FROM process_prices ORDER BY kind, sort, id")


@router.post("/master/process-prices", status_code=201)
def create_process_price(body: ProcessPriceIn):
    with conn() as c:
        if q1(c, "SELECT 1 FROM process_prices WHERE kind=%s AND name=%s", (body.kind, body.name.strip())):
            raise HTTPException(409, f"「{body.name}」已在「{body.kind}」中")
        row = q1(c, """INSERT INTO process_prices(kind,name,spec,unit,price,note,sort)
                       VALUES (%s,%s,%s,%s,%s,%s,(SELECT coalesce(max(sort),0)+1 FROM process_prices WHERE kind=%s)) RETURNING *""",
                 (body.kind, body.name.strip(), body.spec, body.unit, body.price, body.note, body.kind))
        c.commit()
        return row


@router.put("/master/process-prices/{pid}")
def update_process_price(pid: int, body: ProcessPriceIn):
    with conn() as c:
        row = q1(c, "UPDATE process_prices SET kind=%s,name=%s,spec=%s,unit=%s,price=%s,note=%s WHERE id=%s RETURNING *",
                 (body.kind, body.name.strip(), body.spec, body.unit, body.price, body.note, pid))
        if not row:
            raise HTTPException(404)
        c.commit()
        return row


@router.delete("/master/process-prices/{pid}", status_code=204)
def delete_process_price(pid: int):
    with conn() as c:
        c.execute("DELETE FROM process_prices WHERE id=%s", (pid,))
        c.commit()


# ───────────────────────── 專案加工費 ─────────────────────────
class FeeIn(BaseModel):
    name: str = Field(min_length=1)
    unit: Optional[str] = None
    qty: float = 1
    unit_price: float = 0
    note: Optional[str] = None


@router.get("/projects/{pid}/fees")
def list_fees(pid: int):
    with conn() as c:
        return qa(c, "SELECT * FROM project_fees WHERE project_id=%s ORDER BY sort, id", (pid,))


@router.post("/projects/{pid}/fees", status_code=201)
def create_fee(pid: int, body: FeeIn):
    with conn() as c:
        if not q1(c, "SELECT 1 FROM projects WHERE id=%s", (pid,)):
            raise HTTPException(404)
        row = q1(c, """INSERT INTO project_fees(project_id,name,unit,qty,unit_price,note,sort)
                       VALUES (%s,%s,%s,%s,%s,%s,(SELECT coalesce(max(sort),0)+1 FROM project_fees WHERE project_id=%s)) RETURNING *""",
                 (pid, body.name.strip(), body.unit, body.qty, body.unit_price, body.note, pid))
        c.commit()
        return row


@router.put("/fees/{fid}")
def update_fee(fid: int, body: FeeIn):
    with conn() as c:
        row = q1(c, "UPDATE project_fees SET name=%s,unit=%s,qty=%s,unit_price=%s,note=%s WHERE id=%s RETURNING *",
                 (body.name.strip(), body.unit, body.qty, body.unit_price, body.note, fid))
        if not row:
            raise HTTPException(404)
        c.commit()
        return row


@router.delete("/fees/{fid}", status_code=204)
def delete_fee(fid: int):
    with conn() as c:
        c.execute("DELETE FROM project_fees WHERE id=%s", (fid,))
        c.commit()


# 料單備註關鍵字 → 加工牌價項目；數量依單位推算 (公分 = 板寬/10、才 = 才數、孔/個 = 片數)
FEE_RULES = [
    (("斜把", "上斜", "下斜", "側斜"), "斜把"),
    (("打型",), "打型"),
    (("Z把", "Z 把", " Z"), "Z把"),
    (("崁", "埋入"), "埋入式把手"),
]


@router.post("/projects/{pid}/fees/suggest")
def suggest_fees(pid: int):
    """依料單備註自動帶入加工費建議 (已存在同名費用則略過)。"""
    with conn() as c:
        parts = qa(c, """SELECT pt.* FROM parts pt JOIN cabinets cb ON cb.id=pt.cabinet_id WHERE cb.project_id=%s AND pt.name<>''""", (pid,))
        prices = qa(c, "SELECT * FROM process_prices WHERE kind='門板加工' ORDER BY sort")
        existing = {r["name"] for r in qa(c, "SELECT name FROM project_fees WHERE project_id=%s", (pid,))}
        added = []
        for keys, pname in FEE_RULES:
            pp = next((p for p in prices if pname in p["name"]), None)
            if not pp or pp["name"] in existing:
                continue
            qty = D(0)
            hit = 0
            for x in parts:
                text = " ".join(str(x[k] or "") for k in ("mark_p", "mark_q", "mark_r", "remark"))
                if not any(k in text for k in keys):
                    continue
                hit += 1
                u = pp["unit"] or ""
                if u == "公分":
                    qty += (dec(x["width"], D(0)) / 10) * x["qty"]
                elif u == "才":
                    if x["length"] and x["width"]:
                        qty += dec(x["length"]) * dec(x["width"]) / D(90000) * x["qty"]
                else:
                    qty += D(x["qty"])
            if hit:
                row = q1(c, """INSERT INTO project_fees(project_id,name,unit,qty,unit_price,note,sort)
                               VALUES (%s,%s,%s,%s,%s,%s,(SELECT coalesce(max(sort),0)+1 FROM project_fees WHERE project_id=%s)) RETURNING *""",
                         (pid, pp["name"], pp["unit"], r2(qty), pp["price"] or 0, f"依料單備註自動帶入（{hit} 列），請核對數量", pid))
                added.append(row)
        c.commit()
    return {"added": added}


# ───────────────────────── 封邊條規格 ─────────────────────────
class EdgeSpecIn(BaseModel):
    max_thickness: float
    spec: str = Field(min_length=1)


@router.get("/master/edge-specs")
def list_edge_specs():
    with conn() as c:
        return qa(c, "SELECT * FROM edge_band_specs ORDER BY max_thickness")


@router.post("/master/edge-specs", status_code=201)
def create_edge_spec(body: EdgeSpecIn):
    with conn() as c:
        row = q1(c, "INSERT INTO edge_band_specs(max_thickness, spec) VALUES (%s,%s) RETURNING *", (body.max_thickness, body.spec.strip()))
        c.commit()
        return row


@router.put("/master/edge-specs/{sid}")
def update_edge_spec(sid: int, body: EdgeSpecIn):
    with conn() as c:
        row = q1(c, "UPDATE edge_band_specs SET max_thickness=%s, spec=%s WHERE id=%s RETURNING *", (body.max_thickness, body.spec.strip(), sid))
        if not row:
            raise HTTPException(404)
        c.commit()
        return row


@router.delete("/master/edge-specs/{sid}", status_code=204)
def delete_edge_spec(sid: int):
    with conn() as c:
        c.execute("DELETE FROM edge_band_specs WHERE id=%s", (sid,))
        c.commit()


def edge_spec_for(specs, thickness) -> str:
    if thickness is None:
        return "未分類"
    for s in specs:
        if D(str(thickness)) <= s["max_thickness"]:
            return s["spec"]
    return "其他"


# ───────────────────────── 五金進銷貨 ─────────────────────────
class TxnIn(BaseModel):
    kind: str
    txn_date: Optional[date] = None
    qty: float
    amount: Optional[float] = None
    voucher_no: Optional[str] = None
    site: Optional[str] = None
    note: Optional[str] = None


SIGN = {"in": 1, "return_out": 1, "out": -1, "return_in": -1}


@router.get("/master/hardware/{hid}/txns")
def list_txns(hid: int):
    with conn() as c:
        rows = qa(c, "SELECT * FROM hardware_txns WHERE hardware_id=%s ORDER BY txn_date DESC, id DESC", (hid,))
    stock = sum(SIGN[r["kind"]] * r["qty"] for r in rows)
    return {"stock": stock, "txns": rows}


@router.get("/master/hardware-stock")
def hardware_stock():
    """每個五金的現有庫存 (進 - 銷 + 銷退 - 進退)。"""
    with conn() as c:
        rows = qa(c, """SELECT hardware_id, sum(CASE WHEN kind IN ('in','return_out') THEN qty ELSE -qty END) AS stock
                        FROM hardware_txns GROUP BY hardware_id""")
    return {r["hardware_id"]: r["stock"] for r in rows}


@router.post("/master/hardware/{hid}/txns", status_code=201)
def create_txn(hid: int, body: TxnIn):
    if body.kind not in SIGN:
        raise HTTPException(400, "kind 必須是 in / out / return_in / return_out")
    with conn() as c:
        if not q1(c, "SELECT 1 FROM hardware_catalog WHERE id=%s", (hid,)):
            raise HTTPException(404)
        row = q1(c, """INSERT INTO hardware_txns(hardware_id,kind,txn_date,qty,amount,voucher_no,site,note)
                       VALUES (%s,%s,coalesce(%s,CURRENT_DATE),%s,%s,%s,%s,%s) RETURNING *""",
                 (hid, body.kind, body.txn_date, body.qty, body.amount, body.voucher_no, body.site, body.note))
        c.commit()
        return row


@router.delete("/master/hardware-txns/{tid}", status_code=204)
def delete_txn(tid: int):
    with conn() as c:
        c.execute("DELETE FROM hardware_txns WHERE id=%s", (tid,))
        c.commit()


# ───────────────────────── 牌價表 ─────────────────────────
class CabinetPriceIn(BaseModel):
    seq: Optional[float] = None
    name: str = Field(min_length=1)
    spec: Optional[str] = None
    factor: Optional[float] = 1.05
    base_price: Optional[float] = None
    sell_price: Optional[float] = None
    designer_discount: Optional[float] = None
    discount2: Optional[float] = None
    employee_discount_draw: Optional[float] = None
    employee_discount: Optional[float] = None
    install_per_cm: Optional[float] = None


def _cabinet_price_calc(r):
    """牌價表公式：F=E×D(或手填), K=F×G, L=K×1.2, M=F×I, N=M×1.2, O=F×J。"""
    sell = r["sell_price"] if r["sell_price"] is not None else (r["base_price"] * r["factor"] if r["base_price"] is not None and r["factor"] is not None else None)
    r["sell_calc"] = r2(sell) if sell is not None else None
    g, i, j = r["designer_discount"], r["employee_discount_draw"], r["employee_discount"]
    r["designer_price"] = r2(sell * g) if sell is not None and g is not None else None            # K
    r["designer_price_install"] = r2(r["designer_price"] * D("1.2")) if r["designer_price"] is not None else None  # L
    r["employee_price_draw"] = r2(sell * i) if sell is not None and i is not None else None       # M
    r["employee_price_draw_install"] = r2(r["employee_price_draw"] * D("1.2")) if r["employee_price_draw"] is not None else None  # N
    r["employee_price"] = r2(sell * j) if sell is not None and j is not None else None            # O
    return r


@router.get("/master/cabinet-prices")
def list_cabinet_prices():
    with conn() as c:
        return [_cabinet_price_calc(r) for r in qa(c, "SELECT * FROM cabinet_prices ORDER BY sort, id")]


@router.post("/master/cabinet-prices", status_code=201)
def create_cabinet_price(body: CabinetPriceIn):
    with conn() as c:
        row = q1(c, """INSERT INTO cabinet_prices(seq,name,spec,factor,base_price,sell_price,designer_discount,discount2,employee_discount_draw,employee_discount,install_per_cm,sort)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,(SELECT coalesce(max(sort),0)+1 FROM cabinet_prices)) RETURNING *""",
                 (body.seq, body.name.strip(), body.spec, body.factor, body.base_price, body.sell_price, body.designer_discount, body.discount2,
                  body.employee_discount_draw, body.employee_discount, body.install_per_cm))
        c.commit()
        return _cabinet_price_calc(row)


@router.put("/master/cabinet-prices/{cid}")
def update_cabinet_price(cid: int, body: CabinetPriceIn):
    with conn() as c:
        row = q1(c, """UPDATE cabinet_prices SET seq=%s,name=%s,spec=%s,factor=%s,base_price=%s,sell_price=%s,designer_discount=%s,discount2=%s,
                       employee_discount_draw=%s,employee_discount=%s,install_per_cm=%s WHERE id=%s RETURNING *""",
                 (body.seq, body.name.strip(), body.spec, body.factor, body.base_price, body.sell_price, body.designer_discount, body.discount2,
                  body.employee_discount_draw, body.employee_discount, body.install_per_cm, cid))
        if not row:
            raise HTTPException(404)
        c.commit()
        return _cabinet_price_calc(row)


@router.delete("/master/cabinet-prices/{cid}", status_code=204)
def delete_cabinet_price(cid: int):
    with conn() as c:
        c.execute("DELETE FROM cabinet_prices WHERE id=%s", (cid,))
        c.commit()


# ───────────────────────── 成本分析 ─────────────────────────
class CostIn(BaseModel):
    vendor: Optional[str] = None
    series: Optional[str] = None
    color_code: Optional[str] = None
    spec: Optional[str] = None
    base_material: Optional[str] = None
    face: Optional[str] = None
    list_cost: Optional[float] = None
    net_cost: Optional[float] = None
    full_cai: Optional[float] = 32
    usable_cai: Optional[float] = 26
    edge_m_per_cai: Optional[float] = 1.2
    edge_cost: Optional[float] = None
    margin: Optional[float] = None


def _cost_calc(r):
    """成本分析公式：M=(L或K)×1.05, P=M/N, Q=M/O, T=S×R, U=T+Q, X=U+V, W=V/X, Y=X×1.05。"""
    base = r["net_cost"] if r["net_cost"] is not None else r["list_cost"]
    taxed = base * D("1.05") if base is not None else None
    r["taxed_cost"] = r2(taxed)
    r["per_cai"] = r2(taxed / r["full_cai"]) if taxed is not None and r["full_cai"] else None
    r["per_cai_loss"] = r2(taxed / r["usable_cai"]) if taxed is not None and r["usable_cai"] else None
    edge_total = (r["edge_m_per_cai"] or D(0)) * (r["edge_cost"] or D(0))
    r["edge_total"] = r2(edge_total)
    make = (r["per_cai_loss"] or D(0)) + edge_total
    r["make_cost"] = r2(make)
    margin = r["margin"] or D(0)
    price_net = make + margin
    r["price_net"] = r2(price_net)
    r["margin_rate"] = r2(margin / price_net * 100) if price_net else None
    r["price_taxed"] = r2(price_net * D("1.05"))
    return r


@router.get("/master/cost-analysis")
def list_costs():
    with conn() as c:
        return [_cost_calc(r) for r in qa(c, "SELECT * FROM cost_analysis ORDER BY sort, id")]


@router.post("/master/cost-analysis", status_code=201)
def create_cost(body: CostIn):
    with conn() as c:
        row = q1(c, """INSERT INTO cost_analysis(vendor,series,color_code,spec,base_material,face,list_cost,net_cost,full_cai,usable_cai,edge_m_per_cai,edge_cost,margin,sort)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,(SELECT coalesce(max(sort),0)+1 FROM cost_analysis)) RETURNING *""",
                 (body.vendor, body.series, body.color_code, body.spec, body.base_material, body.face, body.list_cost, body.net_cost,
                  body.full_cai, body.usable_cai, body.edge_m_per_cai, body.edge_cost, body.margin))
        c.commit()
        return _cost_calc(row)


@router.put("/master/cost-analysis/{cid}")
def update_cost(cid: int, body: CostIn):
    with conn() as c:
        row = q1(c, """UPDATE cost_analysis SET vendor=%s,series=%s,color_code=%s,spec=%s,base_material=%s,face=%s,list_cost=%s,net_cost=%s,
                       full_cai=%s,usable_cai=%s,edge_m_per_cai=%s,edge_cost=%s,margin=%s WHERE id=%s RETURNING *""",
                 (body.vendor, body.series, body.color_code, body.spec, body.base_material, body.face, body.list_cost, body.net_cost,
                  body.full_cai, body.usable_cai, body.edge_m_per_cai, body.edge_cost, body.margin, cid))
        if not row:
            raise HTTPException(404)
        c.commit()
        return _cost_calc(row)


@router.delete("/master/cost-analysis/{cid}", status_code=204)
def delete_cost(cid: int):
    with conn() as c:
        c.execute("DELETE FROM cost_analysis WHERE id=%s", (cid,))
        c.commit()


# ───────────────────────── 公司資料 (設定) ─────────────────────────
SETTING_KEYS = ["company_name", "company_address", "company_phone", "company_tax_id", "bank_info", "quote_terms", "statement_note"]


@router.get("/settings")
def get_settings():
    with conn() as c:
        rows = qa(c, "SELECT key, value FROM settings")
    out = {k: "" for k in SETTING_KEYS}
    out.update({r["key"]: r["value"] or "" for r in rows})
    return out


@router.put("/settings")
def put_settings(body: dict[str, Optional[str]]):
    with conn() as c:
        for k, v in body.items():
            if k in SETTING_KEYS:
                c.execute("INSERT INTO settings(key,value) VALUES (%s,%s) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value", (k, v))
        c.commit()
    return get_settings()


# ───────────────────────── 版本 / 更新紀錄 / 意見回饋 ─────────────────────────
import os as _os

_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))


def _read(name: str) -> str:
    for p in (_os.path.join(_ROOT, name), _os.path.join(_ROOT, "..", name)):
        if _os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return f.read()
    return ""


@router.get("/version")
def version():
    return {"version": _read("VERSION").strip() or "dev"}


@router.get("/changelog")
def changelog():
    return {"markdown": _read("CHANGELOG.md")}


class FeedbackIn(BaseModel):
    category: str = "bug"
    message: str = Field(min_length=2)
    reporter: Optional[str] = None
    page: Optional[str] = None
    context: Optional[str] = None


class FeedbackUpdate(BaseModel):
    status: Optional[str] = None
    admin_note: Optional[str] = None
    category: Optional[str] = None


FEEDBACK_STATUS = ("new", "planned", "done", "rejected")
FEEDBACK_CATEGORY = ("bug", "feature", "question", "other")


@router.post("/feedback", status_code=201)
def create_feedback(body: FeedbackIn):
    if body.category not in FEEDBACK_CATEGORY:
        raise HTTPException(400, "category 需為 bug / feature / question / other")
    with conn() as c:
        row = q1(c, """INSERT INTO feedback(category,message,reporter,page,context,version) VALUES (%s,%s,%s,%s,%s,%s) RETURNING *""",
                 (body.category, body.message.strip(), (body.reporter or "").strip() or None, body.page, body.context, _read("VERSION").strip() or None))
        c.commit()
        return row


@router.get("/feedback")
def list_feedback(status: Optional[str] = None, category: Optional[str] = None):
    with conn() as c:
        sql, params = "SELECT * FROM feedback WHERE 1=1", []
        if status:
            sql += " AND status=%s"; params.append(status)
        if category:
            sql += " AND category=%s"; params.append(category)
        sql += " ORDER BY CASE status WHEN 'new' THEN 0 WHEN 'planned' THEN 1 ELSE 2 END, created_at DESC"
        rows = qa(c, sql, params)
        counts = {r["status"]: r["n"] for r in qa(c, "SELECT status, count(*) AS n FROM feedback GROUP BY status")}
    return {"items": rows, "counts": counts}


@router.put("/feedback/{fid}")
def update_feedback(fid: int, body: FeedbackUpdate):
    if body.status and body.status not in FEEDBACK_STATUS:
        raise HTTPException(400, "status 需為 new / planned / done / rejected")
    with conn() as c:
        row = q1(c, """UPDATE feedback SET status=coalesce(%s,status), admin_note=coalesce(%s,admin_note), category=coalesce(%s,category), updated_at=now()
                       WHERE id=%s RETURNING *""", (body.status, body.admin_note, body.category, fid))
        if not row:
            raise HTTPException(404)
        c.commit()
        return row


@router.delete("/feedback/{fid}", status_code=204)
def delete_feedback(fid: int):
    with conn() as c:
        c.execute("DELETE FROM feedback WHERE id=%s", (fid,))
        c.commit()


@router.get("/feedback-export.md")
def export_feedback_md(status: str = "new,planned"):
    """把待處理的回饋匯成 Markdown，貼給開發者 (Claude) 處理用。"""
    from fastapi.responses import Response as _Resp
    wanted = [s for s in status.split(",") if s]
    with conn() as c:
        rows = qa(c, "SELECT * FROM feedback WHERE status = ANY(%s) ORDER BY category, created_at", (wanted,))
    cat_name = {"bug": "問題", "feature": "需求", "question": "疑問", "other": "其他"}
    lines = [f"# 拆單系統 操作者回饋（{date.today()}，版本 {_read('VERSION').strip()}）", ""]
    for r in rows:
        lines.append(f"- [#{r['id']}][{cat_name.get(r['category'], r['category'])}] {r['message']}")
        meta = [x for x in [f"頁面 {r['page']}" if r["page"] else None, r["context"], f"回報人 {r['reporter']}" if r["reporter"] else None, str(r["created_at"])[:16], f"狀態 {r['status']}"] if x]
        lines.append("  - " + "｜".join(meta))
        if r["admin_note"]:
            lines.append(f"  - 備註：{r['admin_note']}")
    if not rows:
        lines.append("（沒有待處理的回饋）")
    return _Resp("\n".join(lines) + "\n", media_type="text/markdown; charset=utf-8",
                 headers={"Content-Disposition": "attachment; filename=\"feedback.md\""})


# ───────────────────────── 零件單 ─────────────────────────
@router.get("/projects/{pid}/parts-list")
def parts_list(pid: int):
    """設備五金零件單：五金類列依名稱彙總，附規格/型號 (從五金配件目錄比對)。"""
    with conn() as c:
        p = q1(c, "SELECT * FROM projects WHERE id=%s", (pid,))
        if not p:
            raise HTTPException(404)
        rows = qa(c, """SELECT pt.name, pt.category, sum(pt.qty) AS qty
                        FROM parts pt JOIN cabinets cb ON cb.id=pt.cabinet_id
                        WHERE cb.project_id=%s AND pt.name<>'' AND coalesce(pt.category,'') LIKE '%%五金'
                        GROUP BY pt.name, pt.category ORDER BY pt.category, pt.name""", (pid,))
        hw = qa(c, "SELECT product_name, model, spec, vendor FROM hardware_catalog")
    lookup = {h["product_name"].replace(" ", ""): h for h in hw}
    out = []
    for i, r in enumerate(rows, start=1):
        h = lookup.get(r["name"].replace(" ", ""))
        out.append({"no": i, "name": r["name"], "category": r["category"], "qty": r["qty"],
                    "spec": " ".join(x for x in [h["model"] if h else None, h["spec"] if h else None] if x) if h else "", "vendor": h["vendor"] if h else None})
    return {"project": p, "items": out, "date": date.today()}


# ───────────────────────── 客戶對帳單 ─────────────────────────
@router.get("/customers/{cid}/statement")
def customer_statement(cid: int, month: str, by: str = "delivery"):
    """month = YYYY-MM；by = delivery (交貨日) 或 order (訂貨日)。每張訂單金額 = 計價清單總金額 (含折數、加工費、運費、安裝、稅)。"""
    from .main import quote_calc
    try:
        y, m = (int(x) for x in month.split("-"))
        first, last = date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "month 格式需為 YYYY-MM")
    col = "delivery_date" if by == "delivery" else "order_date"
    with conn() as c:
        cu = q1(c, "SELECT * FROM customers WHERE id=%s", (cid,))
        if not cu:
            raise HTTPException(404)
        projects = qa(c, f"SELECT id FROM projects WHERE customer_id=%s AND {col} BETWEEN %s AND %s ORDER BY {col}, id", (cid, first, last))
    lines = []
    total_net, total_tax, total = D(0), D(0), D(0)
    for p in projects:
        qt = quote_calc(p["id"])
        pieces = sum(l["qty"] for l in qt["lines"] if l["unit"] == "才")
        lines.append({"project_id": p["id"], "order_no": qt["project"]["order_no"], "date": qt["project"][col], "site_name": qt["project"]["site_name"],
                      "pieces": pieces, "cai": r2(sum((l["cai"] or D(0)) for l in qt["lines"])), "net": qt["taxable"], "tax": qt["tax"], "total": qt["total"]})
        total_net += qt["taxable"]; total_tax += qt["tax"]; total += qt["total"]
    return {"customer": cu, "month": month, "by": by, "lines": lines, "total_net": r2(total_net), "total_tax": r2(total_tax), "total": r2(total)}
