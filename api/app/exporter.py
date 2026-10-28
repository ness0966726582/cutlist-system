"""匯出成原「拆單系統 2026年6.0版」Excel 料單格式。

以空白範本 (templates/blank_17.5.xlsx / blank_18.xlsx) 為底，只回填「料單」分頁的輸入格：
表頭 (C1 訂單編號, C2 案場, C3 業務/設計師, K2/K3 日期, L3 拉/KD, L4 送貨地址, O2~O4 修改日期)
與每個櫃體區塊 (名稱 / 櫃號 / 高深寬 / 批次 / 明細列)。其餘分頁 (標籤列印版、板材才數分析、計價清價、流水號…)
的公式保持原樣，Excel 開啟時重新計算。

明細列的自動欄位 (封邊 / 備註 1~3 / 提醒 / 色號名稱 / 板商 / 封邊色號) 直接寫入系統的值 (含手動覆寫)，
避免工廠端因範本公式或色號表差異而與系統不一致。
"""
import io
import os
from datetime import date, datetime

from openpyxl import load_workbook
from openpyxl.workbook.properties import CalcProperties

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
BLOCK_ROWS = 30          # 每個櫃體區塊 30 列明細
PART_ROW_OFFSET = 7      # 區塊起始列 (櫃體名稱) + 7 = 第一列明細

# 明細欄位 → 欄號 (料單分頁)
COL = dict(part_no=3, category=4, name=5, length=6, edge_l=7, width=8, edge_w=9, thickness=10, qty=11,
           color_code=12, color_name=13, board_vendor=14, edge_code=15, mark_p=16, mark_q=17, mark_r=18,
           remark=19, reminder=20)


def _template_for(thickness) -> str:
    name = "blank_17.5.xlsx" if float(thickness or 18) == 17.5 else "blank_18.xlsx"
    return os.path.join(TEMPLATE_DIR, name)


def _d(v):
    if isinstance(v, datetime):
        return v
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day)
    if isinstance(v, str) and v:
        try:
            return datetime.fromisoformat(v)
        except ValueError:
            return None
    return None


def _f(v):
    """numeric → int if whole (Excel 顯示 465 而非 465.0)。"""
    if v is None:
        return None
    f = float(v)
    return int(f) if f.is_integer() else f


def _set(ws, ref: str, value):
    """寫入儲存格；若是合併範圍的非左上格，改寫到左上格。"""
    cell = ws[ref]
    if type(cell).__name__ == "MergedCell":
        for rng in ws.merged_cells.ranges:
            if cell.coordinate in rng:
                cell = ws.cell(rng.min_row, rng.min_col)
                break
    cell.value = value


def build_xlsx(project: dict, cabinets: list[dict]) -> bytes:
    wb = load_workbook(_template_for(project.get("board_thickness")))
    ws = wb["料單"]
    starts = [r for r in range(1, ws.max_row + 1) if ws.cell(r, 1).value == "櫃體名稱"]

    # ── 表頭 (C1 訂單編號, C2 案場, C3 設計師, K2/K3 日期, L3 拉/KD, K4 送貨地址, O2~O4 修改日期) ──
    _set(ws, "C1", project["order_no"])
    _set(ws, "C2", project["site_name"])
    _set(ws, "C3", project.get("designer"))
    _set(ws, "K2", _d(project.get("order_date")))
    _set(ws, "K3", _d(project.get("delivery_date")))
    _set(ws, "L3", project.get("joint_type"))
    _set(ws, "K4", project.get("delivery_address"))
    for i, rv in enumerate((project.get("revision_dates") or [])[:3]):
        _set(ws, f"O{2 + i}", _d(rv))

    # ── 櫃體 → 區塊 (超過 30 列的櫃體拆成續頁區塊) ──
    chunks = []
    for cb in cabinets:
        parts = cb["parts"]
        if not parts:
            continue   # 沒有板材的櫃體不佔區塊
        for i in range(0, len(parts), BLOCK_ROWS):
            chunks.append((cb, parts[i:i + BLOCK_ROWS], i > 0))
    if len(chunks) > len(starts):
        raise ValueError(f"櫃體區塊數 {len(chunks)} 超過範本上限 {len(starts)}（每櫃 30 列明細，超過會多佔一個區塊）；請拆成兩個專案匯出")

    for idx, (cb, parts, cont) in enumerate(chunks):
        b = starts[idx]
        _set(ws, f"C{b}", cb["name"] + ("(續)" if cont else ""))
        _set(ws, f"C{b + 1}", cb["cabinet_no"])
        _set(ws, f"C{b + 2}", _f(cb.get("height")))
        _set(ws, f"C{b + 3}", _f(cb.get("depth")))
        _set(ws, f"C{b + 4}", _f(cb.get("width")))
        _set(ws, f"L{b + 3}", cb.get("batch") or 1)
        for i in range(BLOCK_ROWS):
            r = b + PART_ROW_OFFSET + i
            if i < len(parts):
                x = parts[i]
                for key, col in COL.items():
                    v = x.get(key)
                    if key in ("length", "width", "thickness"):
                        v = _f(v)
                    _set(ws, ws.cell(r, col).coordinate, v if v not in ("",) else None)
                _set(ws, ws.cell(r, COL["qty"]).coordinate, x.get("qty") or 1)
            else:
                # 清掉範本預填的 頂板/底板… 與尺寸公式，保留 A/G/I/M~R/T/U 公式 (E 空白時都會回傳空字串)
                for col in (COL["category"], COL["name"], COL["length"], COL["width"], COL["thickness"],
                            COL["qty"], COL["color_code"], COL["remark"]):
                    _set(ws, ws.cell(r, col).coordinate, None)

    wb.calculation = CalcProperties(fullCalcOnLoad=True)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
