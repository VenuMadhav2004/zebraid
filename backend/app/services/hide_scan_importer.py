"""Automated discovery, validation, SHA-256 deduplication, and ingestion for Zebra 3D hide scans.

Supports:
  - Local dataset directories (recursive scan)
  - Public Google Drive dataset folders (via embeddedfolderview + direct download)

Design guarantees:
  - Preserves original filenames and folder metadata.
  - Never overwrites existing files with differing content; deduplicates by SHA-256.
  - Records incomplete, corrupt, and unsupported files explicitly without silently discarding them.
  - Persists metadata in `<target_dir>/.registry.json` using atomic temp-file replacement.
  - Never exposes absolute filesystem paths in API-facing metadata.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

DEFAULT_DRIVE_FOLDER_ID = "1Q925t9_t2tMHPXTtCyQSLNItmctYA2JI"
REGISTRY_FILENAME = ".registry.json"

SUPPORTED_MODEL_EXTS = {".obj", ".glb", ".gltf", ".ply", ".stl"}
VIEWER_SUPPORTED_EXTS = {".obj"}  # Existing Three.js pipeline uses OBJ + MTL + textures
TEXTURE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
IGNORED_OS_FILES = {".ds_store", "thumbs.db", "desktop.ini"}

_HEADER_BYTES = 64 * 1024
_MAP_DIRECTIVE = re.compile(r"^\s*(map_\w+|bump|norm|disp|refl)\s+(.+?)\s*$", re.IGNORECASE)
_DRIVE_ENTRY_RE = re.compile(
    r'id="entry-([^"]+)"[^>]*>.*?href="([^"]+)".*?class="flip-entry-title">([^<]+)<',
    re.S,
)


@dataclass(frozen=True)
class DriveNode:
    file_id: str
    name: str
    rel_path: str
    is_folder: bool


@dataclass
class RegisteredAsset:
    asset_id: str
    display_name: str
    original_filename: str
    dataset_source: str
    model_format: str
    model_file_path: str
    mtl_path: str | None
    texture_paths: list[str]
    file_size: int
    total_bytes: int
    sha256: str
    import_status: str  # imported | incomplete | corrupt | unsupported
    validation_status: str  # valid | missing_mtl | missing_texture | invalid_obj | unsupported_format
    registered_at: str
    files: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "scan"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _mtllib_names(obj_path: Path) -> list[str]:
    with obj_path.open("rb") as fh:
        head = fh.read(_HEADER_BYTES).decode("utf-8", errors="ignore")
    out: list[str] = []
    for line in head.splitlines():
        if line.startswith("mtllib "):
            parts = line.split(None, 1)
            if len(parts) == 2 and parts[1].strip():
                out.append(Path(parts[1].strip()).name)
    return out


def _texture_names(mtl_path: Path) -> list[str]:
    names: list[str] = []
    for line in mtl_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = _MAP_DIRECTIVE.match(line)
        if m:
            names.append(Path(m.group(2).split()[-1].strip("\"'")).name)
    return names


def _validate_obj_content(obj_path: Path) -> tuple[bool, str | None]:
    if not obj_path.is_file() or obj_path.stat().st_size == 0:
        return False, "OBJ file is empty or missing"
    has_vertex = False
    with obj_path.open("rb") as fh:
        for _ in range(5000):
            line = fh.readline()
            if not line:
                break
            if line.startswith((b"v ", b"vn ", b"vt ", b"f ")):
                has_vertex = True
                break
    if not has_vertex:
        return False, "OBJ file has no geometry directives (v/f)"
    return True, None


def load_registry(target_dir: Path) -> dict[str, Any]:
    reg_path = target_dir / REGISTRY_FILENAME
    if not reg_path.is_file():
        return {"version": 1, "assets": {}, "unsupported": [], "incomplete": []}
    try:
        data = json.loads(reg_path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("assets"), dict):
            data.setdefault("unsupported", [])
            data.setdefault("incomplete", [])
            return data
    except Exception:
        pass
    return {"version": 1, "assets": {}, "unsupported": [], "incomplete": []}


def save_registry(target_dir: Path, registry: dict[str, Any]) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    reg_path = target_dir / REGISTRY_FILENAME
    payload = json.dumps(registry, indent=2, sort_keys=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".registry-", suffix=".tmp", dir=str(target_dir))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp_name, reg_path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def validate_and_build_asset(
    folder: Path,
    obj_path: Path,
    *,
    dataset_source: str,
    base_dir: Path,
    single_model_in_folder: bool,
) -> RegisteredAsset:
    """Validate an OBJ + associated MTL/texture files and compute SHA-256."""
    asset_id = _slug(folder.name) if single_model_in_folder else f"{_slug(folder.name)}-{_slug(obj_path.stem)}"
    display_name = folder.name if single_model_in_folder else f"{folder.name} / {obj_path.stem}"
    now_iso = datetime.now(timezone.utc).isoformat()

    obj_ok, obj_err = _validate_obj_content(obj_path)
    obj_size = obj_path.stat().st_size if obj_path.is_file() else 0
    obj_sha = _sha256_file(obj_path) if obj_path.is_file() else ""

    files: list[dict[str, Any]] = [
        {"name": obj_path.name, "role": "obj", "size_bytes": obj_size, "sha256": obj_sha}
    ]
    notes: list[str] = []
    mtl_rel: str | None = None
    tex_rels: list[str] = []
    validation_status = "valid"

    if not obj_ok:
        validation_status = "invalid_obj"
        if obj_err:
            notes.append(obj_err)

    mtl_refs = _mtllib_names(obj_path) if obj_ok else []
    for mtl_name in mtl_refs:
        mtl_file = folder / mtl_name
        if not mtl_file.is_file():
            if validation_status == "valid":
                validation_status = "missing_mtl"
            notes.append(f"Referenced MTL not found: {mtl_name}")
            continue
        mtl_rel = str(mtl_file.relative_to(base_dir)).replace("\\", "/")
        files.append(
            {
                "name": mtl_file.name,
                "role": "mtl",
                "size_bytes": mtl_file.stat().st_size,
                "sha256": _sha256_file(mtl_file),
            }
        )
        for tex_name in _texture_names(mtl_file):
            tex_file = folder / tex_name
            if not tex_file.is_file() or tex_file.suffix.lower() not in TEXTURE_EXTS:
                if validation_status == "valid":
                    validation_status = "missing_texture"
                notes.append(f"Referenced texture not found or unsupported: {tex_name}")
                continue
            if all(f["name"] != tex_file.name for f in files):
                tex_rels.append(str(tex_file.relative_to(base_dir)).replace("\\", "/"))
                files.append(
                    {
                        "name": tex_file.name,
                        "role": "texture",
                        "size_bytes": tex_file.stat().st_size,
                        "sha256": _sha256_file(tex_file),
                    }
                )

    import_status = "imported" if validation_status == "valid" else ("corrupt" if validation_status == "invalid_obj" else "incomplete")
    total_bytes = sum(int(f["size_bytes"]) for f in files)
    model_rel = str(obj_path.relative_to(base_dir)).replace("\\", "/")

    return RegisteredAsset(
        asset_id=asset_id,
        display_name=display_name,
        original_filename=obj_path.name,
        dataset_source=dataset_source,
        model_format="obj",
        model_file_path=model_rel,
        mtl_path=mtl_rel,
        texture_paths=tex_rels,
        file_size=obj_size,
        total_bytes=total_bytes,
        sha256=obj_sha,
        import_status=import_status,
        validation_status=validation_status,
        registered_at=now_iso,
        files=files,
        notes=notes,
    )


def discover_google_drive_tree(folder_id: str, prefix: str = "") -> list[DriveNode]:
    """Recursively list a public Google Drive folder via embeddedfolderview."""
    url = f"https://drive.google.com/embeddedfolderview?id={folder_id}#list"
    r = httpx.get(url, follow_redirects=True, timeout=30.0)
    if "accounts.google.com" in str(r.url):
        raise PermissionError(f"Google Drive folder {folder_id} requires authentication.")
    r.raise_for_status()

    nodes: list[DriveNode] = []
    for eid, href, title in _DRIVE_ENTRY_RE.findall(r.text):
        clean_title = title.strip()
        rel = f"{prefix}{clean_title}" if prefix else clean_title
        is_folder = "/folders/" in href
        nodes.append(DriveNode(file_id=eid, name=clean_title, rel_path=rel, is_folder=is_folder))
        if is_folder:
            nodes.extend(discover_google_drive_tree(eid, prefix=f"{rel}/"))
    return nodes


def _download_drive_file(file_id: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t"
    fd, tmp_name = tempfile.mkstemp(prefix=".dl-", suffix=".part", dir=str(dest.parent))
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=120.0) as resp:
            resp.raise_for_status()
            ctype = (resp.headers.get("content-type") or "").lower()
            if "text/html" in ctype:
                raise RuntimeError(f"Google Drive returned HTML instead of binary for file {file_id}")
            with tmp_path.open("wb") as out:
                for chunk in resp.iter_bytes(chunk_size=1024 * 256):
                    out.write(chunk)
        os.replace(tmp_path, dest)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def import_from_google_drive(folder_id: str, target_dir: Path) -> dict[str, Any]:
    """Discover, download supported 3D model groups, validate, and register from Google Drive."""
    target_dir = target_dir.resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    registry = load_registry(target_dir)
    known_sha = {
        a["sha256"]: aid
        for aid, a in registry["assets"].items()
        if a.get("import_status") == "imported" and a.get("sha256")
    }

    nodes = discover_google_drive_tree(folder_id)
    file_nodes = [n for n in nodes if not n.is_folder]

    # Top-level folder grouping (e.g. "Zebra 1/Zebra1_flat64_model.obj")
    by_top_folder: dict[str, list[DriveNode]] = {}
    unsupported: list[dict[str, Any]] = []
    for n in file_nodes:
        low = n.name.lower()
        ext = Path(n.name).suffix.lower()
        if low in IGNORED_OS_FILES:
            continue
        parts = n.rel_path.split("/")
        # Agisoft Metashape internal folders (*.files/) and .psx/.oc3/.zip are non-viewer project files
        is_metashape_internal = any(p.endswith(".files") for p in parts[:-1])
        if is_metashape_internal or ext not in (SUPPORTED_MODEL_EXTS | {".mtl"} | TEXTURE_EXTS):
            unsupported.append({"rel_path": n.rel_path, "extension": ext or "(none)", "reason": "Unsupported non-mesh/Metashape file"})
            continue
        top = parts[0] if len(parts) > 1 else "root"
        by_top_folder.setdefault(top, []).append(n)

    imported: list[str] = []
    skipped_existing: list[str] = []
    duplicates: list[dict[str, str]] = []
    failed: list[dict[str, Any]] = []

    for folder_name, group in sorted(by_top_folder.items()):
        folder_path = target_dir / folder_name
        folder_path.mkdir(parents=True, exist_ok=True)
        # Only download top-level model/mtl/texture files (skip auxiliary screenshots unless referenced)
        obj_nodes = [n for n in group if Path(n.name).suffix.lower() == ".obj"]
        other_model_nodes = [n for n in group if Path(n.name).suffix.lower() in (SUPPORTED_MODEL_EXTS - {".obj"})]
        for n in other_model_nodes:
            unsupported.append(
                {
                    "rel_path": n.rel_path,
                    "extension": Path(n.name).suffix.lower(),
                    "reason": "Detected 3D format not yet wired to Three.js OBJ loader",
                }
            )

        if not obj_nodes:
            continue

        # Download OBJ(s) first, then referenced MTLs & textures
        downloaded_names: set[str] = set()
        for obj_n in obj_nodes:
            dest_obj = folder_path / obj_n.name
            if not dest_obj.is_file():
                _download_drive_file(obj_n.file_id, dest_obj)
            downloaded_names.add(obj_n.name)

            # Download referenced MTLs
            for mtl_name in _mtllib_names(dest_obj):
                mtl_node = next((x for x in group if x.name == mtl_name), None)
                if mtl_node:
                    dest_mtl = folder_path / mtl_node.name
                    if not dest_mtl.is_file():
                        _download_drive_file(mtl_node.file_id, dest_mtl)
                    downloaded_names.add(mtl_node.name)
                    for tex_name in _texture_names(dest_mtl):
                        tex_node = next((x for x in group if x.name == tex_name), None)
                        if tex_node:
                            dest_tex = folder_path / tex_node.name
                            if not dest_tex.is_file():
                                _download_drive_file(tex_node.file_id, dest_tex)
                            downloaded_names.add(tex_node.name)

            asset = validate_and_build_asset(
                folder_path,
                dest_obj,
                dataset_source=f"gdrive:{folder_id}",
                base_dir=target_dir,
                single_model_in_folder=(len(obj_nodes) == 1),
            )
            if asset.import_status != "imported":
                failed.append({"asset_id": asset.asset_id, "status": asset.validation_status, "notes": asset.notes})
                continue

            if asset.sha256 in known_sha and known_sha[asset.sha256] != asset.asset_id:
                duplicates.append({"asset_id": asset.asset_id, "duplicate_of": known_sha[asset.sha256], "sha256": asset.sha256})
                continue

            prev = registry["assets"].get(asset.asset_id)
            if prev and prev.get("sha256") == asset.sha256 and prev.get("import_status") == "imported":
                skipped_existing.append(asset.asset_id)
            else:
                registry["assets"][asset.asset_id] = asdict(asset)
                known_sha[asset.sha256] = asset.asset_id
                imported.append(asset.asset_id)

    registry["unsupported"] = unsupported
    registry["incomplete"] = failed
    save_registry(target_dir, registry)

    return {
        "source": f"gdrive:{folder_id}",
        "total_drive_files": len(file_nodes),
        "imported": imported,
        "skipped_existing": skipped_existing,
        "duplicates": duplicates,
        "failed": failed,
        "unsupported_count": len(unsupported),
        "unsupported_sample": unsupported[:20],
        "registered_total": len(registry["assets"]),
    }


def import_from_local_directory(source_dir: Path, target_dir: Path, *, dataset_source: str = "local") -> dict[str, Any]:
    """Scan a local directory (can be target_dir itself) and register valid 3D models incrementally."""
    source_dir = source_dir.resolve()
    target_dir = target_dir.resolve()
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Source directory does not exist: {source_dir}")

    target_dir.mkdir(parents=True, exist_ok=True)
    registry = load_registry(target_dir)
    known_sha = {
        a["sha256"]: aid
        for aid, a in registry["assets"].items()
        if a.get("import_status") == "imported" and a.get("sha256")
    }

    imported: list[str] = []
    skipped_existing: list[str] = []
    duplicates: list[dict[str, str]] = []
    failed: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []

    for folder in sorted(p for p in source_dir.iterdir() if p.is_dir() and not p.name.startswith(".")):
        objs = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".obj")
        for p in folder.rglob("*"):
            if not p.is_file() or p.name.lower() in IGNORED_OS_FILES or p.name == REGISTRY_FILENAME:
                continue
            ext = p.suffix.lower()
            if ext not in (VIEWER_SUPPORTED_EXTS | {".mtl"} | TEXTURE_EXTS):
                unsupported.append(
                    {
                        "rel_path": str(p.relative_to(source_dir)).replace("\\", "/"),
                        "extension": ext or "(none)",
                        "reason": "Unsupported format for OBJ/MTL viewer",
                    }
                )

        if not objs:
            continue

        dest_folder = target_dir / folder.name if source_dir != target_dir else folder
        if source_dir != target_dir:
            dest_folder.mkdir(parents=True, exist_ok=True)
            for src_file in folder.iterdir():
                if src_file.is_file() and src_file.suffix.lower() in (VIEWER_SUPPORTED_EXTS | {".mtl"} | TEXTURE_EXTS):
                    dest_file = dest_folder / src_file.name
                    if not dest_file.exists():
                        dest_file.write_bytes(src_file.read_bytes())

        for obj in objs:
            dest_obj = dest_folder / obj.name
            asset = validate_and_build_asset(
                dest_folder,
                dest_obj,
                dataset_source=dataset_source,
                base_dir=target_dir,
                single_model_in_folder=(len(objs) == 1),
            )
            if asset.import_status != "imported":
                failed.append({"asset_id": asset.asset_id, "status": asset.validation_status, "notes": asset.notes})
                continue
            if asset.sha256 in known_sha and known_sha[asset.sha256] != asset.asset_id:
                duplicates.append({"asset_id": asset.asset_id, "duplicate_of": known_sha[asset.sha256], "sha256": asset.sha256})
                continue
            prev = registry["assets"].get(asset.asset_id)
            if prev and prev.get("sha256") == asset.sha256 and prev.get("import_status") == "imported":
                skipped_existing.append(asset.asset_id)
            else:
                registry["assets"][asset.asset_id] = asdict(asset)
                known_sha[asset.sha256] = asset.asset_id
                imported.append(asset.asset_id)

    registry["unsupported"] = unsupported
    registry["incomplete"] = failed
    save_registry(target_dir, registry)
    return {
        "source": str(source_dir),
        "imported": imported,
        "skipped_existing": skipped_existing,
        "duplicates": duplicates,
        "failed": failed,
        "unsupported_count": len(unsupported),
        "unsupported_sample": unsupported[:20],
        "registered_total": len(registry["assets"]),
    }
