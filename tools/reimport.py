import json, sys, urllib.request, uuid
B = "http://localhost:8100/api"
pid_old, xlsx = sys.argv[1], sys.argv[2]
if pid_old != "0":
    urllib.request.urlopen(urllib.request.Request(f"{B}/projects/{pid_old}", method="DELETE")).read()
b = uuid.uuid4().hex
data = open(xlsx, "rb").read()
body = (f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="jinshan.xlsx"\r\nContent-Type: application/octet-stream\r\n\r\n').encode() + data + f"\r\n--{b}--\r\n".encode()
r = json.loads(urllib.request.urlopen(urllib.request.Request(f"{B}/projects/import-xlsx", data=body, headers={"Content-Type": f"multipart/form-data; boundary={b}"})).read())
print("import", r)
s = json.loads(urllib.request.urlopen(f"{B}/projects/{r['project_id']}/summary").read())
print("pieces", s["total_pieces"], "cai", s["total_cai"], "amount", s["total_amount"])
m = json.loads(urllib.request.urlopen(f"{B}/projects/{r['project_id']}/material").read())
print([(x["color_code"], float(x["thickness"] or 0), x["pieces"]) for x in m["boards"]])
