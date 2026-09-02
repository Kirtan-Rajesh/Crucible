"""
Provue Telemetry Collector (internal service)
=============================================

This service stores the raw telemetry documents and is *not* meant to be
reachable from the outside world. In the deployed topology it lives on an
internal Docker network with no published port, and it only answers metric
queries that carry the shared edge-origin header that the edge tier injects
on its behalf.

It is intentionally vulnerable for the CTF: the full-text search path returns
whole documents and forgets that some documents are marked private.
"""
import json
import os
import pathlib

from flask import Flask, jsonify, request

app = Flask(__name__)

# Shared secret injected by the edge tier on every server-side fetch it makes.
# Anyone talking to the collector *directly* (i.e. without pivoting through the
# edge service) will not have it, so private data stays behind the pivot.
EDGE_ORIGIN_TOKEN = os.environ.get("EDGE_ORIGIN_TOKEN", "edge-origin-2f9c1a7b4e")

DATA_PATH = pathlib.Path(__file__).parent / "data" / "seed.json"
with DATA_PATH.open(encoding="utf-8") as fh:
    _DOCS = json.load(fh)["metrics"]

# Minimal projection used for public listings: never leak the private fields.
_PUBLIC_FIELDS = ("id", "name", "value", "unit", "visibility")


def _public_view(doc):
    return {k: doc[k] for k in _PUBLIC_FIELDS if k in doc}


def _is_edge_origin():
    return request.headers.get("X-Edge-Origin", "") == EDGE_ORIGIN_TOKEN


@app.get("/healthz")
def healthz():
    # Unauthenticated: used by the container healthcheck only.
    return "ok", 200


@app.get("/")
def root():
    # Unauthenticated banner. Reaching this through the edge render endpoint is
    # the observable proof that an attacker has pivoted onto the internal net.
    return jsonify(
        {
            "service": "provue-collector",
            "version": "1.4.2",
            "role": "internal-telemetry-store",
            "endpoints": ["/metrics"],
        }
    )


@app.get("/metrics")
def metrics():
    # Everything past the banner is restricted to the edge origin. A direct
    # caller (no pivot) is refused here, which is what forces the SSRF chain.
    if not _is_edge_origin():
        return (
            jsonify({"error": "collector access is restricted to the edge origin"}),
            401,
        )

    q = (request.args.get("q") or "").strip()

    if not q:
        # Default listing: public documents only, projected to safe fields.
        public = [_public_view(d) for d in _DOCS if d.get("visibility") == "public"]
        return jsonify(
            {
                "count": len(public),
                "metrics": public,
                "_meta": {
                    "note": "full-text search available over telemetry documents",
                    "usage": "/metrics?q=<term>",
                },
            }
        )

    if len(q) < 2:
        return jsonify({"error": "search term must be at least 2 characters"}), 400

    # VULN: full-text search matches across the entire serialized document and
    # returns matched documents in full -- including the ones flagged private,
    # which the developer forgot to exclude from this code path.
    needle = q.lower()
    hits = [d for d in _DOCS if needle in json.dumps(d).lower()]
    return jsonify({"query": q, "count": len(hits), "metrics": hits})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "9000"))
    app.run(host="0.0.0.0", port=port)
