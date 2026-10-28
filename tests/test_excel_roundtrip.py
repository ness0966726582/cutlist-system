"""Excel 料單 匯入 → 匯出 → 再匯入 的純函式 round-trip (不需資料庫)。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from app import exporter, importer  # noqa: E402

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


def _project_from_parsed(parsed):
    h = parsed["header"]
    p = {"order_no": h["order_no"] or "2026010101", "site_name": h["site_name"], "designer": h["designer"], "order_date": h["order_date"],
         "delivery_date": h["delivery_date"], "joint_type": h["joint_type"], "delivery_address": h["delivery_address"],
         "board_thickness": h["board_thickness"], "revision_dates": []}
    cabs = []
    for cab in parsed["cabinets"]:
        parts = []
        for seq, x in enumerate(cab["parts"], start=1):
            parts.append({**x, "part_no": cab["cabinet_no"] * 1000 + seq, "color_name": None, "board_vendor": None, "edge_code": None})
        cabs.append({**cab, "parts": parts})
    return p, cabs


def test_case_workbook_roundtrip():
    src = SAMPLES / "case_新竹金山街.xlsx"
    parsed = importer.parse_workbook(src.read_bytes())
    assert len(parsed["cabinets"]) == 22
    assert parsed["header"]["board_thickness"] == 17.5
    assert parsed["header"]["joint_type"] == "L"
    total_parts = sum(len(c["parts"]) for c in parsed["cabinets"])
    assert total_parts == 337

    p, cabs = _project_from_parsed(parsed)
    data = exporter.build_xlsx(p, cabs)
    again = importer.parse_workbook(data)
    assert [c["cabinet_no"] for c in again["cabinets"]] == [c["cabinet_no"] for c in parsed["cabinets"]]
    for a, b in zip(parsed["cabinets"], again["cabinets"]):
        assert [(x["name"], x["length"], x["width"], x["qty"], x["edge_l"], x["mark_p"]) for x in a["parts"]] == \
               [(x["name"], x["length"], x["width"], x["qty"], x["edge_l"], x["mark_p"]) for x in b["parts"]]


def test_blank_template_imports_as_empty():
    parsed = importer.parse_workbook((SAMPLES / "blank_18.xlsx").read_bytes())
    assert parsed["cabinets"] == []
