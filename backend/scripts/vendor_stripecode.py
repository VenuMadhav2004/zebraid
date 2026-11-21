"""Reproducible, SHA-256-verified vendoring script for STRIPECODE research modules.

IMPORTANT:
Do NOT run `--approve` until explicit team approval to vendor teammate code is confirmed.
This script extracts the exact 27 audited files from:
  - Member 1 PR #13 (lightweight-import commit): 127b563da6e380a293bbfddc451f237b89a7056e
  - Member 2 PR #12:                             96a69a45f754a4b6ea2c2cad46de26115eb72303
  - Common base (identical in both PRs):         3c0c20c

Usage:
  # Verify existing vendored tree:
  python scripts/vendor_stripecode.py --check

  # Vendor after explicit team approval:
  python scripts/vendor_stripecode.py --source ../../stripecode-ai --approve
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

MEMBER1_COMMIT = "871e2956a3cda8d3fb08433a8450a3718e9e312f"
MEMBER2_COMMIT = "ff827ba826f4fa8e34acf3ba41528f91a0252c1e"

# Exact manifest: (relative_path, git_commit, sha256_prefix_16)
MANIFEST: tuple[tuple[str, str, str], ...] = (
    ("member1_dhanushya/__init__.py", MEMBER2_COMMIT, "e3b0c44298fc1c14"),
    ("member1_dhanushya/recognition/__init__.py", MEMBER2_COMMIT, "75e1b30beebff5ac"),
    ("member1_dhanushya/recognition/engine.py", MEMBER2_COMMIT, "3a6078f35a6a7f34"),
    ("member1_dhanushya/recognition/local_matching.py", MEMBER2_COMMIT, "4cb07bc0cd489679"),
    ("member2_nisan/__init__.py", MEMBER2_COMMIT, "e3b0c44298fc1c14"),
    ("member2_nisan/stripe_analysis/__init__.py", MEMBER2_COMMIT, "d9f385c2843b63bb"),
    ("member2_nisan/stripe_analysis/features.py", MEMBER2_COMMIT, "72249b7c2ae0af35"),
    ("member2_nisan/stripe_analysis/identity_map.py", MEMBER2_COMMIT, "63e3aec8bb99c2ab"),
    ("member2_nisan/zebra_vision/__init__.py", MEMBER2_COMMIT, "442f740ded51393f"),
    ("member2_nisan/zebra_vision/simulator.py", MEMBER2_COMMIT, "e1dcf202c86dd991"),
    ("member2_nisan/zebra_vision/video.py", MEMBER2_COMMIT, "04f3d748868dabde"),
    ("research/__init__.py", MEMBER2_COMMIT, "84d4248baf2cb43c"),
    ("research/member1/__init__.py", MEMBER1_COMMIT, "e3b0c44298fc1c14"),
    ("research/member1/models/__init__.py", MEMBER1_COMMIT, "6079aa1328a0b7fe"),
    ("research/member1/models/api.py", MEMBER1_COMMIT, "2fa91522faab771d"),
    ("research/member1/models/enhancements.py", MEMBER1_COMMIT, "bbb4b4805ab2e53f"),
    ("research/member1/models/fusion.py", MEMBER1_COMMIT, "89d1bd44950f4907"),
    ("research/member1/models/morphology.py", MEMBER1_COMMIT, "7f5d4fe086569ec2"),
    ("research/member1/models/partial_hide.py", MEMBER1_COMMIT, "ae15256078d17772"),
    ("research/member1/models/segmentation.py", MEMBER1_COMMIT, "3fb5c47ffe8e4e30"),
    ("research/member1/models/zebra1_processor.py", MEMBER1_COMMIT, "3d035bc3cfb9174e"),
    ("research/member1/models/megadescriptor_dinov2.py", MEMBER1_COMMIT, "eef07a8aa0242e4f"),
    ("research/member2/__init__.py", MEMBER2_COMMIT, "e3b0c44298fc1c14"),
    ("research/member2/science/__init__.py", MEMBER2_COMMIT, "d0108b97c1fa0001"),
    ("research/member2/science/interface_v1.py", MEMBER2_COMMIT, "5dfeacdc1c06e168"),
    ("research/member2/science/request_schema_v1.json", MEMBER2_COMMIT, "7a4259097c19b0c8"),
    ("research/member2/science/schema_v1.json", MEMBER2_COMMIT, "94becc3c68fbdf38"),
    ("research/member2/deployment/__init__.py", MEMBER2_COMMIT, "af426d753457af6b"),
    ("research/member2/deployment/gallery.py", MEMBER2_COMMIT, "af82b278d03d8c28"),
)

DEFAULT_TARGET = Path(__file__).resolve().parent.parent / "third_party" / "stripecode"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_target(target: Path) -> int:
    if not target.is_dir():
        print(f"Vendored tree not present: {target}")
        return 1
    errors = 0
    for rel, _, expected_prefix in MANIFEST:
        p = target / rel
        if not p.is_file():
            print(f"MISSING: {rel}")
            errors += 1
            continue
        actual = _sha256(p.read_bytes())
        if not actual.startswith(expected_prefix):
            print(f"MISMATCH: {rel} expected={expected_prefix}... got={actual[:16]}...")
            errors += 1
    if errors == 0:
        print(f"OK: all {len(MANIFEST)} files verified in {target}")
    return 1 if errors else 0


def vendor(source_repo: Path, target: Path) -> int:
    rows: list[tuple[str, str, str]] = []
    for rel, commit, expected_prefix in MANIFEST:
        blob = subprocess.check_output(["git", "-C", str(source_repo), "show", f"{commit}:{rel}"])
        digest = _sha256(blob)
        if not digest.startswith(expected_prefix):
            raise RuntimeError(f"SHA-256 mismatch for {commit}:{rel}: got {digest[:16]}, expected {expected_prefix}")
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(blob)
        rows.append((rel, commit, digest))

    provenance_lines = [
        "# STRIPECODE Research Modules Provenance",
        "",
        f"- Member 1 (PR #13 lightweight-import): `{MEMBER1_COMMIT}`",
        f"- Member 2 (PR #12): `{MEMBER2_COMMIT}`",
        "- MegaDescriptor v1 (`integration/v1/`) is NOT vendored or modified.",
        "",
        "| File | Source Commit | SHA-256 |",
        "|---|---|---|",
        *[f"| `{rel}` | `{commit[:12]}` | `{digest}` |" for rel, commit, digest in rows],
        "",
    ]
    (target / "PROVENANCE.md").write_text("\n".join(provenance_lines), encoding="utf-8")
    print(f"Vendored {len(rows)} verified files to {target}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Vendor verified STRIPECODE research modules.")
    parser.add_argument("--source", type=Path, default=Path("../../stripecode-ai"), help="Path to stripecode-ai git repo")
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET, help="Destination vendored directory")
    parser.add_argument("--check", action="store_true", help="Verify an existing vendored directory")
    parser.add_argument("--approve", action="store_true", help="Confirm explicit team approval to copy teammate files")
    args = parser.parse_args()

    if args.check:
        return check_target(args.target)
    if not args.approve:
        print("Refusing to copy teammate code without --approve (explicit team approval required).", file=sys.stderr)
        return 2
    return vendor(args.source.resolve(), args.target.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
