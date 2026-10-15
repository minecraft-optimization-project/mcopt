#!/usr/bin/env python3
"""Deterministic load scenario + local spark profile on the test server.

  bench.py run   --label NAME [--mobs 1500] [--seconds 180] [--warmup 45]
  bench.py start | stop | wait

The server dir is /root/mcopt/testserver (tmux session "mc"). Profiles are saved
with spark --save-to-file and copied to /root/mcopt/results/<label>.sparkprofile.
"""
import argparse, glob, os, random, shutil, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rcon import Rcon, props

SRV = "/root/mcopt/testserver"
RES = "/root/mcopt/results"
LOG = f"{SRV}/console.log"
# Area far from spawn, away from player-built terrain. 12x12 chunks.
X0, Z0, CH = 4096, 4096, 12
MOBS = [("minecraft:zombie", 4), ("minecraft:skeleton", 3), ("minecraft:cow", 3), ("minecraft:sheep", 3),
        ("minecraft:villager", 2), ("minecraft:pig", 2), ("minecraft:spider", 1), ("minecraft:chicken", 2)]

def rcon():
    p = props(f"{SRV}/server.properties")
    return Rcon("127.0.0.1", int(p["rcon.port"]), p["rcon.password"])

def running():
    return subprocess.run(["tmux", "has-session", "-t", "mc"], capture_output=True).returncode == 0

def start():
    if running(): return
    open(LOG, "a").write("\n=== bench start %s ===\n" % time.ctime())
    subprocess.run(["tmux", "new", "-d", "-s", "mc", f"{SRV}/run.sh"], check=True)
    subprocess.run(["tmux", "pipe-pane", "-t", "mc", f"cat >> {LOG}"], check=True)
    wait()

def wait(timeout=900):
    off = os.path.getsize(LOG)
    t = time.time()
    while time.time() - t < timeout:
        time.sleep(3)
        with open(LOG, errors="replace") as f:
            f.seek(off); tail = f.read()
        if "Done (" in tail:
            time.sleep(5); return
        if not running(): sys.exit("server exited during startup; see " + LOG)
    sys.exit("timeout waiting for server")

def stop():
    if not running(): return
    try: rcon().cmd("stop")
    except Exception: pass
    for _ in range(120):
        if not running(): return
        time.sleep(1)
    subprocess.run(["tmux", "kill-session", "-t", "mc"])

TEMPLATE = "/root/mcopt/world-template"

def make_template(a):
    """Generate a world with the bench area forceloaded and empty, then keep a pristine copy."""
    stop()
    shutil.rmtree(f"{SRV}/world", ignore_errors=True)
    start()
    r = rcon()
    for c in ["gamerule doMobSpawning false", "gamerule doDaylightCycle false", "gamerule doWeatherCycle false",
              "gamerule doTraderSpawning false", "gamerule doPatrolSpawning false", "gamerule doInsomnia false",
              "time set 6000", "weather clear", "difficulty normal",
              f"forceload add {X0} {Z0} {X0 + CH*16 - 1} {Z0 + CH*16 - 1}"]:
        r.cmd(c)
    time.sleep(60)
    r.cmd("kill @e[type=!minecraft:player]")
    time.sleep(5)
    r.cmd("save-all flush")
    stop()
    shutil.rmtree(TEMPLATE, ignore_errors=True)
    shutil.copytree(f"{SRV}/world", TEMPLATE)
    print("template saved:", TEMPLATE)

def run(a):
    if not os.path.isdir(TEMPLATE): sys.exit("no template world; run: bench.py template")
    stop()
    shutil.rmtree(f"{SRV}/world", ignore_errors=True)
    shutil.copytree(TEMPLATE, f"{SRV}/world")
    start()
    r = rcon()
    time.sleep(15)  # forceloaded area loads from disk
    r.cmd("kill @e[type=!minecraft:player]")
    rng = random.Random(1234)
    pool = [m for m, w in MOBS for _ in range(w)]
    for i in range(a.mobs):
        x = X0 + 8 + rng.random() * (CH*16 - 16); z = Z0 + 8 + rng.random() * (CH*16 - 16)
        r.cmd(f"execute positioned {x:.1f} 0 {z:.1f} positioned over motion_blocking_no_leaves run summon {rng.choice(pool)} ~ ~ ~ {{PersistenceRequired:1b}}")
    time.sleep(a.warmup)
    before = set(glob.glob(f"{SRV}/config/spark/*.sparkprofile"))
    r.cmd("spark profiler stop"); time.sleep(2)
    r.cmd("spark profiler start --interval 4"); 
    time.sleep(a.seconds)
    r.cmd("spark profiler stop --save-to-file")
    for _ in range(60):
        time.sleep(2)
        new = set(glob.glob(f"{SRV}/config/spark/*.sparkprofile")) - before
        if new: break
    else:
        sys.exit("no saved profile found under config/spark")
    os.makedirs(RES, exist_ok=True)
    dst = f"{RES}/{a.label}.sparkprofile"
    time.sleep(2); shutil.copy(max(new, key=os.path.getmtime), dst)
    print(r.cmd("execute if entity @e[type=!minecraft:player]").strip(), "| profile:", dst)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["run", "template", "start", "stop", "wait"])
    ap.add_argument("--label"); ap.add_argument("--mobs", type=int, default=1500)
    ap.add_argument("--seconds", type=int, default=180); ap.add_argument("--warmup", type=int, default=45)
    a = ap.parse_args()
    if a.action in ("run", "template"): {"run": run, "template": make_template}[a.action](a)
    else: {"start": start, "stop": stop, "wait": wait}[a.action]()
