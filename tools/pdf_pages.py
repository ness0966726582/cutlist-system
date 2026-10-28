import sys, os
sys.path.append(r"C:\Users\MTK_d\AppData\Roaming\Python\Python313\site-packages")
import pymupdf

pdf, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)
doc = pymupdf.open(pdf)
print("pages", len(doc))
for i, p in enumerate(doc):
    t = p.get_text()
    print(i + 1, int(p.rect.width), int(p.rect.height), "chars", len(t), "images", len(p.get_images()))
    pix = p.get_pixmap(dpi=55)
    pix.save(os.path.join(outdir, f"p{i+1:02d}.png"))
    with open(os.path.join(outdir, f"p{i+1:02d}.txt"), "w", encoding="utf-8") as f:
        f.write(t)
