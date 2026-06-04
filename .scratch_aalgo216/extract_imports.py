import re, pathlib
text = pathlib.Path(".scratch_aalgo216/imports_raw.txt").read_text()
syms = set()
for line in text.splitlines():
    m = re.match(r"^[^:]+:\d+:(.*)$", line)
    if not m:
        continue
    code = m.group(1).strip()
    m2 = re.match(r"from\s+[\w.]+\s+import\s+(.+)$", code)
    if m2:
        rhs = m2.group(1).strip().rstrip("(\\")
        rhs = re.sub(r"[()\\]", " ", rhs)
        for part in rhs.split(","):
            name = part.strip().split(" as ")[0].strip()
            if name and not (name == "*"):
                syms.add(name)
        continue
    m3 = re.match(r"import\s+(.+)$", code)
    if m3:
        for p in m3.group(1).split(","):
            syms.add(p.strip().split(" as ")[0].split(".")[-1])
for s in sorted(syms):
    print(s)
