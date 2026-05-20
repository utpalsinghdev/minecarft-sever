# Running Nexus on an old Android phone (24/7 server)

This guide covers running your Minecraft server on Android so it stays up all day. **Old phones are tight on RAM** — read [feasibility](#feasibility) first.

## Feasibility

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| RAM (free) | 3 GB | 4 GB+ |
| Storage | 2 GB free | 8 GB+ (worlds grow) |
| Android | 8+ (64-bit) | 10+ |
| CPU | ARM64 (aarch64) | Snapdragon 6-series or better |
| Power | Charger 24/7 | Yes — avoid battery swelling |

**Honest note:** A Raspberry Pi 4 or old laptop is usually easier and cooler than an old phone. Android is doable in **Termux** (simpler) or **Linux + Docker** (full Nexus UI).

---

## Path A — Termux only (best for old Android)

No Docker. Minecraft + optional manual world swaps. Lightest on the phone.

### 1. Install Termux

Use **[F-Droid](https://f-droid.org/en/packages/com.termux/)** (not Play Store — that build is outdated).

Also install (optional but useful):

- **Termux:Boot** — start server when phone boots  
- **Termux:Wake Lock** — CPU stays on while server runs  

### 2. Install Java and tools

```bash
pkg update && pkg upgrade -y
pkg install -y openjdk-21 wget tmux
```

### 3. Create server folder

```bash
mkdir -p ~/minecraft && cd ~/minecraft
wget https://piston-data.mojang.com/v1/objects/.../server.jar -O server.jar
```

Get the exact `server.jar` URL for your version from [MCVersions](https://mcversions.net/) or copy `server.jar` from your Mac after running Nexus once (from Docker volume or download once on PC).

**Easier:** On your Mac, after `docker compose up`, copy the jar out:

```bash
docker cp nexus-minecraft:/data/server.jar ~/server.jar
```

Then send `server.jar` to the phone (USB, Google Drive, `termux-setup-storage`).

### 4. Accept EULA and add your world

```bash
cd ~/minecraft
echo "eula=true" > eula.txt
mkdir world
# Copy your world into ~/minecraft/world/ (with level.dat inside)
# Use Termux storage or adb push
```

### 5. Start server (low memory)

```bash
termux-wake-lock
tmux new -s mc
java -Xms512M -Xmx1024M -jar server.jar nogui
```

Detach from tmux: `Ctrl+B` then `D`. Reattach: `tmux attach -t mc`.

### 6. Autostart on boot (Termux:Boot)

Create `~/.termux/boot/start-minecraft`:

```bash
#!/data/data/com.termux/files/usr/bin/bash
termux-wake-lock
sleep 30
cd ~/minecraft && tmux new-session -d -s mc 'java -Xms512M -Xmx1024M -jar server.jar nogui'
```

```bash
chmod +x ~/.termux/boot/start-minecraft
```

### 7. Connect from another device

On the phone (Termux):

```bash
ip -4 addr show wlan0 | grep inet
```

On PC Minecraft: **Multiplayer** → Add server → `<phone-ip>:25565`  
Same Minecraft version as `server.jar` (e.g. **26.1.2**).

Set in `server.properties` (create after first run):

```properties
online-mode=false
max-players=5
view-distance=6
simulation-distance=6
```

Lower view distance = less lag on weak phones.

---

## Path B — Full Nexus (Docker + web UI)

Use if the phone has **4 GB+ RAM** and you want upload/switch worlds like on your Mac.

### Option: UserLAnd / Linux Deploy (Ubuntu arm64)

1. Install **UserLAnd** or **Linux Deploy** → Ubuntu  
2. Inside Linux:

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin git
sudo usermod -aG docker $USER
# log out and back in

git clone https://github.com/YOUR_USERNAME/nexus.git
cd nexus
cp .env.example .env
# edit .env → DEFAULT_PLAYER=whiterose
```

3. Use the Android compose file (less RAM):

```bash
docker compose -f docker-compose.yml -f docker-compose.android.yml up -d --build
```

4. Web UI on phone browser: `http://127.0.0.1:8080`  
   From laptop on same Wi‑Fi: `http://<phone-ip>:8080`

**Caveats on Android:**

- Docker in proot/chroot is **slow** and may crash under heat  
- Web UI needs Docker socket — same as Mac setup  
- Keep phone **plugged in** and **Wi‑Fi** on; disable battery optimization for Termux / UserLAnd  

---

## Keep the server running all day

| Tip | Why |
|-----|-----|
| Charger always connected | Avoids sleep and battery damage |
| `termux-wake-lock` | Stops CPU deep sleep killing Java |
| Disable battery optimization | Settings → Apps → Termux → Unrestricted |
| Use **tmux** | Survives accidental terminal close |
| Lower `view-distance` | Less CPU/RAM |
| `-Xmx1024M` or `768M` on old phones | Prevents OOM kill |
| Wi‑Fi only | Mobile data + NAT is painful for hosting |

---

## Play from outside your home (optional)

1. Router **port forward** `25565` → phone’s local IP  
2. Or use **playit.gg** / **ngrok** TCP tunnel (easier on restricted networks)  
3. Give friends your **public IP** (search “what is my ip” on home network)  

Security: keep `online-mode=false` only for trusted friends; use whitelist in `server.properties`:

```properties
white-list=true
enforce-whitelist=true
```

Then `/whitelist add PlayerName` in server console.

---

## Transfer worlds Mac → Android

1. Zip world on Mac (`level.dat` inside folder)  
2. Upload via Nexus web UI if using Path B  
3. Path A: copy into `~/minecraft/world/` and restart server  

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Server killed / “Killed” | Lower `-Xmx` to `768M` or `512M` |
| Phone very hot | Lower view-distance; fewer players; remove phone case |
| Can’t connect | Same Wi‑Fi? Firewall? Correct IP? Version match? |
| Lag | `view-distance=4`, `max-players=2` |
| Termux stops in background | Wake lock + disable battery optimization |

---

## Quick recommendation

| Your phone | Use |
|------------|-----|
| Old (2–3 GB RAM) | **Path A — Termux**, 512M–1G heap, no web UI |
| Mid (4 GB RAM) | **Path A** or **Path B** with `docker-compose.android.yml` |
| Newer (6 GB+) | **Path B** full Nexus |

Your Nexus project on GitHub is built for **Path B** on a Linux host; Path A is the practical daily driver for a weak Android.
