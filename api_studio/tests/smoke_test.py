import json
import sys
import time
from urllib import request as urlrequest
from urllib.error import HTTPError

BASE = "http://localhost:5050"


def call(method, path, payload=None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urlrequest.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urlrequest.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = body
        return exc.code, parsed


def expect(ok, message):
    if not ok:
        print("FAIL:", message)
        sys.exit(1)
    print("OK:", message)


status, health = call("GET", "/api/studio/health")
expect(status == 200 and health.get("success"), "studio health")

status, assets = call("GET", "/api/v1/assets")
expect(status == 200 and assets.get("success"), "list assets")
expect(len(assets.get("data", [])) >= 4, "seed assets present")

status, snapshot = call("POST", "/api/v1/asset-health/snapshots", {"assetCode": "EAF_01", "healthScore": 48, "condition": "CRITICAL"})
expect(status == 200 and snapshot.get("success"), "submit low health snapshot")

time.sleep(0.3)
status, pm = call("GET", "/api/v1/sap/pm/notifications")
expect(status == 200 and pm.get("success"), "list PM notifications")
expect(len(pm.get("data", [])) >= 1, "PM notification created")

status, openapi = call("GET", "/openapi.json")
expect(status == 200 and "paths" in openapi, "openapi export")

print("All smoke tests passed.")
