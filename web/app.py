import hashlib
import os
import re
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path

import docker
from docker.errors import NotFound
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

WORLDS_DIR = Path("/worlds")
CONFIG_DIR = Path("/config")
ACTIVE_FILE = CONFIG_DIR / "active.txt"
RUNTIME_DIR = WORLDS_DIR / "runtime"
CONTAINER_NAME = os.environ.get("MINECRAFT_CONTAINER", "nexus-minecraft")
DEFAULT_PLAYER = os.environ.get("DEFAULT_PLAYER", "whiterose")
SKIP_DIRS = {"runtime", "active", ".DS_Store"}
MAX_UPLOAD_MB = 500

app = FastAPI(title="Nexus Minecraft Worlds")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
def on_startup():
    WORLDS_DIR.mkdir(parents=True, exist_ok=True)
    ensure_runtime_world()


def sanitize_name(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9_-]+", "-", name)
    name = re.sub(r"-+", "-", name).strip("-")
    if not name:
        raise HTTPException(400, "Invalid world name")
    return name


def get_active() -> str | None:
    if ACTIVE_FILE.exists():
        return ACTIVE_FILE.read_text().strip() or None
    return None


def get_container():
    client = docker.from_env()
    try:
        return client.containers.get(CONTAINER_NAME)
    except NotFound:
        raise HTTPException(503, f"Container '{CONTAINER_NAME}' not found. Is docker compose up?")


def stop_minecraft() -> None:
    container = get_container()
    if container.status == "running":
        container.stop(timeout=60)


def start_minecraft() -> str:
    container = get_container()
    if container.status != "running":
        container.start()
    container.reload()
    return container.status


def offline_player_uuid(username: str) -> str:
    """Minecraft offline-mode UUID for a username."""
    data = f"OfflinePlayer:{username}".encode("utf-8")
    md5 = bytearray(hashlib.md5(data).digest())
    md5[6] = (md5[6] & 0x0F) | 0x30
    md5[8] = (md5[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(md5)))


def list_player_saves(world_dir: Path) -> list[Path]:
    """Singleplayer saves under players/data/*.dat"""
    saves = []
    data_dir = world_dir / "players" / "data"
    if data_dir.exists():
        for f in data_dir.glob("*.dat"):
            if "_old" not in f.name:
                saves.append(f)
    return saves


def save_player_data_to_world(world_dir: Path, source_dir: Path) -> None:
    """Persist server playerdata back into the archived world."""
    src_pd = source_dir / "playerdata"
    if not src_pd.exists():
        return

    dest_pd = world_dir / "playerdata"
    dest_pd.mkdir(exist_ok=True)
    dest_sp = world_dir / "players" / "data"
    dest_sp.mkdir(parents=True, exist_ok=True)

    for f in src_pd.glob("*.dat"):
        shutil.copy2(f, dest_pd / f.name)
        shutil.copy2(f, dest_sp / f.name)


def migrate_player_data(world_dir: Path) -> None:
    """
    Dedicated servers read playerdata/<uuid>.dat, not players/data/.
    Singleplayer uses players/data/ with your Mojang UUID.
    Offline mode uses a different UUID — copy the richest save to that file.
    """
    playerdata = world_dir / "playerdata"
    playerdata.mkdir(exist_ok=True)

    saves = list_player_saves(world_dir)
    for src in saves:
        shutil.copy2(src, playerdata / src.name)

    if not saves:
        return

    # Best singleplayer save (usually has armor/items)
    primary = max(saves, key=lambda p: p.stat().st_size)
    offline_id = offline_player_uuid(DEFAULT_PLAYER)
    offline_file = playerdata / f"{offline_id}.dat"

    # Apply singleplayer inventory to the UUID the server actually uses
    if primary.name != offline_file.name:
        shutil.copy2(primary, offline_file)
        sp_dir = world_dir / "players" / "data"
        sp_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(primary, sp_dir / offline_file.name)


def sync_world_to_runtime(name: str) -> None:
    """Copy selected world into runtime/ (what the server actually mounts)."""
    source = WORLDS_DIR / name
    if not source.is_dir() or not (source / "level.dat").exists():
        raise HTTPException(404, f"World '{name}' not found or missing level.dat")

    stop_minecraft()

    if RUNTIME_DIR.exists():
        shutil.rmtree(RUNTIME_DIR)
    shutil.copytree(source, RUNTIME_DIR)
    migrate_player_data(RUNTIME_DIR)

    # Remove stale session lock from copied save
    lock = RUNTIME_DIR / "session.lock"
    if lock.exists():
        lock.unlink()

    start_minecraft()


