"""Nexus web UI for phone — no Docker. Uses Java + tmux in ~/minecraft."""
import hashlib
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
import zipfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

logging.basicConfig(
    filename="/tmp/nexus-upload.log",
    level=logging.INFO,
    format="%(asctime)s %(message)s",
)
log = logging.getLogger("nexus")

HOME = Path.home()
BASE = Path(os.environ.get("NEXUS_HOME", HOME / "minecarft-sever"))
WORLDS_DIR = Path(os.environ.get("WORLDS_DIR", BASE / "worlds"))
CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", BASE / "config"))
ACTIVE_FILE = CONFIG_DIR / "active.txt"
LIVE_WORLD = Path(os.environ.get("LIVE_WORLD", HOME / "minecraft" / "world"))
MINECRAFT_DIR = LIVE_WORLD.parent
SERVER_JAR = Path(os.environ.get("SERVER_JAR", MINECRAFT_DIR / "server.jar"))
TMUX_SESSION = os.environ.get("TMUX_SESSION", "mc")
DEFAULT_PLAYER = os.environ.get("DEFAULT_PLAYER", "whiterose")
SKIP_DIRS = {"runtime", "active", ".DS_Store", "_incoming", "_tmp"}
MAX_UPLOAD_MB = 500
INCOMING_DIR = WORLDS_DIR / "_incoming"
upload_jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()

STATIC_DIR = Path(__file__).parent.parent / "web" / "static"

app = FastAPI(title="Nexus Phone")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def find_java() -> str:
    for candidate in [
        HOME / "jdk-25.0.3+9" / "bin" / "java",
        *sorted(HOME.glob("jdk-25*/bin/java")),
        Path("/usr/bin/java"),
    ]:
        if candidate.exists():
            return str(candidate)
    raise HTTPException(503, "Java 25 not found. Install Temurin JDK 25 in ~/jdk-25*")


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


def offline_player_uuid(username: str) -> str:
    data = f"OfflinePlayer:{username}".encode("utf-8")
    md5 = bytearray(hashlib.md5(data).digest())
    md5[6] = (md5[6] & 0x0F) | 0x30
    md5[8] = (md5[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(md5)))


def list_player_saves(world_dir: Path) -> list[Path]:
    saves = []
    data_dir = world_dir / "players" / "data"
    if data_dir.exists():
        for f in data_dir.glob("*.dat"):
            if "_old" not in f.name:
                saves.append(f)
    return saves


def migrate_player_data(world_dir: Path) -> None:
    playerdata = world_dir / "playerdata"
    playerdata.mkdir(exist_ok=True)
    saves = list_player_saves(world_dir)
    for src in saves:
        shutil.copy2(src, playerdata / src.name)
    if not saves:
        return
    primary = max(saves, key=lambda p: p.stat().st_size)
    offline_file = playerdata / f"{offline_player_uuid(DEFAULT_PLAYER)}.dat"
    if primary.name != offline_file.name:
        shutil.copy2(primary, offline_file)
        sp_dir = world_dir / "players" / "data"
        sp_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(primary, sp_dir / offline_file.name)


def save_live_world_to_archive(name: str) -> None:
    if not LIVE_WORLD.exists() or not (LIVE_WORLD / "level.dat").exists():
        return
    dest = WORLDS_DIR / name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(LIVE_WORLD, dest)


def mc_running() -> bool:
    r = subprocess.run(
        ["tmux", "has-session", "-t", TMUX_SESSION],
        capture_output=True,
    )
    return r.returncode == 0


def stop_minecraft() -> None:
    subprocess.run(["tmux", "kill-session", "-t", TMUX_SESSION], capture_output=True)


