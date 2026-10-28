"""Master-data CRUD + CSV round-trip checks."""
import json, sys, urllib.request, uuid

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


def upload(path, data, fname):
    b = uuid.uuid4().hex
    body = (f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{fname}"\r\nContent-Type: text/csv\r\n\r\n').encode() + data + f"\r\n--{b}--\r\n".encode()
    req = urllib.request.Request(B + path, method="POST", data=body, headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    with urllib.request.urlopen(req) as r:
        return r.status, json.loads(r.read().decode())


s, ths = call("GET", "/master/thicknesses"); log("thicknesses", ths)
s, r = call("POST", "/master/colors", {"code": "TEST9", "board_name": "測試板", "vendor": "翰可", "edge_code": "E1", "prices": {"18": 100, "4": 50}}); log("create color", s, r["prices"] if s == 201 else r)
s, r = call("POST", "/master/colors", {"code": "TEST9"}); log("dup color ->", s)
s, r = call("PUT", "/master/colors/TEST9", {"code": "TEST9", "board_name": "測試板2", "vendor": "翰可", "prices": {"18": 120, "4": None}}); log("update color", s, r["board_name"], r["prices"])
s, rows = call("GET", "/master/colors?with_prices=true&q=TEST9"); log("list with prices", s, rows[0]["prices"])
# csv export/import
with urllib.request.urlopen(f"{B}/master/colors-export.csv") as r:
    csv_text = r.read().decode("utf-8-sig")
lines = csv_text.splitlines(); log("csv header", lines[0], "rows", len(lines) - 1)
test_line = next(l for l in lines if l.startswith("TEST9")); log("csv TEST9 line", test_line)
hdr = lines[0].split(","); i18 = hdr.index("18"); i4 = hdr.index("4")
cells = test_line.split(","); cells[i18] = "131"; cells[i4] = "63"; cells[1] = "測試板CSV"
s, r = upload("/master/colors-import-csv", ("﻿" + lines[0] + "\n" + ",".join(cells) + "\nTEST10,新色,翰可,,,,70\n").encode("utf-8"), "c.csv"); log("csv import", s, r)
s, c = call("GET", "/master/colors/TEST9"); log("after import", c["board_name"], [(float(p["thickness"]), float(p["price"])) for p in c["prices"]])
s, c10 = call("GET", "/master/colors/TEST10"); log("TEST10", s, [(float(p["thickness"]), float(p["price"])) for p in c10["prices"]] if s == 200 else c10)
# delete in-use color refused
s, p = call("POST", "/projects", {"site_name": "master測試"}); pid = p["id"]
s, cb = call("POST", f"/projects/{pid}/cabinets", {"name": "櫃", "height": 1000, "depth": 500, "width": 800, "color_code": "TEST9"})
s, r = call("DELETE", "/master/colors/TEST9"); log("delete in-use color ->", s, str(r)[:40])
call("DELETE", f"/projects/{pid}")
s, r = call("DELETE", "/master/colors/TEST9"); log("delete unused color ->", s)
s, r = call("DELETE", "/master/colors/TEST10"); log("delete TEST10 ->", s)
# marks
s, m = call("POST", "/master/marks", {"name": "測試標記", "code": "T", "number": 99}); log("mark create", s)
s, r = call("PUT", f"/master/marks/{m['id']}", {"name": "測試標記2", "code": "T2", "number": 98}); log("mark update", s, r["name"])
s, r = call("DELETE", f"/master/marks/{m['id']}"); log("mark delete", s)
# hardware
s, h = call("POST", "/master/hardware", {"vendor": "V", "product_name": "測試五金", "list_price": 12.5}); log("hw create", s)
s, r = call("PUT", f"/master/hardware/{h['id']}", {"vendor": "V2", "product_name": "測試五金", "list_price": 13}); log("hw update", s, r["vendor"])
from urllib.parse import quote
s, r = call("GET", "/master/hardware?q=" + quote("測試五金")); log("hw search", len(r))
for x in r:
    s, _ = call("DELETE", f"/master/hardware/{x['id']}")
log("hw delete", s)
# vendors
s, v = call("POST", "/master/vendors", {"name": "測試廠商"}); log("vendor create", s)
s, r = call("POST", "/master/vendors", {"name": "測試廠商"}); log("vendor dup ->", s)
s, r = call("DELETE", f"/master/vendors/{v['id']}"); log("vendor delete", s)
# catalog
s, r = call("POST", "/master/parts-catalog", {"category": "外部", "name": "測試板件X"}); log("catalog add", s)
s, full = call("GET", "/master/parts-catalog/full"); item = next(x for x in full["外部"] if x["name"] == "測試板件X")
s, r = call("DELETE", f"/master/parts-catalog/{item['id']}"); log("catalog delete", s)
s, full = call("GET", "/master/parts-catalog"); log("catalog gone:", "測試板件X" not in full["外部"])
open(sys.argv[1], "w", encoding="utf-8").write("\n".join(out)); print("done")
