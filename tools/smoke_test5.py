"""Checks for the remaining-sheet features (quote discounts/fees, parts list, statement, edge specs, hardware txns, price tables, cost, settings)."""
import json, sys, urllib.request
from urllib.parse import quote

B = "http://localhost:8100/api"
out = []
log = lambda *a: out.append(" ".join(str(x) for x in a))


def call(method, path, body=None):
    req = urllib.request.Request(B + path, method=method, headers={"Content-Type": "application/json"},
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req) as r:
            t = r.read().decode(); return r.status, (json.loads(t) if t else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


s, pp = call("GET", "/master/process-prices?kind=" + quote("門板加工")); log("process 門板加工", s, len(pp), [(x["name"], x["unit"], x["price"]) for x in pp[:4]])
s, cp = call("GET", "/master/cabinet-prices"); log("cabinet prices", s, len(cp), {k: cp[0][k] for k in ("name", "spec", "sell_calc", "designer_price", "designer_price_install", "employee_price")})
s, ca = call("GET", "/master/cost-analysis"); log("cost rows", s, len(ca), {k: ca[0][k] for k in ("color_code", "taxed_cost", "per_cai", "per_cai_loss", "make_cost", "price_net", "margin_rate", "price_taxed")})
s, st = call("GET", "/settings"); log("settings", s, st["company_name"], bool(st["bank_info"]))
s, es = call("GET", "/master/edge-specs"); log("edge specs", s, [(float(x["max_thickness"]), x["spec"]) for x in es])

# customer with discounts + project
s, cu = call("POST", "/customers", {"code": "T-DISC", "name": "折數測試", "board_discount": 0.5, "install_discount": 0.2})
s, p = call("POST", "/projects", {"site_name": "計價測試", "customer_id": cu["id"], "delivery_date": "2026-10-25"}); pid = p["id"]
s, cb = call("POST", f"/projects/{pid}/cabinets", {"name": "高櫃", "height": 2000, "depth": 600, "width": 1200, "color_code": "1614"})
# set door lengths so marks exist; add 上斜 remark
door = next(x for x in cb["parts"] if x["name"] == "左門板")
body = {k: door[k] for k in ("category", "name", "width", "thickness", "qty", "color_code", "status_code")}; body["length"] = 1900; body["remark"] = "上斜"
call("PUT", f"/parts/{door['id']}", body)
s, q = call("GET", f"/projects/{pid}/quote"); log("quote default", s, {k: q[k] for k in ("subtotal", "discount", "discount_source", "boards_net", "fees_total", "install", "freight", "tax", "total")})
s, sg = call("POST", f"/projects/{pid}/fees/suggest"); log("suggest fees", s, [(f["name"], float(f["qty"]), float(f["unit_price"])) for f in sg["added"]])
s, f1 = call("POST", f"/projects/{pid}/fees", {"name": "運送上樓", "unit": "次", "qty": 1, "unit_price": 800}); log("fee add", s)
s, q2 = call("PUT", f"/projects/{pid}/quote-settings", {"freight": 500, "install": 0, "install_auto": True, "board_discount": None, "quote_meta": {"contact": "王先生"}})
log("quote w/ auto install", s, {k: q2[k] for k in ("subtotal", "discount", "boards_net", "fees_total", "install", "install_rate", "freight", "taxable", "tax", "total")})
chk = float(q2["boards_net"]) == round(float(q2["subtotal"]) * 0.5, 2) and float(q2["install"]) == round(float(q2["boards_net"]) * 0.2, 2) and abs(float(q2["total"]) - round(float(q2["taxable"]) * 1.05, 2)) < 0.02
log("quote math ok:", chk, "cabinets:", q2["cabinets"][0]["spec"])
s, q3 = call("PUT", f"/projects/{pid}/quote-settings", {"freight": 0, "install": 1000, "install_auto": False, "board_discount": 0.8, "quote_meta": {}}); log("override discount", q3["discount"], q3["discount_source"], q3["install"])
s, pl = call("GET", f"/projects/{pid}/parts-list"); log("parts list", s, pl["items"])
s, hw = call("POST", f"/cabinets/{cb['id']}/parts", {"name": "活隔粒", "qty": 8}); s, pl = call("GET", f"/projects/{pid}/parts-list"); log("parts list w/ hw", [(i["name"], float(i["qty"]), i["spec"]) for i in pl["items"]])
s, stm = call("GET", f"/customers/{cu['id']}/statement?month=2026-10&by=delivery"); log("statement", s, len(stm["lines"]), stm["total"], stm["lines"][0]["order_no"] if stm["lines"] else None)
s, stm2 = call("GET", f"/customers/{cu['id']}/statement?month=2026-09"); log("statement empty month", len(stm2["lines"]), stm2["total"])
s, mt = call("GET", f"/projects/{pid}/material"); log("edge bands", [(e["color_code"], e["spec"], round(float(e["edge_band_mm"]) / 1000, 1)) for e in mt["edge_bands"]])
s, lb = call("GET", f"/projects/{pid}/labels"); log("label joint/edge fields", lb[0]["joint_type"], lb[0]["edge_l_first"], lb[0]["edge_l_flag"])
# hardware txns
s, hwl = call("GET", "/master/hardware?q=" + quote("w0")); hid = hwl[0]["id"]
s, t1 = call("POST", f"/master/hardware/{hid}/txns", {"kind": "in", "qty": 100, "amount": 1000, "voucher_no": "V1"})
s, t2 = call("POST", f"/master/hardware/{hid}/txns", {"kind": "out", "qty": 30, "site": "測試"})
s, tx = call("GET", f"/master/hardware/{hid}/txns"); log("stock after in100 out30:", tx["stock"], "txns", len(tx["txns"]))
s, stock = call("GET", "/master/hardware-stock"); log("stock map", stock.get(str(hid)))
call("DELETE", f"/master/hardware-txns/{t1['id']}"); call("DELETE", f"/master/hardware-txns/{t2['id']}")
s, r = call("POST", f"/master/hardware/{hid}/txns", {"kind": "bad", "qty": 1}); log("bad kind ->", s)
# process price CRUD
s, np_ = call("POST", "/master/process-prices", {"kind": "門板加工", "name": "測試加工", "unit": "才", "price": 99}); log("process add", s)
s, r = call("POST", "/master/process-prices", {"kind": "門板加工", "name": "測試加工"}); log("process dup ->", s)
call("DELETE", f"/master/process-prices/{np_['id']}")
# edge spec CRUD
s, e1 = call("POST", "/master/edge-specs", {"max_thickness": 12, "spec": "測試規格"}); call("DELETE", f"/master/edge-specs/{e1['id']}"); log("edge spec add/del", s)
# cabinet price calc
s, c1 = call("POST", "/master/cabinet-prices", {"name": "測試櫃", "spec": "100x50", "factor": 1.05, "base_price": 1000, "designer_discount": 0.6, "employee_discount_draw": 0.5, "employee_discount": 0.47})
log("cabinet price calc", float(c1["sell_calc"]), float(c1["designer_price"]), float(c1["designer_price_install"]), float(c1["employee_price"]))
call("DELETE", f"/master/cabinet-prices/{c1['id']}")
s, cs = call("POST", "/master/cost-analysis", {"color_code": "T", "list_cost": 1050, "full_cai": 32, "usable_cai": 26, "edge_m_per_cai": 1.2, "edge_cost": 8, "margin": 39})
log("cost calc (expect 95.55):", float(cs["price_taxed"]), "margin%", float(cs["margin_rate"]))
call("DELETE", f"/master/cost-analysis/{cs['id']}")
s, st2 = call("PUT", "/settings", {"company_phone": "02-0000"}); log("settings put", s, st2["company_phone"]); call("PUT", "/settings", {"company_phone": ""})
call("DELETE", f"/projects/{pid}")
open(sys.argv[1], "w", encoding="utf-8").write("\n".join(out)); print("done")
