"""Discovery and safe serving of authorized 3D hide scans (OBJ + MTL + textures).

Files are only ever resolved from the server-side discovery map; client input is
used as a lookup key, never joined into a filesystem path.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from app.core.errors import ServiceUnavailableError
from app.repositories.base import NotFoundError

TEXTURE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
_HEADER_BYTES = 64 * 1024
_MAP_DIRECTIVE = re.compile(r"^\s*(map_\w+|bump|norm|disp|refl)\s+(.+?)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class ScanFile:
    name: str
    role: str  # obj | mtl | texture
    path: Path
    size_bytes: int


@dataclass(frozen=True)
class HideScan:
    id: str
    label: str
    files: tuple[ScanFile, ...] = field(default_factory=tuple)

    @property
    def total_bytes(self) -> int:
        return sum(f.size_bytes for f in self.files)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "scan"


def _mtllib_names(obj_path: Path) -> list[str]:
    with obj_path.open("rb") as fh:
        head = fh.read(_HEADER_BYTES).decode("utf-8", errors="ignore")
    return [line.split(None, 1)[1].strip() for line in head.splitlines() if line.startswith("mtllib ") and len(line.split(None, 1)) == 2]


def _texture_names(mtl_path: Path) -> list[str]:
    names: list[str] = []
    for line in mtl_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = _MAP_DIRECTIVE.match(line)
        if m:
            # last token is the file (options such as -s/-o may precede it)
            names.append(Path(m.group(2).split()[-1].strip("\"'")).name)
    return names


def discover_scans(root: str | Path) -> dict[str, HideScan]:
    base = Path(root)
    if not base.is_dir():
        return {}
    scans: dict[str, HideScan] = {}
    for folder in sorted(p for p in base.iterdir() if p.is_dir() and not p.name.startswith(".")):
        objs = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".obj")
        for obj in objs:
            files = [ScanFile(obj.name, "obj", obj, obj.stat().st_size)]
            for mtl_name in _mtllib_names(obj):
                mtl = folder / Path(mtl_name).name
                if mtl.is_file():
                    files.append(ScanFile(mtl.name, "mtl", mtl, mtl.stat().st_size))
                    for tex_name in _texture_names(mtl):
                        tex = folder / tex_name
                        if tex.is_file() and tex.suffix.lower() in TEXTURE_EXTS and all(f.name != tex.name for f in files):
                            files.append(ScanFile(tex.name, "texture", tex, tex.stat().st_size))
            scan_id = _slug(folder.name) if len(objs) == 1 else f"{_slug(folder.name)}-{_slug(obj.stem)}"
            label = folder.name if len(objs) == 1 else f"{folder.name} / {obj.stem}"
            scans[scan_id] = HideScan(scan_id, label, tuple(files))
    return scans


def require_root(hide_scans_dir: str) -> Path:
    if not hide_scans_dir:
        raise ServiceUnavailableError("No authorized 3D scan directory is configured (HIDE_SCANS_DIR).", code="hide_scans_unavailable")
    root = Path(hide_scans_dir)
    if not root.is_dir():
        raise ServiceUnavailableError("The configured 3D scan directory is not accessible.", code="hide_scans_unavailable")
    return root


def get_scan_file(hide_scans_dir: str, scan_id: str, file_name: str) -> ScanFile:
    scans = discover_scans(require_root(hide_scans_dir))
    scan = scans.get(scan_id)
    if scan is None:
        raise NotFoundError(f"3D scan '{scan_id}' not found")
    for f in scan.files:
        if f.name == file_name:
            return f
    raise NotFoundError(f"file '{file_name}' is not part of scan '{scan_id}'")
