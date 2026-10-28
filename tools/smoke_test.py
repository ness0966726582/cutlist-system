import json, sys, urllib.request

BASE = "http://localhost:8100/api"
out = []


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method, headers={"Content-Type": "application/json"},
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req) as r:
            txt = r.read().decode()
            return r.status, (json.loads(txt) if txt else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def log(*a):
    out.append(" ".join(str(x) for x in a))


s, h = call("GET", "/health"); log("health", s, h)
s, colors = call("GET", "/master/colors?limit=3"); log("colors", s, colors)
s, c = call("GET", "/master/colors/1614"); log("color 1614", s, c)
s, cat = call("GET", "/master/parts-catalog"); log("catalog cats", s, list(cat.keys()), "桶身 n=", len(cat.get("桶身", [])))
s, lk = call("GET", "/master/lookups"); log("lookups", s, {k: len(v) for k, v in lk.items()})
s, m = call("GET", "/master/marks"); log("marks", s, len(m))
s, hw = call("GET", "/master/hardware"); log("hardware", s, len(hw))
s, v = call("GET", "/master/vendors"); log("vendors", s, len(v))

s, cu = call("POST", "/customers", {"code": "TEST001", "name": "測試設計師", "board_discount": 0.41}); log("customer", s, cu)
s, p = call("POST", "/projects", {"site_name": "測試案場", "customer_id": cu["id"], "designer": "測試設計師", "board_thickness": 18}); log("project", s, p)
pid = p["id"]
s, cb = call("POST", f"/projects/{pid}/cabinets", {"name": "水槽櫃", "height": 2000, "depth": 600, "width": 1200}); log("cabinet", s, cb["cabinet_no"], cb["note"], "parts=", len(cb["parts"]))
for x in cb["parts"]:
    log("  ", x["part_no"], x["category"], x["name"], x["length"], x["edge_l"], x["width"], x["edge_w"], x["thickness"], "P=", x["mark_p"], "Q=", x["mark_q"], "R=", x["mark_r"], "T=", x["reminder"])
# set colors on parts and check pricing
for x in cb["parts"]:
    body = {k: x[k] for k in ("category", "name", "length", "width", "thickness", "qty", "remark", "status_code")}
    body["color_code"] = "1614" if x["thickness"] != 4 else "9999"
    s, r = call("PUT", f"/parts/{x['id']}", body)
    if s != 200: log("PUT part fail", s, r)
s, p2 = call("GET", f"/projects/{pid}")
for x in p2["cabinets"][0]["parts"][:4]:
    log("  priced", x["name"], x["color_code"], x["color_name"], x["edge_code"], "cai=", x["area_cai"], "unit=", x["unit_price"], "amt=", x["amount"])
# add a part manually (door with length to test hinge count), and a hardware item
s, r = call("POST", f"/cabinets/{cb['id']}/parts", {"category": "外部", "name": "左門板", "length": 1900, "width": 596, "thickness": 18, "qty": 2, "color_code": "1614"}); log("door", s, r["mark_p"], r["edge_l"], r["edge_w"], r["reminder"])
s, r = call("POST", f"/cabinets/{cb['id']}/parts", {"category": "內部五金", "name": "活隔粒", "qty": 8}); log("hardware part", s, r["part_no"], r["name"])
s, sm = call("GET", f"/projects/{pid}/summary"); log("summary", s, sm["total_pieces"], sm["total_cai"], sm["total_amount"], sm["cabinets"])
s, qt = call("GET", f"/projects/{pid}/quote?freight=500&install=1000"); log("quote", s, "lines=", len(qt["lines"]), "subtotal=", qt["subtotal"], "tax=", qt["tax"], "total=", qt["total"])
s, lb = call("GET", f"/projects/{pid}/labels"); log("labels", s, len(lb), lb[0])
s, se = call("GET", f"/projects/{pid}/serials"); log("serials", s, len(se), se[0], se[-1])
s, r = call("POST", f"/projects/{pid}/scans", {"serial_no": 1, "stage": "cut"}); log("scan", s, r)
s, mt = call("GET", f"/projects/{pid}/material"); log("material", s, mt)
# 17.5 version check
s, p175 = call("POST", "/projects", {"site_name": "17.5測試", "board_thickness": 17.5})
s, cb2 = call("POST", f"/projects/{p175['id']}/cabinets", {"name": "高櫃", "height": 2000, "depth": 600, "width": 1200})
log("17.5 頂板 length:", [x["length"] for x in cb2["parts"] if x["name"] == "頂板"], "thickness:", [x["thickness"] for x in cb2["parts"] if x["name"] == "頂板"])
s, lst = call("GET", "/projects"); log("projects", s, [(x["order_no"], x["cabinet_count"], x["piece_count"]) for x in lst])
# cleanup second
call("DELETE", f"/projects/{p175['id']}")
open(sys.argv[1], "w", encoding="utf-8").write("\n".join(out))
print("done", len(out))
