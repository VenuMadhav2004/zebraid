"""Print feature availability from a running API. Usage: python features.py http://127.0.0.1:8000"""
import json
import sys
import urllib.request

base = sys.argv[1].rstrip("/") + "/api/v1"


def get(path):
    try:
        with urllib.request.urlopen(base + path, timeout=15) as r:
            return json.load(r)
    except Exception as exc:  # noqa: BLE001
        return {"_error": f"{type(exc).__name__}"}


def line(label, available, detail):
    print(f"  {'ok' if available else '!!'} {label}: {detail}")


caps = get("/analyses/capabilities")
for kind in ("stripe_morphology", "spatial_frequency"):
    c = caps.get(kind, {})
    line(f"stripe {kind}", c.get("available"), "available" if c.get("available") else f"unavailable - {c.get('reason') or caps.get('_error')}")
rec = get("/identifications/capabilities")
line("recognition (MegaDescriptor v1)", rec.get("available"), "available" if rec.get("available") else f"unavailable - {rec.get('reason') or rec.get('_error')}")
gem = get("/assistant/status")
line("gemini assistant", gem.get("available"), f"available ({gem.get('model')})" if gem.get("available") else f"unavailable - {gem.get('reason') or gem.get('_error')}")
scans = get("/hide-scans")
names = ", ".join(s["id"] for s in scans.get("scans", []))
line("3D hide scans", scans.get("available"), f"{len(scans.get('scans', []))} available ({names})" if scans.get("available") else f"unavailable - {scans.get('reason') or scans.get('_error')}")
