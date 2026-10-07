#!/usr/bin/env python3
"""
kdbox_rng_stratum.py

A tiny local stratum (v1) server that turns a Goldshell KD-Box II into a
self-contained hardware entropy source / number randomizer, with no internet,
no real coin, and no pool.

How it works:
  The box's blake2s ASIC (36 chips / 3240 cores) can only do one thing: search
  the 32-bit nonce of an ~80-byte header for a blake2s digest under a target.
  This server hands the box a header we control at a low difficulty, so the
  chip streams back nonces whose blake2s hash meets that target. Each returned
  nonce is an unpredictable draw from the hardware. We fold those into a SHA-256
  entropy pool and squeeze random bytes / numbers out of it.

  So the "dead" miner becomes a blake2s-backed RNG faucet.

Usage (on the PC the box can reach on the LAN):
  python kdbox_rng_stratum.py --port 3333 --diff 0.0005

Then point the box's miner at stratum+tcp://<this-pc-ip>:3333 (see the companion
json/run script). Watch it subscribe, get work, and submit nonces; this server
prints the live random stream and writes raw random bytes to rng_out.bin.

This is a demo / toy RNG. It is a legitimate physical entropy source (the timing
and values of hardware nonce hits are not predictable), but it is not certified;
do not use it to protect anything that matters without proper evaluation.
"""
import argparse, hashlib, json, os, socket, struct, threading, time, sys

def h2(b): return b.hex()

class Pool:
    """SHA-256 entropy pool fed by hardware nonces."""
    def __init__(self, outpath):
        self.state = hashlib.sha256(b"kdbox-rng-" + os.urandom(16)).digest()
        self.count = 0
        self.lock = threading.Lock()
        self.out = open(outpath, "ab", buffering=0) if outpath else None
    def feed(self, *parts):
        with self.lock:
            h = hashlib.sha256()
            h.update(self.state)
            for p in parts:
                h.update(p if isinstance(p, (bytes, bytearray)) else str(p).encode())
            self.state = h.digest()
            self.count += 1
            if self.out:
                self.out.write(self.state)   # 32 fresh random bytes per hit
            return self.state
    def rand_u32(self):
        return struct.unpack("<I", self.state[:4])[0]

class StratumServer:
    def __init__(self, host, port, diff, pool, quiet=False):
        self.host, self.port, self.diff, self.pool = host, port, diff, pool
        self.quiet = quiet
        self.job = 0
        self.extranonce1 = "0000"            # 2 bytes we assign
        self.en2size = 4
        self.submits = 0
        self.start = time.time()

    def log(self, *a):
        if not self.quiet:
            print("[srv]", *a, flush=True)

    def notify(self, clean=True):
        """Build a mining.notify job. Fields are standard stratum v1; the exact
        content does not matter for an RNG, only that the box builds an 80-byte
        header and hashes it. ntime advances so repeated jobs differ."""
        self.job += 1
        jid = "%x" % self.job
        prevhash = "00" * 32
        coinb1 = "01000000010000000000000000000000000000000000000000000000000000000000000000ffffffff"
        coinb2 = "ffffffff0100f2052a01000000000000000000"
        merkle = []
        version = "20000000"
        nbits   = "1e0fffff"
        ntime   = "%08x" % int(time.time())
        return {"id": None, "method": "mining.notify",
                "params": [jid, prevhash, coinb1, coinb2, merkle, version, nbits, ntime, clean]}

    def send(self, conn, obj):
        conn.sendall((json.dumps(obj) + "\n").encode())

    def handle(self, conn, addr):
        self.log("miner connected:", addr)
        conn.settimeout(120)
        buf = b""
        subscribed = False
        def job_pusher():
            # keep work fresh so the chip never idles
            while True:
                time.sleep(25)
                try: self.send(conn, self.notify(clean=False))
                except Exception: return
        pusher_started = False
        try:
            while True:
                try:
                    data = conn.recv(4096)
                except socket.timeout:
                    continue
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                    except Exception:
                        continue
                    m = msg.get("method")
                    mid = msg.get("id")
                    if m == "mining.subscribe":
                        self.send(conn, {"id": mid, "result": [
                            [["mining.set_difficulty", "1"], ["mining.notify", "1"]],
                            self.extranonce1, self.en2size], "error": None})
                        self.send(conn, {"id": None, "method": "mining.set_difficulty",
                                         "params": [self.diff]})
                        self.send(conn, self.notify(clean=True))
                        subscribed = True
                        if not pusher_started:
                            threading.Thread(target=job_pusher, daemon=True).start()
                            pusher_started = True
                        self.log("subscribed; diff=%s" % self.diff)
                    elif m == "mining.authorize":
                        self.send(conn, {"id": mid, "result": True, "error": None})
                        self.log("authorized:", (msg.get("params") or [""])[0])
                    elif m == "mining.configure":
                        self.send(conn, {"id": mid, "result": {}, "error": None})
                    elif m == "mining.suggest_difficulty":
                        self.send(conn, {"id": mid, "result": True, "error": None})
                    elif m == "mining.submit":
                        p = msg.get("params", [])
                        # [worker, job_id, extranonce2, ntime, nonce]
                        en2   = p[2] if len(p) > 2 else ""
                        ntime = p[3] if len(p) > 3 else ""
                        nonce = p[4] if len(p) > 4 else ""
                        try:
                            nbytes = bytes.fromhex(nonce)
                        except Exception:
                            nbytes = nonce.encode()
                        st = self.pool.feed(nbytes, en2, ntime, time.time_ns())
                        self.submits += 1
                        self.send(conn, {"id": mid, "result": True, "error": None})
                        if self.submits <= 5 or self.submits % 10 == 0:
                            u = struct.unpack("<I", st[:4])[0]
                            rate = self.submits / max(1e-9, time.time() - self.start)
                            self.log("hw nonce #%d  nonce=0x%s  ->  random: d20=%d  0-99=%d  u32=%u  (%.1f/s)"
                                     % (self.submits, nonce, (u % 20) + 1, u % 100, u, rate))
                    else:
                        if mid is not None:
                            self.send(conn, {"id": mid, "result": True, "error": None})
        finally:
            self.log("miner disconnected:", addr, "total hw nonces:", self.submits)

    def serve(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((self.host, self.port))
        s.listen(5)
        self.log("listening on %s:%d  diff=%s  (point the box's miner here)"
                 % (self.host, self.port, self.diff))
        while True:
            conn, addr = s.accept()
            threading.Thread(target=self.handle, args=(conn, addr), daemon=True).start()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=3333)
    ap.add_argument("--diff", type=float, default=0.0005,
                    help="stratum share difficulty; lower = more nonces/sec = faster RNG")
    ap.add_argument("--out", default="rng_out.bin", help="append raw random bytes here")
    args = ap.parse_args()
    pool = Pool(args.out)
    StratumServer(args.host, args.port, args.diff, pool).serve()

if __name__ == "__main__":
    main()