def start_minecraft() -> None:
    java = find_java()
    if not SERVER_JAR.exists():
        raise HTTPException(503, f"server.jar not found at {SERVER_JAR}")
    MINECRAFT_DIR.mkdir(parents=True, exist_ok=True)
    lock = LIVE_WORLD / "session.lock"
    if lock.exists():
        lock.unlink(missing_ok=True)
    cmd = (
        f"cd {MINECRAFT_DIR} && {java} -Xms512M -Xmx1024M "
        f"-jar server.jar nogui 2>&1 | tee -a server.log"
    )
    subprocess.run(
        ["tmux", "new-session", "-d", "-s", TMUX_SESSION, cmd],
        check=True,
    )


def sync_world_to_live(name: str) -> None:
    source = WORLDS_DIR / name
    if not source.is_dir() or not (source / "level.dat").exists():
        raise HTTPException(404, f"World '{name}' not found or missing level.dat")
    stop_minecraft()
    if LIVE_WORLD.exists():
        shutil.rmtree(LIVE_WORLD)
    shutil.copytree(source, LIVE_WORLD)
    migrate_player_data(LIVE_WORLD)
    start_minecraft()


def set_active(name: str) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    previous = get_active()
    if previous and previous != name and mc_running():
        save_live_world_to_archive(previous)
    ACTIVE_FILE.write_text(name)
    sync_world_to_live(name)


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
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/worlds")
async def list_worlds():
    WORLDS_DIR.mkdir(parents=True, exist_ok=True)
    worlds = []
    for entry in sorted(WORLDS_DIR.iterdir()):
        if not entry.is_dir() or entry.name in SKIP_DIRS or entry.name.startswith("."):
            continue
        worlds.append(world_info(entry))
    return {"active": get_active(), "worlds": worlds}


@app.get("/api/server/status")
async def server_status():
    return {
        "mode": "phone-java",
        "running": mc_running(),
        "session": TMUX_SESSION,
        "minecraft_port": 25565,
        "web_port": 8080,
    }


def _set_job(job_id: str, **kwargs) -> None:
    with jobs_lock:
        upload_jobs.setdefault(job_id, {})
        upload_jobs[job_id].update(kwargs)


def _get_job(job_id: str) -> dict | None:
    with jobs_lock:
        return upload_jobs.get(job_id, {}).copy() if job_id in upload_jobs else None


def _extract_zip(zip_path: Path, extract_dir: Path) -> None:
    """Prefer system unzip (lower RAM); fall back to zipfile."""
    extract_dir.mkdir(parents=True, exist_ok=True)
    if shutil.which("unzip"):
        r = subprocess.run(
            ["unzip", "-oq", str(zip_path), "-d", str(extract_dir)],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0:
            return
        log.warning("unzip failed: %s", r.stderr)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)


def _ensure_writable(path: Path) -> None:
    """Fix ownership/permissions so userland can write (UserLAnd/proot quirk)."""
    path = Path(path)
    if not path.exists():
        return
    if os.access(path, os.W_OK):
        return
    subprocess.run(["chmod", "-R", "u+rwX", str(path)], check=False)
    if not os.access(path, os.W_OK):
        subprocess.run(["sudo", "chown", "-R", f"{os.getuid()}:{os.getgid()}", str(path)], check=False)
        subprocess.run(["chmod", "-R", "u+rwX", str(path)], check=False)


def _remove_world(path: Path) -> None:
    path = Path(path)
    if not path.exists():
        return
    _ensure_writable(path.parent)
    shutil.rmtree(path, ignore_errors=True)
    subprocess.run(["sudo", "rm", "-rf", str(path)], check=False)


def _install_world(root: Path, dest: Path) -> None:
    _remove_world(dest)
    WORLDS_DIR.mkdir(parents=True, exist_ok=True)
    _ensure_writable(WORLDS_DIR)
    # move is faster than copy and avoids permission issues on partial trees
    shutil.move(str(root), str(dest))
    _ensure_writable(dest)
    for dirpath, _, filenames in os.walk(dest):
        os.chmod(dirpath, 0o755)
        for fn in filenames:
            try:
                os.chmod(os.path.join(dirpath, fn), 0o644)
            except OSError:
                pass