def set_active(name: str) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    previous = get_active()
    if previous and previous != name and RUNTIME_DIR.exists():
        prev_dir = WORLDS_DIR / previous
        save_player_data_to_world(prev_dir, RUNTIME_DIR)
    ACTIVE_FILE.write_text(name)
    sync_world_to_runtime(name)


def restart_minecraft() -> str:
    get_container().restart(timeout=30)
    c = get_container()
    c.reload()
    return c.status


def ensure_runtime_world() -> None:
    """On startup, populate runtime if missing."""
    if (RUNTIME_DIR / "level.dat").exists():
        return
    active = get_active()
    if not active:
        return
    source = WORLDS_DIR / active
    if source.is_dir() and (source / "level.dat").exists():
        shutil.copytree(source, RUNTIME_DIR)
        migrate_player_data(RUNTIME_DIR)


def find_world_root(path: Path) -> Path | None:
    if (path / "level.dat").exists():
        return path
    for child in path.iterdir():
        if child.is_dir() and (child / "level.dat").exists():
            return child
    return None


def world_info(path: Path) -> dict:
    size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    active = get_active()
    return {
        "id": path.name,
        "name": path.name,
        "display_name": path.name.replace("-", " ").title(),
        "size_mb": round(size / 1024 / 1024, 1),
        "active": path.name == active,
        "valid": (path / "level.dat").exists(),
    }


@app.get("/")
async def index():
    return FileResponse("static/index.html")


@app.get("/api/worlds")
async def list_worlds():
    WORLDS_DIR.mkdir(parents=True, exist_ok=True)
    worlds = []
    for entry in sorted(WORLDS_DIR.iterdir()):
        if not entry.is_dir() or entry.name in SKIP_DIRS:
            continue
        if entry.name.startswith("."):
            continue
        worlds.append(world_info(entry))
    return {"active": get_active(), "worlds": worlds}


@app.get("/api/server/status")
async def server_status():
    try:
        client = docker.from_env()
        c = client.containers.get(CONTAINER_NAME)
        return {"container": CONTAINER_NAME, "status": c.status, "running": c.status == "running"}
    except NotFound:
        return {"container": CONTAINER_NAME, "status": "not_found", "running": False}


@app.post("/api/worlds/upload")
async def upload_world(
    file: UploadFile = File(...),
    name: str | None = Form(None),
):
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(400, "Upload a .zip file containing a Minecraft world folder")

    world_name = sanitize_name(name or Path(file.filename).stem)

    dest = WORLDS_DIR / world_name
    if dest.exists():
        raise HTTPException(409, f"World '{world_name}' already exists. Delete it first or pick another name.")

    WORLDS_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        zip_path = tmp_path / "upload.zip"

        size = 0
        with zip_path.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_MB * 1024 * 1024:
                    raise HTTPException(413, f"File too large (max {MAX_UPLOAD_MB} MB)")
                out.write(chunk)

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmp_path / "extracted")
        except zipfile.BadZipFile:
            raise HTTPException(400, "Invalid zip file")

        root = find_world_root(tmp_path / "extracted")
        if root is None:
            raise HTTPException(400, "No valid Minecraft world found (missing level.dat)")

        shutil.copytree(root, dest)
        migrate_player_data(dest)

    return {"ok": True, "world": world_info(dest)}


@app.post("/api/worlds/{world_id}/activate")
async def activate_world(world_id: str):
    world_id = sanitize_name(world_id)
    set_active(world_id)
    return {"ok": True, "active": world_id, "message": "World synced and server restarted"}


@app.delete("/api/worlds/{world_id}")
async def delete_world(world_id: str):
    world_id = sanitize_name(world_id)
    if get_active() == world_id:
        raise HTTPException(400, "Cannot delete the active world. Switch to another world first.")
    dest = WORLDS_DIR / world_id
    if not dest.exists():
        raise HTTPException(404, "World not found")
    shutil.rmtree(dest)
    return {"ok": True}


@app.post("/api/server/restart")
async def restart_server():
    status = restart_minecraft()
    return {"ok": True, "server_status": status}
