"""Discovery, persistent registry integration, and safe serving of authorized 3D hide scans.

Files are only ever resolved from the server-side discovery map; client input is
used as a lookup key, never joined into a filesystem path.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.errors import AppError, ServiceUnavailableError
from app.repositories.base import NotFoundError
from app.services.hide_scan_importer import (
    load_registry,
    save_registry,
    validate_and_build_asset,
)

TEXTURE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
_HEADER_BYTES = 64 * 1024
_MAP_DIRECTIVE = re.compile(r"^\s*(map_\w+|bump|norm|disp|refl)\s+(.+?)\s*$", re.IGNORECASE)
_SAFE_FOLDER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,127}$")


@dataclass(frozen=True)
class ScanFile:
    name: str
    role: str  # obj | mtl | texture
    path: Path
    size_bytes: int
    sha256: str | None = None


@dataclass(frozen=True)
class HideScan:
    id: str
    label: str
    files: tuple[ScanFile, ...] = field(default_factory=tuple)
    model_format: str = "obj"
    dataset_source: str = "local"
    import_status: str = "discovered"
    validation_status: str = "valid"
    registered_at: str | None = None
    sha256: str | None = None
    mtl_file: str | None = None
    texture_files: tuple[str, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)

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
            names.append(Path(m.group(2).split()[-1].strip("\"'")).name)
    return names


def discover_scans(root: str | Path) -> dict[str, HideScan]:
    base = Path(root)
    if not base.is_dir():
        return {}
    registry = load_registry(base)
    reg_assets: dict[str, dict[str, Any]] = registry.get("assets", {})

    scans: dict[str, HideScan] = {}
    for folder in sorted(p for p in base.iterdir() if p.is_dir() and not p.name.startswith(".")):
        objs = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".obj")
        for obj in objs:
            scan_id = _slug(folder.name) if len(objs) == 1 else f"{_slug(folder.name)}-{_slug(obj.stem)}"
            reg = reg_assets.get(scan_id) or {}
            file_sha_map = {f["name"]: f.get("sha256") for f in reg.get("files", []) if isinstance(f, dict) and "name" in f}

            files = [ScanFile(obj.name, "obj", obj, obj.stat().st_size, file_sha_map.get(obj.name))]
            mtl_file: str | None = None
            tex_files: list[str] = []
            for mtl_name in _mtllib_names(obj):
                mtl = folder / Path(mtl_name).name
                if mtl.is_file():
                    mtl_file = mtl.name
                    files.append(ScanFile(mtl.name, "mtl", mtl, mtl.stat().st_size, file_sha_map.get(mtl.name)))
                    for tex_name in _texture_names(mtl):
                        tex = folder / tex_name
                        if tex.is_file() and tex.suffix.lower() in TEXTURE_EXTS and all(f.name != tex.name for f in files):
                            tex_files.append(tex.name)
                            files.append(ScanFile(tex.name, "texture", tex, tex.stat().st_size, file_sha_map.get(tex.name)))
            label = reg.get("display_name") or (folder.name if len(objs) == 1 else f"{folder.name} / {obj.stem}")
            scans[scan_id] = HideScan(
                id=scan_id,
                label=label,
                files=tuple(files),
                model_format=reg.get("model_format", "obj"),
                dataset_source=reg.get("dataset_source", "local"),
                import_status=reg.get("import_status", "discovered"),
                validation_status=reg.get("validation_status", "valid"),
                registered_at=reg.get("registered_at"),
                sha256=reg.get("sha256"),
                mtl_file=mtl_file,
                texture_files=tuple(tex_files),
                notes=tuple(reg.get("notes") or ()),
            )
    return scans


def registry_summary(root: str | Path) -> dict[str, int]:
    reg = load_registry(Path(root))
    return {
        "unsupported_count": len(reg.get("unsupported") or []),
        "incomplete_count": len(reg.get("incomplete") or []),
    }


def require_root(hide_scans_dir: str) -> Path:
    if not hide_scans_dir:
        raise ServiceUnavailableError("No authorized 3D scan directory is configured (HIDE_SCANS_DIR).", code="hide_scans_unavailable")
    root = Path(hide_scans_dir)
    if not root.is_dir():
        raise ServiceUnavailableError("The configured 3D scan directory is not accessible.", code="hide_scans_unavailable")
    return root


def get_scan_record(hide_scans_dir: str, asset_id: str) -> HideScan:
    scans = discover_scans(require_root(hide_scans_dir))
    scan = scans.get(asset_id)
    if scan is None:
        raise NotFoundError(f"3D scan '{asset_id}' not found")
    return scan


def get_scan_file(hide_scans_dir: str, scan_id: str, file_name: str) -> ScanFile:
    scan = get_scan_record(hide_scans_dir, scan_id)
    for f in scan.files:
        if f.name == file_name:
            return f
    raise NotFoundError(f"file '{file_name}' is not part of scan '{scan_id}'")


def register_scan_folder(hide_scans_dir: str, folder_name: str, *, dataset_source: str = "manual") -> list[dict[str, Any]]:
    """Validate and register all .obj models in one immediate subfolder of HIDE_SCANS_DIR."""
    root = require_root(hide_scans_dir).resolve()
    if not _SAFE_FOLDER_NAME.match(folder_name) or ".." in folder_name or "/" in folder_name or "\\" in folder_name:
        raise AppError("Invalid scan folder name.", status_code=422, code="validation_error")
    folder = (root / folder_name).resolve()
    try:
        folder.relative_to(root)
    except ValueError:
        raise AppError("Scan folder must reside inside HIDE_SCANS_DIR.", status_code=422, code="validation_error") from None
    if not folder.is_dir():
        raise NotFoundError(f"Scan folder '{folder_name}' not found")

    objs = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".obj")
    if not objs:
        raise AppError(f"No .obj files found in '{folder_name}'.", status_code=422, code="validation_error")

    registry = load_registry(root)
    registered: list[dict[str, Any]] = []
    from dataclasses import asdict

    for obj in objs:
        asset = validate_and_build_asset(
            folder,
            obj,
            dataset_source=dataset_source,
            base_dir=root,
            single_model_in_folder=(len(objs) == 1),
        )
        if asset.import_status != "imported":
            raise AppError(
                f"Model '{obj.name}' failed validation ({asset.validation_status}): {'; '.join(asset.notes)}",
                status_code=422,
                code="validation_error",
            )
        entry = asdict(asset)
        registry["assets"][asset.asset_id] = entry
        registered.append(entry)
    save_registry(root, registry)
    return registered


def unregister_scan(hide_scans_dir: str, asset_id: str) -> None:
    root = require_root(hide_scans_dir).resolve()
    registry = load_registry(root)
    if asset_id not in registry.get("assets", {}):
        raise NotFoundError(f"Registered 3D scan '{asset_id}' not found")
    del registry["assets"][asset_id]
    save_registry(root, registry)
