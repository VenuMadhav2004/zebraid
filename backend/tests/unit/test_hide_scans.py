"""Authorized 3D hide scan listing/serving (temp directory, no network, no DB)."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints import hide_scans as endpoint
from app.core.config import Settings
from app.main import create_app

S = "/api/v1/hide-scans"


def _make_scan(root: Path, folder: str = "Zebra 9", stem: str = "Zebra9") -> Path:
    d = root / folder
    d.mkdir(parents=True)
    (d / f"{stem}.obj").write_text(f"# test\nmtllib {stem}.mtl\nusemtl m\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    (d / f"{stem}.mtl").write_text(f"newmtl m\nmap_Kd {stem}.png\n")
    (d / f"{stem}.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    (d / "unrelated_screenshot.png").write_bytes(b"\x89PNG\r\n\x1a\n")  # not referenced by the MTL
    return d


@pytest.fixture
def client_for(monkeypatch):
    def make(hide_dir: str = "", allow_remote: bool = True):
        settings = Settings(_env_file=None, hide_scans_dir=hide_dir, hide_scans_allow_remote=allow_remote)
        monkeypatch.setattr(endpoint, "get_settings", lambda: settings)
        return TestClient(create_app(settings), raise_server_exceptions=False)

    return make


def test_lists_scan_with_referenced_files_only(tmp_path, client_for):
    _make_scan(tmp_path)
    body = client_for(str(tmp_path)).get(S).json()
    assert body["available"] is True
    (scan,) = body["scans"]
    assert scan["id"] == "zebra-9" and scan["label"] == "Zebra 9"
    assert [(f["name"], f["role"]) for f in scan["files"]] == [("Zebra9.obj", "obj"), ("Zebra9.mtl", "mtl"), ("Zebra9.png", "texture")]
    assert "path" not in str(body) and str(tmp_path) not in str(body)


def test_downloads_listed_file(tmp_path, client_for):
    d = _make_scan(tmp_path)
    resp = client_for(str(tmp_path)).get(f"{S}/zebra-9/files/Zebra9.obj")
    assert resp.status_code == 200
    assert resp.content == (d / "Zebra9.obj").read_bytes()


@pytest.mark.parametrize("name", ["unrelated_screenshot.png", "..%2F..%2Fetc%2Fpasswd", "Zebra9.OBJ", "nope.obj"])
def test_unlisted_or_traversal_names_are_404(tmp_path, client_for, name):
    _make_scan(tmp_path)
    assert client_for(str(tmp_path)).get(f"{S}/zebra-9/files/{name}").status_code == 404


def test_unknown_scan_is_404(tmp_path, client_for):
    _make_scan(tmp_path)
    assert client_for(str(tmp_path)).get(f"{S}/zebra-404/files/Zebra9.obj").status_code == 404


def test_remote_clients_forbidden_by_default(tmp_path, client_for):
    _make_scan(tmp_path)
    c = client_for(str(tmp_path), allow_remote=False)  # TestClient host is "testclient", not loopback
    assert c.get(S).status_code == 403
    assert c.get(f"{S}/zebra-9/files/Zebra9.obj").status_code == 403


def test_unconfigured_directory_reports_unavailable(client_for):
    body = client_for("").get(S).json()
    assert body == {"available": False, "reason": body["reason"], "scans": []}
    assert "HIDE_SCANS_DIR" in body["reason"]
    assert client_for("").get(f"{S}/zebra-1/files/x.obj").status_code == 503
