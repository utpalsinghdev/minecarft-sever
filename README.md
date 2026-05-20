# Nexus

Dockerized **Minecraft Java** server with a web UI to upload worlds, switch saves, and play locally or on LAN.

![Minecraft](https://img.shields.io/badge/Minecraft-26.1.2-green?style=flat-square)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)

## Features

- **Web UI** at `http://localhost:8080` — Minecraft-styled manager
- **Drag & drop** world uploads (`.zip` with `level.dat`)
- **Switch worlds** — pick a save; server restarts with that world
- **Player data migration** — singleplayer inventory mapped for offline mode
- **Vanilla server** via [itzg/minecraft-server](https://github.com/itzg/docker-minecraft-server)

## Requirements

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine + Compose v2)
- Minecraft **Java Edition 26.1.2** (client version must match server)

## Quick start

```bash
git clone https://github.com/YOUR_USERNAME/nexus.git
cd nexus

# Set your in-game username (offline mode)
cp .env.example .env
# Edit .env → DEFAULT_PLAYER=YourUsername

docker compose up -d --build
```

| Service | Address |
|---------|---------|
| Web UI | http://localhost:8080 |
| Minecraft | `localhost:25565` |

1. Open the web UI and upload a world (zip your save folder from `~/Library/Application Support/minecraft/saves/…` on Mac).
2. Click **Play** on a world to activate it.
3. In Minecraft: **Multiplayer** → **Add Server** → `localhost`.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DEFAULT_PLAYER` | `Steve` | Username you use to join (must match for inventory migration) |
| `VERSION` | `26.1.2` | Minecraft server version in `docker-compose.yml` |
| `MEMORY` | `2G` | JVM heap for the server |
| `ONLINE_MODE` | `false` | Set `true` if all players use licensed accounts |

Create `.env` from `.env.example`:

```env
DEFAULT_PLAYER=YourUsername
```

## Project structure

```
nexus/
├── docker-compose.yml   # Minecraft + web services
├── .env.example
├── web/
│   ├── app.py           # FastAPI backend
│   ├── Dockerfile
│   └── static/
│       └── index.html   # Web UI
├── worlds/              # Your uploaded saves (gitignored)
│   └── .gitkeep
└── config/              # Active world id (gitignored)
    └── .gitkeep
```

## Commands

```bash
docker compose up -d --build   # Start / rebuild
docker compose down            # Stop
docker compose logs -f minecraft
docker compose logs -f web
```

## LAN play

Find your machine IP:

```bash
# macOS
ipconfig getifaddr en0

# Linux
hostname -I | awk '{print $1}'
```

Friends connect to `<your-ip>:25565` with the same Minecraft version.

## How world switching works

1. Worlds are stored in `worlds/<name>/`.
2. Activating a world copies it to `worlds/runtime/` (what the server mounts).
3. Progress is saved back to the archive when you switch away.
4. Player files are migrated from singleplayer `players/data/` to server `playerdata/`.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Can't connect | Wait for `Done!` in `docker compose logs minecraft` |
| Wrong / missing items | Set `DEFAULT_PLAYER` in `.env` to your exact login name, re-activate world |
| Version mismatch | Use Minecraft **26.1.2** on client and server |
| World won't switch | Allow ~1 min for copy + restart; check logs |

## Run on an old Android phone (24/7)

| Guide | Use case |
|-------|----------|
| **[docs/TERMUX-MAC-DOCKER.md](docs/TERMUX-MAC-DOCKER.md)** | **Termux + SSH from Mac + Docker** (recommended) |
| [docs/ANDROID.md](docs/ANDROID.md) | Overview, Termux-only fallback, feasibility |

Helper scripts: `scripts/termux-boot-sshd.sh`, `scripts/ubuntu-start-docker.sh`, `scripts/termux-boot-nexus.sh`

```bash
# Low-RAM overlay (Linux on Android)
docker compose -f docker-compose.yml -f docker-compose.android.yml up -d --build
```

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgments

- [itzg/docker-minecraft-server](https://github.com/itzg/docker-minecraft-server)