def _process_upload_job(job_id: str, zip_path: Path, world_name: str) -> None:
    dest = WORLDS_DIR / world_name
    tmp_extract = WORLDS_DIR / "_tmp" / job_id
    try:
        _set_job(job_id, status="extracting", message="Unpacking zip…")
        log.info("job %s extracting %s", job_id, zip_path)
        if tmp_extract.exists():
            shutil.rmtree(tmp_extract, ignore_errors=True)
        _extract_zip(zip_path, tmp_extract)
        root = find_world_root(tmp_extract)
        if root is None:
            raise ValueError("No level.dat found in zip")
        _set_job(job_id, status="extracting", message="Saving world…")
        _install_world(root, dest)
        migrate_player_data(dest)
        _set_job(job_id, status="done", message="Ready", world=world_info(dest))
        log.info("job %s done -> %s", job_id, dest)
    except Exception as e:
        log.exception("job %s failed", job_id)
        _set_job(job_id, status="error", message=str(e))
    finally:
        shutil.rmtree(tmp_extract, ignore_errors=True)
        zip_path.unlink(missing_ok=True)


@app.get("/api/worlds/upload/{job_id}/status")
async def upload_status(job_id: str):
    job = _get_job(job_id)
    if not job:
        raise HTTPException(404, "Unknown upload job")
    return job


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
        raise HTTPException(409, f"World '{world_name}' already exists. Delete it first.")

    WORLDS_DIR.mkdir(parents=True, exist_ok=True)
    INCOMING_DIR.mkdir(parents=True, exist_ok=True)

    job_id = uuid.uuid4().hex[:12]
    zip_path = INCOMING_DIR / f"{job_id}.zip"
    _set_job(job_id, status="uploading", received=0, total=None, world_name=world_name, message="Receiving file…")
    log.info("job %s upload start %s", job_id, file.filename)

    size = 0
    try:
        with zip_path.open("wb") as out:
            while chunk := await file.read(256 * 1024):
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_MB * 1024 * 1024:
                    zip_path.unlink(missing_ok=True)
                    _set_job(job_id, status="error", message=f"Max {MAX_UPLOAD_MB} MB")
                    raise HTTPException(413, f"File too large (max {MAX_UPLOAD_MB} MB)")
                out.write(chunk)
                _set_job(job_id, received=size, message=f"Uploaded {size // 1024 // 1024} MB…")
    except Exception:
        zip_path.unlink(missing_ok=True)
        raise

    log.info("job %s received %s bytes", job_id, size)
    _set_job(job_id, status="queued", received=size, message="Extracting (keep page open)…")
    threading.Thread(
        target=_process_upload_job,
        args=(job_id, zip_path, world_name),
        daemon=True,
    ).start()

    return {
        "ok": True,
        "job_id": job_id,
        "status": "queued",
        "message": "File received. Extracting in background…",
        "world_name": world_name,
    }


@app.post("/api/worlds/{world_id}/activate")
async def activate_world(world_id: str):
    world_id = sanitize_name(world_id)
    set_active(world_id)
    return {"ok": True, "active": world_id, "message": "World loaded and server restarted"}


@app.delete("/api/worlds/{world_id}")
async def delete_world(world_id: str):
    world_id = sanitize_name(world_id)
    if get_active() == world_id:
        raise HTTPException(400, "Cannot delete the active world. Switch first.")
    dest = WORLDS_DIR / world_id
    if not dest.exists():
        raise HTTPException(404, "World not found")
    shutil.rmtree(dest)
    return {"ok": True}


@app.post("/api/server/restart")
async def restart_server():
    active = get_active()
    if active:
        sync_world_to_live(active)
    elif LIVE_WORLD.exists():
        stop_minecraft()
        start_minecraft()
    else:
        raise HTTPException(400, "No world to run. Upload one first.")
    return {"ok": True, "running": mc_running()}
