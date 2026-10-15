"""Minimal decoder for spark sampler protobuf (spark 1.10.x) -> per-mod self time + hot frames."""
import gzip
import struct
import sys
from collections import defaultdict


def varint(b, i):
    r = s = 0
    while True:
        c = b[i]
        i += 1
        r |= (c & 0x7F) << s
        if c < 0x80:
            return r, i
        s += 7


def fields(b):
    """Yield (field_no, wire_type, value) for a message buffer."""
    i, n = 0, len(b)
    while i < n:
        k, i = varint(b, i)
        f, w = k >> 3, k & 7
        if w == 0:
            v, i = varint(b, i)
        elif w == 1:
            v = b[i:i + 8]
            i += 8
        elif w == 2:
            ln, i = varint(b, i)
            v = b[i:i + ln]
            i += ln
        elif w == 5:
            v = b[i:i + 4]
            i += 4
        else:
            raise ValueError(f"wire type {w}")
        yield f, w, v


def packed_doubles(v):
    return list(struct.unpack(f"<{len(v)//8}d", v))


def packed_ints(v):
    out, i = [], 0
    while i < len(v):
        x, i = varint(v, i)
        out.append(x)
    return out


def parse_node(b):
    n = {"cls": "", "meth": "", "times": [], "refs": []}
    for f, w, v in fields(b):
        if f == 3:
            n["cls"] = v.decode()
        elif f == 4:
            n["meth"] = v.decode()
        elif f == 8:
            n["times"] += packed_doubles(v) if w == 2 else [struct.unpack("<d", v)[0]]
        elif f == 9:
            n["refs"] += packed_ints(v) if w == 2 else [v]
    return n


def parse_thread(b):
    t = {"name": "", "nodes": [], "times": [], "refs": []}
    for f, w, v in fields(b):
        if f == 1:
            t["name"] = v.decode()
        elif f == 3:
            t["nodes"].append(parse_node(v))
        elif f == 4:
            t["times"] += packed_doubles(v) if w == 2 else [struct.unpack("<d", v)[0]]
        elif f == 5:
            t["refs"] += packed_ints(v) if w == 2 else [v]
    return t


def parse_map_entry(b):
    k = val = ""
    for f, w, v in fields(b):
        if f == 1:
            k = v.decode()
        elif f == 2:
            val = v.decode()
    return k, val


def main(path):
    raw = open(path, "rb").read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    threads, class_src = [], {}
    for f, w, v in fields(raw):
        if f == 2:
            threads.append(parse_thread(v))
        elif f == 3:
            k, val = parse_map_entry(v)
            class_src[k] = val
    for t in threads:
        nodes = t["nodes"]
        total = sum(t["times"])
        print(f"== thread {t['name']!r}: {len(nodes)} nodes, total {total/1000:.1f}s sampled")
        by_mod = defaultdict(float)
        by_frame = defaultdict(float)
        for nd in nodes:
            tot = sum(nd["times"])
            child = sum(sum(nodes[r]["times"]) for r in nd["refs"])
            self_t = max(tot - child, 0.0)
            by_mod[class_src.get(nd["cls"], "minecraft/java")] += self_t
            by_frame[f"{nd['cls']}.{nd['meth']}"] += self_t
        print("-- self time by mod (top 25)")
        for m, v in sorted(by_mod.items(), key=lambda x: -x[1])[:25]:
            print(f"{v/total*100:6.2f}%  {m}")
        print("-- hottest frames by self time (top 25)")
        for m, v in sorted(by_frame.items(), key=lambda x: -x[1])[:25]:
            src = class_src.get(m.rsplit(".", 1)[0], "")
            print(f"{v/total*100:6.2f}%  {m}  [{src}]")


if __name__ == "__main__":
    main(sys.argv[1])


import re

HANDLER = re.compile(r"(?:handler|redirect|wrapOperation|modify\w*|localvar|md[0-9a-f]{6})\$[a-z0-9]{6,7}\$([a-z0-9_\-]+)\$")
KNOWN = {  # 1.20.1 intermediary -> mojmap names for common tick frames
    "net.minecraft.server.MinecraftServer.method_3748": "MinecraftServer.tickServer",
    "net.minecraft.server.MinecraftServer.method_3813": "MinecraftServer.tickChildren",
    "net.minecraft.class_3218.method_18765": "ServerLevel.tick",
    "net.minecraft.class_3218.method_18762": "ServerLevel.tickNonPassenger (entity tick)",
    "net.minecraft.class_3218.method_18763": "ServerLevel.tickPassenger",
    "net.minecraft.class_1937.method_18471": "Level.tickBlockEntities",
    "net.minecraft.class_3215.method_12127": "ServerChunkCache.tick",
    "net.minecraft.class_3215.method_14161": "ServerChunkCache.tickChunks",
    "net.minecraft.class_3218.method_18203": "ServerLevel.tickChunk (random ticks/weather)",
    "net.minecraft.class_1948.method_8663": "NaturalSpawner.spawnForChunk",
    "net.minecraft.class_3898.method_17233": "ChunkMap.tick",
    "net.minecraft.class_3204.method_15892": "DistanceManager.runAllUpdates",
    "net.minecraft.server.MinecraftServer.method_16208": "MinecraftServer.waitUntilNextTick (idle)",
    "net.minecraft.class_3324.method_14571": "PlayerList.tick",
    "net.minecraft.server.MinecraftServer.method_3723": "MinecraftServer.saveEverything (autosave)",
}


