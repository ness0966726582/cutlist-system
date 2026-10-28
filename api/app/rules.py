"""料單 公式規則移植 (對應 Excel 「料單」分頁 G / I / P / Q / R / T 欄、D7、板材才數分析 O 欄)。

每條規則上方註明來源儲存格，方便對照原始公式。
"""
from decimal import Decimal
from typing import Iterable, Optional

# 料單!G14 ─ 長邊封邊：名稱在此集合 → "AA"，否則空白
EDGE_L_NAMES = {
    "頂板", "底板", "右側板", "左側板",
    "天地蓋頂板", "天地蓋底板", "天地蓋右側板", "天地蓋左側板",
    "前抽牆", "後抽牆", "左抽牆", "右抽牆",
    "踢腳板", "補板", "固隔", "活隔",
    "中立板", "中立板(退)", "固隔(退)", "活固隔", "立板",
    "內頂板", "內左側落板", "內右側落板", "內底板",
    "內左側板", "內右側板",
    "上前平肢", "上後平肢", "上前立肢", "上後立肢",
    "下前立肢", "下後立肢", "下前平肢", "下後平肢",
    "左側落板", "右側落板",
    "外蓋背板", "台面", "床板", "假門板",
    "上掀門板", "平掀門板", "下掀門板",
    "左門板", "右門板",
    "抽盤", "抽盤抽頭",
    "上軌道板", "下軌道板", "左軌道板", "右軌道板", "指縫擋板", "左木框滑門", "右木框滑門",
    "層板", "壁面層板", "桌板", "上封板", "下封板", "左封板", "右封板",
    "左圓角側板", "右圓角側板", "抽頭", "入柱抽頭", "假抽頭", "背拉桿", "木滑門", "抽屜拉桿",
}

# 料單!I14 ─ 寬邊封邊
EDGE_W_NAMES = {
    "右側板", "左側板", "活隔",
    "天地蓋頂板", "天地蓋底板",
    "左門板", "右門板",
    "左側落板", "右側落板",
    "外蓋背板", "活固隔",
    "左木框滑門", "右木框滑門",
    "左鋁框滑門", "右鋁框滑門",
    "桌板", "台面", "床板", "假門板",
    "上掀門板", "平掀門板", "下掀門板",
    "抽盤抽頭", "抽盤", "層板", "壁面層板",
    "上封板", "下封板", "左封板", "右封板",
    "抽頭", "踢腳板", "補板", "木滑門",
}


AUTO_FIELDS = ("edge_l", "edge_w", "mark_p", "mark_q", "mark_r", "reminder")


def norm_edge(v) -> str:
    """封邊值正規化：Excel 裡常見 'A　'(全形空白) → 'A'。合法值 '', 'A', 'AA'。"""
    if v is None:
        return ""
    return str(v).replace("　", "").strip().upper()


def norm_text(v) -> str:
    if v is None:
        return ""
    return " ".join(str(v).replace("　", " ").split())


def edge_l(name: str) -> str:
    return "AA" if name in EDGE_L_NAMES else ""


def edge_w(name: str) -> str:
    return "AA" if name in EDGE_W_NAMES else ""


def hinge_count(length) -> int:
    """料單!P14 門板鉸鏈數：長 ≤1000 → 2，≤1800 → 3，否則 4。"""
    if length is None:
        return 2
    length = float(length)
    return 2 if length <= 1000 else 3 if length <= 1800 else 4


def mark_p(name: str, length, cabinet_part_names: Iterable[str]) -> str:
    """料單!P14 ─ 備註 1。需要同櫃其他板材名稱 (COUNTIF($E$14:$E$43, ...))。"""
    names = set(cabinet_part_names)
    if name in ("左門板", "右門板"):
        return f"鉸{hinge_count(length)}"
    if name == "入柱背板":
        return "側"
    if name == "外蓋背板":
        return "面"
    if "入柱背板" in names and name in ("頂板", "底板"):
        return "面"
    if "外蓋背板" in names and name in ("左側板", "右側板"):
        return "側"
    if "入柱背板" not in names and "外蓋背板" not in names:
        if "背板" in names and name in (
            "左側板", "右側板", "頂板", "底板",
            "天地蓋右側板", "天地蓋左側板", "天地蓋底板", "天地蓋頂板",
        ):
            return "背板溝"
        if "抽底" in names and name in ("右抽牆", "左抽牆", "前抽牆", "後抽牆"):
            return "背板溝"
    return ""


