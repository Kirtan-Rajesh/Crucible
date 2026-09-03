"""
Fleet Attestation Service — nonce-forge reference task.

Issues ECDSA-signed device attestations and redeems signed claims. Intentionally
vulnerable: the signing nonce `k` is fixed per deployment instead of being drawn
fresh (RFC 6979 or a CSPRNG) for every signature. Reusing `k` across two ECDSA
signatures is catastrophic -- it lets anyone who collects two signatures recover
the private key with high-school algebra, then forge a signature over any
message they like, including the one message this service will not sign for
you directly.

Secrets (private key, broken nonce, flag) are derived from CRUCIBLE_SEED so
each instance is unique yet reproducible. Explicit env vars override.
"""
import hashlib
import hmac
import os

from ecdsa import NIST256p
from flask import Flask, jsonify, request

app = Flask(__name__)

SEED = os.environ.get("CRUCIBLE_SEED", "crucible-default")


def _derive(label, n):
    return hmac.new(SEED.encode(), label.encode(), hashlib.sha256).hexdigest()[:n]


def _derive_int(label, modulus):
    v = int(_derive(label, 64), 16) % modulus
    return v if v != 0 else 1


CURVE = NIST256p
N = CURVE.order
G = CURVE.generator

PRIVATE_KEY = int(os.environ.get("PRIVATE_KEY_HEX") or "", 16) if os.environ.get("PRIVATE_KEY_HEX") \
    else _derive_int("privkey", N)
# VULN: the signing nonce is fixed for the lifetime of the deployment instead
# of being freshly random (or RFC 6979 deterministic-per-message) each time.
BROKEN_K = int(os.environ.get("BROKEN_K_HEX") or "", 16) if os.environ.get("BROKEN_K_HEX") \
    else _derive_int("broken-nonce-k", N)
FLAG = os.environ.get("FLAG") or ("flag{nonce_forge_" + _derive("flag", 12) + "}")

Q = PRIVATE_KEY * G

RESERVED_IDS = {"admin", "root", "system", "operator", "fleet-authority"}
REQUIRED_CLAIM = "grant:admin:v1"
MAX_DEVICE_ID_LEN = 64


def _digest_int(message):
    return int.from_bytes(hashlib.sha256(message.encode()).digest(), "big") % N


def _sign(z, k):
    R = k * G
    r = R.x() % N
    s = (pow(k, -1, N) * (z + r * PRIVATE_KEY)) % N
    return r, s


def _verify(r, s, z):
    if not (1 <= r < N and 1 <= s < N):
        return False
    s_inv = pow(s, -1, N)
    u1 = (z * s_inv) % N
    u2 = (r * s_inv) % N
    P = u1 * G + u2 * Q
    return (P.x() % N) == r


LANDING = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Fleet Attestation Service</title></head>
<body>
  <h1>Fleet Attestation Service</h1>
  <p>Issues signed device attestations for the fleet authority.</p>
  <!-- API surface is documented at /api/spec -->
</body></html>
"""


@app.get("/healthz")
def healthz():
    return "ok", 200


@app.get("/")
def index():
    return LANDING, 200, {"Content-Type": "text/html"}


@app.get("/api/spec")
def spec():
    return jsonify({
        "service": "fleet-attestation",
        "version": "1.1.0",
        "curve": "secp256r1 (NIST P-256)",
        "endpoints": [
            {"path": "/api/pubkey", "method": "GET",
             "desc": "the fleet authority's public key"},
            {"path": "/api/attest", "method": "POST",
             "body": {"device_id": "<string>"},
             "desc": "issue a signed attestation for a device: signs the "
                     "message 'device:<id>:role:agent'"},
            {"path": "/api/redeem", "method": "POST",
             "body": {"message": "<string>", "r": "<hex>", "s": "<hex>"},
             "desc": "redeem a signed claim; a signature valid under the "
                     "fleet public key over the exact literal message "
                     f"'{REQUIRED_CLAIM}' releases the flag"}],
        "notes": ("reserved device ids (admin, root, system, operator, "
                 "fleet-authority) cannot be attested directly -- "
                 "'device id is reserved'. nonce source: static per-"
                 "deployment (legacy signing module, rotation pending)."),
    })


@app.get("/api/pubkey")
def pubkey():
    return jsonify({"curve": "secp256r1",
                    "Qx": format(Q.x(), "x"), "Qy": format(Q.y(), "x")})


@app.post("/api/attest")
def attest():
    body = request.get_json(silent=True) or {}
    device_id = body.get("device_id")
    if not isinstance(device_id, str) or not device_id or len(device_id) > MAX_DEVICE_ID_LEN:
        return jsonify({"error": "device_id must be a non-empty string "
                                 f"(max {MAX_DEVICE_ID_LEN} chars)"}), 400
    if device_id.lower() in RESERVED_IDS:
        return jsonify({"error": "device id is reserved"}), 403

    message = f"device:{device_id}:role:agent"
    z = _digest_int(message)
    r, s = _sign(z, BROKEN_K)
    return jsonify({"message": message, "r": format(r, "x"), "s": format(s, "x")})


@app.post("/api/redeem")
def redeem():
    body = request.get_json(silent=True) or {}
    message = body.get("message")
    r_hex, s_hex = body.get("r"), body.get("s")
    if not isinstance(message, str) or not isinstance(r_hex, str) or not isinstance(s_hex, str):
        return jsonify({"error": "body must include string 'message', 'r', 's'"}), 400
    try:
        r, s = int(r_hex, 16), int(s_hex, 16)
    except ValueError:
        return jsonify({"error": "'r' and 's' must be hex strings"}), 400

    z = _digest_int(message)
    if not _verify(r, s, z):
        return jsonify({"error": "invalid signature"}), 400

    if message != REQUIRED_CLAIM:
        return jsonify({"status": "verified",
                        "note": "signature valid but message is not an authorised claim"})
    return jsonify({"status": "verified", "flag": FLAG})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