def owner_of(nd, class_src):
    if nd["cls"] in class_src:
        return class_src[nd["cls"]]
    m = HANDLER.search(nd["meth"])
    return m.group(1) if m else None


def busy_breakdown(path, top=30):
    raw = open(path, "rb").read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    threads, class_src = [], {}
    for f, w, v in fields(raw):
        if f == 2:
            threads.append(parse_thread(v))
        elif f == 3:
            k, val = parse_map_entry(v)
            class_src[k] = val
    t = [x for x in threads if x["name"] == "Server thread"][0]
    nodes = t["nodes"]
    tot = lambda i: sum(nodes[i]["times"])
    key = lambda i: f"{nodes[i]['cls']}.{nodes[i]['meth']}"
    # find tickServer subtree roots
    roots = [i for i in range(len(nodes)) if key(i) == "net.minecraft.server.MinecraftServer.method_3748"]
    busy = sum(tot(i) for i in roots)
    wall = sum(t["times"])
    print(f"\n== busy time inside tickServer: {busy/1000:.1f}s of {wall/1000:.1f}s wall ({busy/wall*100:.1f}%)")
    by_owner = defaultdict(float)
    stack = [(i, None) for i in roots]
    while stack:
        i, own = stack.pop()
        nd = nodes[i]
        o = owner_of(nd, class_src) or own
        child = sum(tot(r) for r in nd["refs"])
        by_owner[o or "vanilla"] += max(tot(i) - child, 0.0)
        stack.extend((r, o) for r in nd["refs"])
    print("-- busy time attributed to nearest mod in stack")
    for m, v in sorted(by_owner.items(), key=lambda x: -x[1])[:top]:
        print(f"{v/busy*100:6.2f}%  {m}")
    print("-- tick phase tree (>=2% of busy)")
    def walk(i, depth):
        if depth > 7:
            return
        for r in sorted(nodes[i]["refs"], key=lambda r: -tot(r)):
            share = tot(r) / busy * 100
            if share < 2:
                continue
            k = key(r)
            label = KNOWN.get(k, k)
            o = owner_of(nodes[r], class_src)
            print(f"{'  '*depth}{share:5.1f}%  {label}{'  ['+o+']' if o else ''}")
            walk(r, depth + 1)
    for i in roots:
        walk(i, 0)


if __name__ == "__main__":
    busy_breakdown(sys.argv[1])


def entity_breakdown(path, top=30):
    raw = open(path, "rb").read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    threads, class_src = [], {}
    for f, w, v in fields(raw):
        if f == 2:
            threads.append(parse_thread(v))
        elif f == 3:
            k, val = parse_map_entry(v)
            class_src[k] = val
    t = [x for x in threads if x["name"] == "Server thread"][0]
    nodes = t["nodes"]
    tot = lambda i: sum(nodes[i]["times"])
    busy = sum(tot(i) for i in range(len(nodes)) if nodes[i]["cls"] == "net.minecraft.server.MinecraftServer" and nodes[i]["meth"] == "method_3748")
    # Entity.tick() = method_5773; count outermost occurrence per stack only
    has_tick_anc = set()
    by_cls = defaultdict(float)
    stack = [(i, False) for i in t["refs"]]
    while stack:
        i, inside = stack.pop()
        nd = nodes[i]
        is_tick = nd["meth"] == "method_5773"
        if is_tick and not inside:
            by_cls[nd["cls"]] += tot(i)
        stack.extend((r, inside or is_tick) for r in nd["refs"])
    print("\n-- Entity.tick() time by entity class (% of busy)")
    for c, v in sorted(by_cls.items(), key=lambda x: -x[1])[:top]:
        print(f"{v/busy*100:6.2f}%  {c}  [{class_src.get(c, 'vanilla')}]")


if __name__ == "__main__":
    entity_breakdown(sys.argv[1])
