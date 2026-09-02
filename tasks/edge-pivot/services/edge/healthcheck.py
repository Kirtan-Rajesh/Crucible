import sys
import urllib.request

# Exits 0 iff the service answers /healthz with 200. Kept free of shell
# metacharacters so it is portable across Docker (exec form) and podman-compose
# (which runs the healthcheck via /bin/sh).
try:
    resp = urllib.request.urlopen("http://localhost:8080/healthz", timeout=2)
    sys.exit(0 if resp.status == 200 else 1)
except Exception:
    sys.exit(1)
