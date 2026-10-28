import json, sys, uuid, urllib.request

BASE = "http://localhost:8100/api"
out = []
log = lambda *a: out.append(" ".join(str(x) for x in a))


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method, headers={"Content-Type": "application/json"},
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req) as r:
            t = r.read().decode(); return r.status, (json.loads(t) if t else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def upload(path, filepath, ctype):
    b = uuid.uuid4().hex
    name = filepath.split("\\")[-1].split("/")[-1]
    data = open(filepath, "rb").read()
    body = (f"--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\nContent-Type: {ctype}\r\n\r\n").encode() + data + f"\r\n--{b}--\r\n".encode()
    req = urllib.request.Request(BASE + path, method="POST", data=body, headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


xlsx, pdf = sys.argv[1], sys.argv[2]
s, r = upload("/projects/import-xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"); log("import", s, r)
pid = r["project_id"]
s, p = call("GET", f"/projects/{pid}")
log("project", p["order_no"], p["site_name"], p["designer"], p["order_date"], p["delivery_date"], "joint", p["joint_type"], "thick", p["board_thickness"], "cabs", len(p["cabinets"]))
for cb in p["cabinets"][:3]:
    log(" cab", cb["cabinet_no"], cb["name"], cb["height"], cb["depth"], cb["width"], "color", cb["color_code"], "parts", len(cb["parts"]))
    for x in cb["parts"][:9]:
        log("   ", x["part_no"], x["category"], x["name"], x["length"], repr(x["edge_l"]), x["width"], repr(x["edge_w"]), x["thickness"], x["qty"], x["color_code"], x["color_name"], "|", x["mark_p"], "|", x["mark_q"], "|", x["mark_r"], "|", x["remark"], "|", x["reminder"], "manual=", x["manual_fields"], "cai=", x["area_cai"], "amt=", x["amount"])
cb3 = p["cabinets"][2]
log(" cab3 part edges:", [(x["name"], x["edge_l"], x["edge_w"], x["manual_fields"]) for x in cb3["parts"][:5]])
# upload pdf
s, a = upload(f"/projects/{pid}/attachments?kind=drawing&note=test", pdf, "application/pdf"); log("upload pdf", s, a if s != 201 else (a["id"], a["filename"], a["page_count"], a["size"]))
aid = a["id"]
req = urllib.request.Request(f"{BASE}/attachments/{aid}/pages/3.png?dpi=60")
with urllib.request.urlopen(req) as r:
    png = r.read(); log("page3 png bytes", len(png), r.headers.get("content-type"))
# link cabinet 1 to page 1
cb1 = p["cabinets"][0]
s, r = call("PUT", f"/cabinets/{cb1['id']}", {"name": cb1["name"], "height": cb1["height"], "depth": cb1["depth"], "width": cb1["width"], "batch": cb1["batch"], "note": cb1["note"], "color_code": cb1["color_code"], "drawing_attachment_id": aid, "drawing_page": 1, "drawing_label": "①", "generate_default_parts": False})
log("link drawing", s, r["drawing_attachment_id"], r["drawing_page"], r["drawing_label"])
# duplicate + apply color + manual field edit + reset
s, d = call("POST", f"/cabinets/{cb1['id']}/duplicate"); log("duplicate", s, d["cabinet_no"], len(d["parts"]), d["parts"][0]["part_no"])
s, r = call("POST", f"/cabinets/{d['id']}/apply-color", {"color_code": "2330"}); log("apply color", s, {x["name"]: x["color_code"] for x in r[:6]})
x = d["parts"][0]
body = {k: x[k] for k in ("category", "name", "length", "width", "thickness", "qty", "color_code", "remark", "status_code", "edge_l", "edge_w", "mark_p", "mark_q", "mark_r", "reminder")}
body["edge_l"] = "A"; body["mark_q"] = "右凸5mm"; body["manual_fields"] = ["edge_l", "mark_q"]
s, r = call("PUT", f"/parts/{x['id']}", body); log("manual edit", s, r["edge_l"], r["mark_q"], r["manual_fields"])
s, r = call("POST", f"/parts/{x['id']}/reset-auto"); log("reset", s, r["edge_l"], r["mark_q"], r["manual_fields"])
# free-text name w/o category → inferred
s, r = call("POST", f"/cabinets/{d['id']}/parts", {"name": "踢腳板", "length": 2400, "width": 120, "qty": 1}); log("infer cat", s, r["category"], r["thickness"], r["color_code"], r["edge_l"], r["edge_w"])
s, r = call("POST", f"/cabinets/{d['id']}/parts", {"name": "美背", "length": 700, "width": 900}); log("unknown name", s, r["category"], r["edge_l"])
s, sm = call("GET", f"/projects/{pid}/summary"); log("summary", sm["total_pieces"], sm["total_cai"], sm["total_amount"])
s, mt = call("GET", f"/projects/{pid}/material"); log("material boards", [(b["color_code"], b["thickness"], b["pieces"], round(float(b["cai"]), 1), round(float(b["edge_band_mm"]) / 1000, 1)) for b in mt["boards"]], "hw", len(mt["hardware"]))
s, lb = call("GET", f"/projects/{pid}/labels"); log("labels", len(lb))
s, se = call("GET", f"/projects/{pid}/serials"); log("serials", len(se))
s, lst = call("GET", "/projects"); log("list", [(x["order_no"], x["cabinet_count"], x["piece_count"], x["attachment_count"]) for x in lst])
# cleanup duplicate cabinet
call("DELETE", f"/cabinets/{d['id']}")
open(sys.argv[3], "w", encoding="utf-8").write("\n".join(out))
print("done")
