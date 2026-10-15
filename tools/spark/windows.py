"""Per-minute window stats from a spark profile + frames that spiked in a given window."""
import gzip, struct, sys, datetime
from collections import defaultdict
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from analyze import fields, parse_thread, packed_ints, varint
from report import load_yarn, deobf_cls, short, MIXIN

STAT = {1: "ticks", 2: "cpu_proc", 3: "cpu_sys", 4: "tps", 5: "mspt_med", 6: "mspt_max", 7: "players", 8: "entities", 9: "tile_entities", 10: "chunks", 11: "start", 12: "end", 13: "duration"}

def parse_stats(b):
    d = {}
    for f, w, v in fields(b):
        if w == 1: v = struct.unpack("<d", v)[0]
        d[STAT.get(f, f)] = v
    return d

prof, tiny = sys.argv[1], sys.argv[2]
raw = open(prof, "rb").read()
raw = gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw
windows, stats, threads, class_src = [], {}, [], {}
for f, w, v in fields(raw):
    if f == 2: threads.append(parse_thread(v))
    elif f == 3:
        kv = dict((ff, vv.decode()) for ff, _, vv in fields(v)); class_src[kv.get(1, "")] = kv.get(2, "")
    elif f == 6: windows += packed_ints(v) if w == 2 else [v]
    elif f == 7:
        k = s = None
        for ff, ww, vv in fields(v):
            if ff == 1: k = vv
            elif ff == 2: s = parse_stats(vv)
        stats[k] = s
print("window(min)  local  players entities tiles chunks  tps  mspt_med mspt_max")
for i, wdx in enumerate(windows):
    s = stats.get(wdx, {})
    ts = datetime.datetime.fromtimestamp(wdx * 60).strftime("%H:%M")
    print(f"{i:2} {wdx} {ts}  {s.get('players','?'):>4} {s.get('entities','?'):>8} {s.get('tile_entities','?'):>6} {s.get('chunks','?'):>6}  {s.get('tps',0):5.2f} {s.get('mspt_med',0):7.1f} {s.get('mspt_max',0):8.1f}")
spike = int(sys.argv[3]) if len(sys.argv) > 3 else max(range(len(windows)), key=lambda i: stats.get(windows[i], {}).get("mspt_max", 0))
print(f"\n== frames over-represented in window {spike} vs average of others (ms, self+callee inclusive, outermost per frame)")
classes, methods = load_yarn(tiny)
t = next(x for x in threads if x["name"] == "Server thread")
nodes = t["nodes"]
def nm(n):
    m = MIXIN.search(n["meth"])
    meth = f"<mixin {m.group(1)}:{m.group(2)}>" if m else methods.get(n["meth"], n["meth"])
    return f"{short(deobf_cls(n['cls'], classes))}.{meth}  [{class_src.get(n['cls'], m.group(1) if m else '')}]"
incl = defaultdict(lambda: [0.0] * len(windows))
stack = [(i, frozenset()) for i in t["refs"]]
while stack:
    i, seen = stack.pop()
    k = nm(nodes[i])
    if k not in seen:
        for wi, tv in enumerate(nodes[i]["times"]): incl[k][wi] += tv
    stack.extend((r, seen | {k}) for r in nodes[i]["refs"])
rows = []
for k, ts in incl.items():
    others = (sum(ts) - ts[spike]) / max(len(ts) - 1, 1)
    rows.append((ts[spike] - others, ts[spike], others, k))
for d, s, o, k in sorted(rows, reverse=True)[:40]:
    print(f"{d:9.0f} (window {s:8.0f} vs avg {o:7.0f})  {k}")