def mark_q(name: str) -> str:
    """料單!Q14 ─ 備註 2 (開槽方向 / 輪 / 固)。"""
    if name in ("天地蓋右側板", "天地蓋左側板"):
        return "側 面"
    if name in ("背拉桿", "中立板", "頂板", "底板", "前抽牆", "後抽牆",
                "內左側落板", "內右側落板", "抽屜拉桿", "立板"):
        return "側"
    if name in ("木滑門", "鋁框滑門"):
        return "輪"
    if name in ("右側板", "左側板", "右抽牆", "左抽牆", "天地蓋頂板", "天地蓋底板", "內頂板"):
        return "面"
    if name == "固隔":
        return "固"
    return ""


def mark_r(name: str) -> str:
    """料單!R14 ─ 備註 3 (排孔)。"""
    if name in ("左側板", "右側板", "天地蓋左側板", "天地蓋右側板", "中立板", "立板"):
        return "排"
    return ""


def reminder(name: str) -> str:
    """料單!T14 ─ 提醒。"""
    if name == "中立板":
        return "面開槽？排孔？"
    if name == "木框滑門":
        return "前排孔要退喔！"
    if name in ("左門板", "右門板", "抽頭"):
        return "把手？"
    if name in ("左側板", "右側板", "天地蓋右側板", "天地蓋左側板"):
        return "排孔？"
    return ""


def cabinet_note(cabinet_name: str) -> str:
    """料單!D7 ─ IFS(水槽櫃/爐台櫃 → 無頂板, 油機吊櫃 → 無底板)。"""
    if cabinet_name in ("水槽櫃", "爐台櫃", "爐檯櫃"):
        return "無頂板"
    if cabinet_name == "油機吊櫃":
        return "無底板"
    return ""


def area_cai(length, width, qty) -> Optional[Decimal]:
    """板材才數分析!O2 ─ 才數 = 長 × 寬 / 90000 × 數量 (mm → 才)。"""
    if length is None or width is None:
        return None
    return (Decimal(str(length)) * Decimal(str(width)) / Decimal(90000) * Decimal(qty or 0)).quantize(Decimal("0.0001"))


def label_edge_fields(edge: str):
    """標籤列印版!W/X ─ 封邊字串轉標籤欄位。"""
    edge = edge or ""
    w = "" if (edge[:1] == "0" or edge == "") else edge[:1]
    x = "A" if edge == "AA" else (" " if edge == "A" else "")
    return w, x


def default_parts(height, depth, width, thickness):
    """料單 新櫃體預設列 (R14~R24)：桶身 / 內部 / 外部 標準板件與尺寸公式。

    t = 板厚 (17.5 版 → 減 35；18 版 → 減 36，即 2 × 板厚)。
    """
    t = Decimal(str(thickness))
    h = Decimal(str(height)) if height is not None else None
    d = Decimal(str(depth)) if depth is not None else None
    w = Decimal(str(width)) if width is not None else None

    def sub(a, b):
        return None if a is None else a - Decimal(b)

    rows = [
        # (類別, 名稱, 長, 寬, 厚)
        ("桶身", "頂板",   sub(w, 2 * t), d,               t),   # F14 = C11-2t, H14 = C10
        ("桶身", "底板",   sub(w, 2 * t), d,               t),
        ("桶身", "左側板", h,             d,               t),   # F16 = C9
        ("桶身", "右側板", h,             d,               t),
        ("桶身", "背板",   sub(h, 22),    sub(w, 22),      Decimal(4)),  # F18 = C9-22, H18 = C11-22, J18 = 4
        ("桶身", "背拉桿", sub(w, 2 * t), Decimal(120),    t),   # F19 = F14, H19 = 120
        ("內部", "中立板", sub(w, 2 * t), sub(d, 22),      t),   # H20 = C10-22
        ("內部", "活隔",   None,          sub(d, 32),      t),   # H21 = C10-22-10
        ("內部", "固隔",   None,          sub(d, 22),      t),   # H22 = C10-22
        ("外部", "左門板", None,          (w / 2 - 4) if w is not None else None, t),  # H23 = C11/2-4
        ("外部", "右門板", None,          (w / 2 - 4) if w is not None else None, t),
    ]
    return rows
