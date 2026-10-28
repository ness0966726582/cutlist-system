import sys, zipfile, re
for path in sys.argv[1:]:
    z = zipfile.ZipFile(path)
    names = z.namelist()
    print("==", path)
    print("entries:", len(names))
    for n in names:
        if n.startswith("xl/worksheets/sheet") or n in ("xl/workbook.xml", "xl/styles.xml", "xl/sharedStrings.xml") or "vba" in n.lower() or "chart" in n.lower() or "drawing" in n.lower() or "pivot" in n.lower() or "table" in n.lower() or "extern" in n.lower() or "query" in n.lower() or "connection" in n.lower():
            print(f"  {n}  {z.getinfo(n).file_size}")
    wbxml = z.read("xl/workbook.xml").decode("utf-8", "ignore")
    print("  sheets:", re.findall(r'<sheet [^>]*name="([^"]+)"[^>]*', wbxml))
    print("  hidden:", re.findall(r'<sheet [^>]*name="([^"]+)"[^>]*state="(\w+)"', wbxml))
    print("  calcPr:", re.findall(r'<calcPr[^>]*/>', wbxml))
