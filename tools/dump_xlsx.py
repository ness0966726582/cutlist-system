import sys, json, re, collections
from openpyxl import load_workbook

path = sys.argv[1]
out = sys.argv[2]
wb = load_workbook(path, data_only=False)
report = {"file": path, "sheets": [], "defined_names": {}}

try:
    for name, dn in wb.defined_names.items():
        report["defined_names"][name] = dn.attr_text
except Exception as e:
    report["defined_names_error"] = str(e)

for ws in wb.worksheets:
    info = {
        "name": ws.title,
        "state": ws.sheet_state,
        "dims": ws.dimensions,
        "max_row": ws.max_row,
        "max_col": ws.max_column,
        "merged": len(ws.merged_cells.ranges),
        "data_validations": [],
        "cond_formats": [],
        "formulas": [],
        "formula_count": 0,
        "value_count": 0,
        "header_rows": [],
        "func_usage": collections.Counter(),
        "cross_sheet_refs": collections.Counter(),
    }
    try:
        for dv in ws.data_validations.dataValidation:
            info["data_validations"].append({"type": dv.type, "formula1": dv.formula1, "sqref": str(dv.sqref)})
    except Exception as e:
        info["dv_error"] = str(e)
    try:
        for rng, rules in ws.conditional_formatting._cf_rules.items():
            for r in rules:
                info["cond_formats"].append({"range": str(rng.sqref), "type": r.type, "formula": list(r.formula) if r.formula else None})
    except Exception as e:
        info["cf_error"] = str(e)

    # header rows: first 6 rows values
    for r in range(1, min(ws.max_row, 8) + 1):
        row = []
        for c in range(1, min(ws.max_column, 40) + 1):
            v = ws.cell(r, c).value
            if v is not None:
                row.append(f"{ws.cell(r,c).coordinate}={v!r}"[:80])
        if row:
            info["header_rows"].append(row)

    # formula patterns: group by normalized formula (replace row numbers)
    patterns = collections.OrderedDict()
    for row in ws.iter_rows():
        for cell in row:
            v = cell.value
            if v is None:
                continue
            if hasattr(v, "text") and hasattr(v, "ref"):
                v = "={ARRAY " + str(v.ref) + "}" + str(v.text)
            if isinstance(v, str) and v.startswith("="):
                info["formula_count"] += 1
                for f in re.findall(r"([A-Z][A-Z0-9\.]+)\(", v):
                    info["func_usage"][f] += 1
                for s in re.findall(r"'?([^'!\(\),=+\-*/]+)'?!", v):
                    if s != ws.title:
                        info["cross_sheet_refs"][s.strip("'")] += 1
                norm = re.sub(r"(?<![A-Za-z])(\$?[A-Z]{1,3})\$?(\d+)", r"\1#", v)
                if norm not in patterns:
                    patterns[norm] = {"example_cell": cell.coordinate, "example": v, "count": 0, "cells": []}
                patterns[norm]["count"] += 1
                if len(patterns[norm]["cells"]) < 5:
                    patterns[norm]["cells"].append(cell.coordinate)
            else:
                info["value_count"] += 1
    info["formulas"] = [{"pattern": k[:400], **v} for k, v in patterns.items()]
    info["func_usage"] = dict(info["func_usage"].most_common())
    info["cross_sheet_refs"] = dict(info["cross_sheet_refs"].most_common())
    report["sheets"].append(info)

with open(out, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=1)

# brief summary to stdout
print("FILE:", path)
print("defined names:", len(report["defined_names"]))
for s in report["sheets"]:
    print(f"- {s['name']} [{s['state']}] dims={s['dims']} values={s['value_count']} formulas={s['formula_count']} patterns={len(s['formulas'])} dv={len(s['data_validations'])} cf={len(s['cond_formats'])} merged={s['merged']}")
