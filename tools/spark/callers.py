"""For frames matching a substring, show the top caller chains (deobfuscated) and top callees."""
import gzip, sys
from collections import defaultdict
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from analyze import fields, parse_thread, parse_map_entry
from report import load_yarn, deobf_cls, short, MIXIN

prof, tiny, *pats = sys.argv[1:]
classes, methods = load_yarn(tiny)
raw = open(prof, "rb").read(); raw = gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw
threads, class_src = [], {}
for f, _, v in fields(raw):
    if f == 2: threads.append(parse_thread(v))
    elif f == 3:
        k, val = parse_map_entry(v); class_src[k] = val
t = next(x for x in threads if x["name"] == "Server thread"); nodes = t["nodes"]
tot = [sum(n["times"]) for n in nodes]
busy = sum(tot[i] for i, n in enumerate(nodes) if n["cls"] == "net.minecraft.server.MinecraftServer" and n["meth"] == "method_3748")
parent = {}
for i, n in enumerate(nodes):
    for r in n["refs"]: parent[r] = i
def nm(i):
    n = nodes[i]; m = MIXIN.search(n["meth"])
    meth = f"<mixin {m.group(1)}:{m.group(2)}>" if m else methods.get(n["meth"], n["meth"])
    src = class_src.get(n["cls"]) or (m.group(1) if m else "")
    return f"{short(deobf_cls(n['cls'], classes))}.{meth}" + (f" [{src}]" if src else "")
SKIP = ("$$Lambda", "mixinextras$bridge", "neruina", "Pipeline", "ReduceOp", "Spliterator", "forEach", "Iterator", "lambda$")
for pat in pats:
    hits = [i for i in range(len(nodes)) if pat in nm(i)]
    # outermost matches only
    hs = set(hits); outer = [i for i in hits if not any(a in hs for a in iter(lambda c=[i]: (c.__setitem__(0, parent.get(c[0])) or c[0]), None))]
    total = sum(tot[i] for i in outer)
    print(f"\n#### {pat}: {total/busy*100:.2f}% of tick time")
    chains = defaultdict(float)
    for i in outer:
        path, j = [], parent.get(i)
        while j is not None and len(path) < 4:
            s = nm(j)
            if not any(k in s for k in SKIP): path.append(s)
            j = parent.get(j)
        chains[" <- ".join(path)] += tot[i]
    print("  called from:")
    for c, v in sorted(chains.items(), key=lambda x: -x[1])[:5]:
        print(f"    {v/busy*100:5.2f}%  {c}")
    callees = defaultdict(float)
    for i in outer:
        for r in nodes[i]["refs"]: callees[nm(r)] += tot[r]
    print("  calls into:")
    for c, v in sorted(callees.items(), key=lambda x: -x[1])[:5]:
        print(f"    {v/busy*100:5.2f}%  {c}")
