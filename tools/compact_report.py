import sys, json, collections
r = json.load(open(sys.argv[1], encoding="utf-8"))
out = []
out.append(f"# {r['file']}")
out.append("## defined names")
for k, v in r["defined_names"].items():
    out.append(f"- {k} = {v}")
for s in r["sheets"]:
    out.append(f"\n## [{s['state']}] {s['name']}  dims={s['dims']} values={s['value_count']} formulas={s['formula_count']} merged={s['merged']}")
    if s["header_rows"]:
        out.append("headers:")
        for row in s["header_rows"][:4]:
            out.append("  " + " | ".join(row)[:600])
    if s["func_usage"]:
        out.append("funcs: " + ", ".join(f"{k}:{v}" for k, v in s["func_usage"].items()))
    if s["cross_sheet_refs"]:
        out.append("xrefs: " + ", ".join(f"{k}:{v}" for k, v in s["cross_sheet_refs"].items()))
    if s["data_validations"]:
        for dv in s["data_validations"]:
            out.append(f"DV: {dv['type']} {dv['formula1']} @ {dv['sqref'][:60]}...")
    if s["cond_formats"]:
        c = collections.Counter((cf["type"], str(cf["formula"])[:60]) for cf in s["cond_formats"])
        out.append("CF: " + "; ".join(f"{t} {f} x{n}" for (t, f), n in c.items()))
    if s["formulas"]:
        out.append("formula patterns (sorted by count):")
        for p in sorted(s["formulas"], key=lambda x: -x["count"]):
            ex = p["example"].replace("\n", " ")
            ex = " ".join(ex.split())
            out.append(f"  - x{p['count']} @{p['example_cell']}: {ex[:700]}")
open(sys.argv[2], "w", encoding="utf-8").write("\n".join(out))
print(len(out))
