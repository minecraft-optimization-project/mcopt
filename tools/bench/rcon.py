#!/usr/bin/env python3
"""Minimal Source RCON client. Usage: rcon.py [--props server.properties] "cmd" ["cmd" ...]"""
import socket, struct, sys, re, os, time

def props(path):
    d = {}
    for line in open(path):
        if "=" in line and not line.startswith("#"):
            k, v = line.rstrip("\n").split("=", 1); d[k] = v
    return d

class Rcon:
    def __init__(self, host, port, pw):
        self.s = socket.create_connection((host, port), timeout=600)
        self.id = 0
        if self.cmd(pw, 3) is None: raise SystemExit("rcon auth failed")
    def _send(self, kind, body):
        self.id += 1
        data = struct.pack("<ii", self.id, kind) + body.encode() + b"\0\0"
        self.s.sendall(struct.pack("<i", len(data)) + data)
        return self.id
    def _recv(self):
        n = struct.unpack("<i", self._read(4))[0]
        data = self._read(n)
        rid, kind = struct.unpack("<ii", data[:8])
        return rid, data[8:-2].decode(errors="replace")
    def _read(self, n):
        b = b""
        while len(b) < n:
            c = self.s.recv(n - len(b))
            if not c: raise ConnectionError("closed")
            b += c
        return b
    def cmd(self, body, kind=2):
        rid = self._send(kind, body)
        r, out = self._recv()
        if kind == 3: return None if r == -1 else out
        return out

if __name__ == "__main__":
    args = sys.argv[1:]
    p = "/root/mcopt/testserver/server.properties"
    if args[:1] == ["--props"]: p, args = args[1], args[2:]
    pr = props(p)
    r = Rcon("127.0.0.1", int(pr["rcon.port"]), pr["rcon.password"])
    for c in args:
        print(r.cmd(c))
