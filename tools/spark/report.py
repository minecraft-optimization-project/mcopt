"""Per-mod tick cost report from a spark sampler profile, with Yarn-deobfuscated frames.

usage: python3 -I report.py <profile.bin> <yarn mappings.tiny> [top_mods]
"""
import gzip
import re
import sys
from collections import defaultdict

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from analyze import fields, parse_map_entry, parse_thread  # noqa: E402

TICK_SERVER = ("net.minecraft.server.MinecraftServer", "method_3748")
ENTITY_TICK = "method_5773"
MIXIN = re.compile(r"(?:handler|redirect|wrapOperation|wrapWithCondition|modify\w*|localvar)\$[a-z0-9]{6,7}\$([a-z0-9_\-]+)\$(\w+)")
# Mods that only dispatch or wrap other code; time passes through them to the real owner.
TRANSPARENT = re.compile(r"^(neruina|fabric-.*|fabricloader|architectury|mixinextras|cardinal-components.*)$")


def load_yarn(path):
    classes, methods = {}, {}
    cur = None
    for line in open(path):
        p = line.rstrip("\n").split("\t")
        if p[0] == "c":
            cur = p[1]
            classes[p[1].replace("/", ".")] = p[2].replace("/", ".")
        elif len(p) >= 5 and p[1] == "m":
            methods[p[3]] = p[4]
    return classes, methods


def deobf_cls(c, classes):
    outer, _, inner = c.partition("$$Lambda")
    parts = outer.split("$")
    for i in range(len(parts), 0, -1):
        k = "$".join(parts[:i])
        if k in classes:
            named = classes[k] + ("$" + "$".join(parts[i:]) if parts[i:] else "")
            return named + ("$$Lambda" if inner else "")
    return c


def short(c):
    return c.rsplit(".", 1)[-1]


def main(prof, tiny, top_mods=15):
    classes, methods = load_yarn(tiny)
    raw = open(prof, "rb").read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    threads, class_src = [], {}
    for f, _, v in fields(raw):
        if f == 2:
            threads.append(parse_thread(v))
        elif f == 3:
            k, val = parse_map_entry(v)
            class_src[k] = val
    t = next(x for x in threads if x["name"] == "Server thread")
    nodes = t["nodes"]
    tot = [sum(n["times"]) for n in nodes]

    def name(i):
        n = nodes[i]
        m = MIXIN.search(n["meth"])
        meth = f"<mixin {m.group(1)}:{m.group(2)}>" if m else methods.get(n["meth"], n["meth"])
        return f"{short(deobf_cls(n['cls'], classes))}.{meth}"

    def owner(i):
        n = nodes[i]
        o = class_src.get(n["cls"])
        if not o:
            m = MIXIN.search(n["meth"])
            o = m.group(1) if m else None
        return None if (o and TRANSPARENT.match(o)) else o

    roots = [i for i, n in enumerate(nodes) if (n["cls"], n["meth"]) == TICK_SERVER]
    busy = sum(tot[i] for i in roots)
    wall = sum(t["times"])
    print(f"busy {busy/1000:.1f}s / wall {wall/1000:.1f}s = {busy/wall*100:.1f}% (avg {busy/wall*50:.1f} ms of 50 ms tick budget)")

    by_mod = defaultdict(float)          # self time attributed to nearest owning mod
    entry = defaultdict(lambda: defaultdict(float))   # mod -> outermost frame of that mod -> inclusive time
    leaf = defaultdict(lambda: defaultdict(float))    # mod -> hottest self-time frame under it
    ent = defaultdict(float)
    stack = [(i, None, False) for i in roots]
    while stack:
        i, own, in_tick = stack.pop()
        o = owner(i) or own
        if o and o != own:
            entry[o][name(i)] += tot[i]
        selft = max(tot[i] - sum(tot[r] for r in nodes[i]["refs"]), 0.0)
        by_mod[o or "vanilla"] += selft
        if o:
            leaf[o][name(i)] += selft
        is_tick = nodes[i]["meth"] == ENTITY_TICK
        if is_tick and not in_tick:
            ent[(deobf_cls(nodes[i]["cls"], classes), class_src.get(nodes[i]["cls"], "vanilla"))] += tot[i]
        stack.extend((r, o, in_tick or is_tick) for r in nodes[i]["refs"])

    pct = lambda v: f"{v/busy*100:5.2f}%"
    print("\n## Tick time by mod (pass-through wrappers excluded)")
    for m, v in sorted(by_mod.items(), key=lambda x: -x[1])[:30]:
        print(f"{pct(v)}  {m}")
    print("\n## Entity.tick() by entity type")
    for (c, src), v in sorted(ent.items(), key=lambda x: -x[1])[:25]:
        print(f"{pct(v)}  {short(c)}  [{src}]")
    print(f"\n## Where the time goes inside the top {top_mods} mods")
    for m, v in sorted(((k, v) for k, v in by_mod.items() if k != "vanilla"), key=lambda x: -x[1])[:top_mods]:
        print(f"\n### {m}  ({pct(v)} of tick time)")
        print("  entry points (inclusive):")
        for k, x in sorted(entry[m].items(), key=lambda x: -x[1])[:4]:
            print(f"    {pct(x)}  {k}")
        print("  hottest frames (self):")
        for k, x in sorted(leaf[m].items(), key=lambda x: -x[1])[:4]:
            print(f"    {pct(x)}  {k}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 15)
