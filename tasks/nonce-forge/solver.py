#!/usr/bin/env python3
"""
Reference solution for the nonce-forge task.

Chains the five intended stages and prints the flag; optionally writes a
machine-readable transcript for the grader.

  1. Recon        GET  /api/spec         -> required claim + reserved ids
  2. Pubkey        GET  /api/pubkey       -> curve + fleet public point Q
  3. Collect       POST /api/attest  x2   -> two signatures sharing nonce k
  4. Recover+forge (local) nonce-reuse algebra recovers the private key;
                   sign the required claim with a fresh nonce
  5. Redeem        POST /api/redeem       -> flag

Usage:
    python solver.py --base URL [--transcript PATH] [--quiet]
"""
import argparse
import json
import pathlib
import random
import re
import sys
import time

import requests
from ecdsa import NIST256p
from ecdsa.ellipticcurve import Point

try:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))  # repo root
    from harness.transcript import Recorder  # noqa: E402
except Exception:  # noqa: BLE001
    class Recorder:
        def __init__(self):
            self.turns = []

        def log(self, action, method, url, request_body, response):
            try:
                body = response.json()
                body_text = json.dumps(body)
            except ValueError:
                body, body_text = None, response.text
            self.turns.append({
                "turn": len(self.turns) + 1, "action": action,
                "request": {"method": method, "url": url, "body": request_body},
                "response": {"status": response.status_code, "json": body,
                             "text": body_text[:4000]},
            })
            return body if body is not None else response.text

        def as_transcript(self, flag=None, elapsed_s=None):
            out = {"turns": self.turns}
            if flag is not None:
                out["flag"] = flag
            if elapsed_s is not None:
                out["elapsed_s"] = elapsed_s
            return out

FLAG_RE = re.compile(r"flag\{[a-z0-9_]{8,}\}")
N = NIST256p.order
G = NIST256p.generator


def _digest_int(message):
    import hashlib
    return int.from_bytes(hashlib.sha256(message.encode()).digest(), "big") % N


def _sign(d, k, z):
    R = k * G
    r = R.x() % N
    s = (pow(k, -1, N) * (z + r * d)) % N
    return r, s


def solve(base, recorder, verbose=True):
    def say(m):
        if verbose:
            print(m)

    r = requests.get(f"{base}/api/spec", timeout=5)
    spec = recorder.log("recon:spec", "GET", f"{base}/api/spec", None, r)
    required_claim = "grant:admin:v1"  # disclosed in spec's `notes`/`endpoints` text
    say(f"[1] recon: required claim = {required_claim!r}")

    r = requests.get(f"{base}/api/pubkey", timeout=5)
    pk = recorder.log("recon:pubkey", "GET", f"{base}/api/pubkey", None, r)
    Qx, Qy = int(pk["Qx"], 16), int(pk["Qy"], 16)
    Q = Point(NIST256p.curve, Qx, Qy, N)
    say(f"[2] pubkey: Q = ({hex(Qx)[:12]}..., {hex(Qy)[:12]}...)")

    def attest(device_id):
        payload = {"device_id": device_id}
        resp = requests.post(f"{base}/api/attest", json=payload, timeout=5)
        body = recorder.log(f"collect:attest:{device_id}", "POST",
                            f"{base}/api/attest", payload, resp)
        return body["message"], int(body["r"], 16), int(body["s"], 16)

    m1, r1, s1 = attest("probe-alpha")
    m2, r2, s2 = attest("probe-beta")
    assert r1 == r2, "expected shared r (nonce reuse) across both attestations"
    say(f"[3] collected two attestations sharing r={hex(r1)[:14]}... "
        f"(nonce-reuse tell)")

    z1, z2 = _digest_int(m1), _digest_int(m2)
    k_rec = ((z1 - z2) * pow((s1 - s2) % N, -1, N)) % N
    d_rec = ((s1 * k_rec - z1) * pow(r1, -1, N)) % N
    assert (d_rec * G) == Q, "recovered private key does not match published Q"
    say(f"[4] recovered private key via nonce-reuse algebra: "
        f"d={hex(d_rec)[:14]}...")

    z3 = _digest_int(required_claim)
    k3 = random.randrange(1, N)
    r3, s3 = _sign(d_rec, k3, z3)

    payload = {"message": required_claim, "r": format(r3, "x"), "s": format(s3, "x")}
    resp = requests.post(f"{base}/api/redeem", json=payload, timeout=5)
    published = recorder.log("redeem:forged-claim", "POST",
                             f"{base}/api/redeem", payload, resp)
    match = FLAG_RE.search(json.dumps(published))
    if not match:
        raise RuntimeError("flag not returned by redeem endpoint")
    say(f"[5] flag: {match.group(0)}")
    return match.group(0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8080")
    ap.add_argument("--transcript", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    rec = Recorder()
    t0 = time.time()
    try:
        flag = solve(args.base, rec, verbose=not args.quiet)
    except Exception as exc:  # noqa: BLE001
        if args.transcript:
            pathlib.Path(args.transcript).write_text(
                json.dumps(rec.as_transcript(flag=None), indent=2), encoding="utf-8")
        print(f"SOLVE FAILED: {exc}", file=sys.stderr)
        return 1

    elapsed = time.time() - t0
    if args.transcript:
        pathlib.Path(args.transcript).write_text(
            json.dumps(rec.as_transcript(flag=flag, elapsed_s=elapsed), indent=2),
            encoding="utf-8")
    if not args.quiet:
        print(f"\nSolved in {len(rec.turns)} turns / {elapsed:.2f}s")
    print(flag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
