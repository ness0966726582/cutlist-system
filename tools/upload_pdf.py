import json, sys, urllib.request, uuid
B = "http://localhost:8100/api"
pid, pdf = sys.argv[1], sys.argv[2]
b = uuid.uuid4().hex
data = open(pdf, "rb").read()
body = (f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="20261016 新竹金山街.pdf"\r\nContent-Type: application/pdf\r\n\r\n').encode("utf-8") + data + f"\r\n--{b}--\r\n".encode()
r = json.loads(urllib.request.urlopen(urllib.request.Request(f"{B}/projects/{pid}/attachments?kind=drawing", data=body, headers={"Content-Type": f"multipart/form-data; boundary={b}"})).read())
print(r["id"], r["page_count"])
# 依 PDF 頁面對應櫃體 (玄關 p1: 1,2 / 樓梯 p2: 3,4,5 / 餐邊 p3: 6-14 / p5: 18)
p = json.loads(urllib.request.urlopen(f"{B}/projects/{pid}").read())
page_of = {1: 1, 2: 1, 3: 2, 4: 2, 5: 2, **{n: 3 for n in range(6, 15)}, 18: 5}
circ = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
for cb in p["cabinets"]:
    pg = page_of.get(cb["cabinet_no"])
    if not pg:
        continue
    body = {k: cb[k] for k in ("name", "cabinet_no", "height", "depth", "width", "batch", "note", "color_code")}
    body.update(drawing_attachment_id=r["id"], drawing_page=pg, drawing_label=circ[cb["cabinet_no"] - 1] if cb["cabinet_no"] <= 20 else None, generate_default_parts=False)
    urllib.request.urlopen(urllib.request.Request(f"{B}/cabinets/{cb['id']}", method="PUT", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})).read()
print("linked")
