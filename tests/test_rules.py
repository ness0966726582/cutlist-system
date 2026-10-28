"""料單規則的純函式測試 (對應 Excel 料單 G/I/P/Q/R/T 欄與才數公式)。"""
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from app import rules  # noqa: E402


def test_edge_rules_match_excel():
    assert rules.edge_l("頂板") == "AA" and rules.edge_w("頂板") == ""
    assert rules.edge_l("左側板") == "AA" and rules.edge_w("左側板") == "AA"
    assert rules.edge_l("背板") == "" and rules.edge_w("背板") == ""


def test_hinge_count_by_door_length():
    assert rules.mark_p("左門板", 1000, []) == "鉸2"
    assert rules.mark_p("左門板", 1800, []) == "鉸3"
    assert rules.mark_p("右門板", 1900, []) == "鉸4"


def test_back_groove_depends_on_siblings():
    names = ["頂板", "底板", "左側板", "背板"]
    assert rules.mark_p("左側板", 2000, names) == "背板溝"
    assert rules.mark_p("左側板", 2000, ["頂板", "外蓋背板"]) == "側"
    assert rules.mark_p("頂板", 1000, ["入柱背板"]) == "面"


def test_marks_and_reminders():
    assert rules.mark_q("中立板") == "側" and rules.mark_r("中立板") == "排"
    assert rules.reminder("中立板") == "面開槽？排孔？"
    assert rules.reminder("左門板") == "把手？"
    assert rules.cabinet_note("水槽櫃") == "無頂板" and rules.cabinet_note("油機吊櫃") == "無底板"


def test_area_cai():
    assert rules.area_cai(1164, 600, 1) == Decimal("7.7600")
    assert rules.area_cai(None, 600, 1) is None


def test_default_parts_use_board_thickness():
    rows = rules.default_parts(2000, 600, 1200, 18)
    top = next(r for r in rows if r[1] == "頂板")
    assert top[2] == Decimal(1164) and top[3] == Decimal(600)
    rows175 = rules.default_parts(2000, 600, 1200, 17.5)
    assert next(r for r in rows175 if r[1] == "頂板")[2] == Decimal("1165.0")


def test_norm_edge_strips_fullwidth_space():
    assert rules.norm_edge("A　") == "A"
    assert rules.norm_edge(None) == ""
