# Termux on Android + SSH from Mac + Docker (Nexus)

Use your phone as the server, **control it from your Mac terminal**, and run Nexus in **Docker** so Java/version deps stay inside containers.

```
Mac Terminal  ──SSH──►  Termux (Android)  ──proot──►  Ubuntu  ──Docker──►  Nexus
```

---

## Part 1 — Termux on the phone (one-time)

### Install apps (F-Droid)

1. **Termux**
2. **Termux:Boot** (auto-start SSH + server after reboot)
3. **Termux:Wake Lock** (optional; helps 24/7)

### Base setup (run on the phone in Termux)

```bash
pkg update && pkg upgrade -y
pkg install -y openssh git proot-distro termux-auth
```

Set a password (needed for SSH):

```bash
passwd
```

Start SSH (Termux uses port **8022**):

```bash
sshd
```

Allow storage (to copy worlds / clone repo to shared folder):

```bash
termux-setup-storage
# tap Allow
```

Note your user and IP:

```bash
whoami          # e.g. u0_a123
ip -4 addr show wlan0 | grep inet   # e.g. 192.168.1.42
```

---

## Part 2 — SSH from your Mac

On your **Mac**:

```bash
ssh -p 8022 u0_a123@192.168.1.42
```

Replace `u0_a123` and IP with your values. Phone and Mac must be on the **same Wi‑Fi** (or use Tailscale below).

### Easier: SSH config on Mac

Add to `~/.ssh/config`:

```
Host android
    HostName 192.168.1.42
    Port 8022
    User u0_a123
```

Then:

```bash
ssh android
```

### SSH keys (no password each time)

On Mac:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/termux -N ""
ssh-copy-id -i ~/.ssh/termux.pub -p 8022 u0_a123@192.168.1.42
```

Update `Host android` with:

```
    IdentityFile ~/.ssh/termux
```

### Access from anywhere (optional)

Install **Tailscale** on Mac + phone → SSH to the phone’s Tailscale IP (100.x.x.x) instead of LAN IP.

---

## Part 3 — Ubuntu (proot) + Docker inside Termux

Docker does **not** run in plain Termux. It runs inside a small Ubuntu via **proot** (no root required).

### Install Ubuntu

In Termux:

```bash
proot-distro install ubuntu
```

### Enter Ubuntu

```bash
proot-distro login ubuntu
```

You should see a `root@localhost` prompt. All Docker commands run **inside** this environment.

### Install Docker in Ubuntu

```bash
apt update && apt upgrade -y
apt install -y docker.io docker-compose-v2 git curl

# Storage driver that works in proot (no real kernel cgroup)
mkdir -p /var/run/docker
dockerd --storage-driver=vfs --iptables=false --ip6tables=false -H unix:///var/run/docker.sock &
sleep 5
docker info
```

If `docker info` works, Docker is ready.

**Start dockerd after each reboot** (add to Ubuntu, not Termux):

```bash
echo '#!/bin/bash
dockerd --storage-driver=vfs --iptables=false --ip6tables=false -H unix:///var/run/docker.sock &
sleep 3' > /usr/local/bin/start-docker.sh
chmod +x /usr/local/bin/start-docker.sh
```

Run `/usr/local/bin/start-docker.sh` before `docker compose` each session (or use Termux:Boot — see Part 5).

---

## Part 4 — Deploy Nexus from your Mac

### Clone project (inside Ubuntu proot)

From Mac, SSH in and open Ubuntu:

```bash
ssh android
proot-distro login ubuntu
```

Inside Ubuntu:

```bash
# Termux home is visible here:
cd /data/data/com.termux/files/home
# or clone to shared storage:
mkdir -p /sdcard/nexus && cd /sdcard/nexus

git clone https://github.com/YOUR_USERNAME/nexus.git
cd nexus
cp .env.example .env
nano .env    # DEFAULT_PLAYER=whiterose
```

### Start Nexus (low RAM for phone)

```bash
/usr/local/bin/start-docker.sh
docker compose -f docker-compose.yml -f docker-compose.android.yml up -d --build
docker compose logs -f minecraft
```

Wait for: `Done! For help, type "help"`

- **Web UI on phone:** `http://127.0.0.1:8080` (browser on phone)
- **Web UI from Mac:** `http://192.168.1.42:8080` (phone LAN IP)
- **Minecraft:** `192.168.1.42:25565`

### Run compose from Mac in one shot

```bash
ssh android "proot-distro login ubuntu -- bash -lc 'cd ~/nexus && /usr/local/bin/start-docker.sh && docker compose -f docker-compose.yml -f docker-compose.android.yml up -d'"
```

Adjust path if you cloned elsewhere.

---

## Part 5 — 24/7: boot + wake lock

### Termux:Boot — start SSH on power-on

On phone (Termux, **not** Ubuntu), create:

`~/.termux/boot/01-sshd`:

```bash
#!/data/data/com.termux/files/usr/bin/bash
sshd
termux-wake-lock
```

```bash
chmod +x ~/.termux/boot/01-sshd
```

### Optional: start Docker + Minecraft on boot

`~/.termux/boot/02-nexus`:

```bash
#!/data/data/com.termux/files/usr/bin/bash
sleep 60
proot-distro login ubuntu -- bash -lc '/usr/local/bin/start-docker.sh && cd /data/data/com.termux/files/home/nexus && docker compose -f docker-compose.yml -f docker-compose.android.yml up -d'
```

Fix `cd` path to where you cloned `nexus`.

### Phone settings

- Keep **charger** connected  
- Termux → Battery → **Unrestricted**  
- Disable aggressive “kill background apps” for Termux (varies by OEM)

---

## Part 6 — Daily workflow from Mac

| Task | Command |
|------|---------|
| Shell on phone (Termux) | `ssh android` |
| Shell in Ubuntu + Docker | `ssh android` then `proot-distro login ubuntu` |
| Logs | `docker compose logs -f minecraft` |
| Restart | `docker compose restart` |
| Stop | `docker compose down` |
| Upload world | Browser → `http://<phone-ip>:8080` |

Copy world from Mac:

```bash
scp -P 8022 my-world.zip android:~/storage/downloads/
```

Then upload via web UI or unzip into `nexus/worlds/` on the phone.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Cannot connect to Docker daemon` | Run `/usr/local/bin/start-docker.sh` inside Ubuntu |
| `docker info` fails in proot | Confirm `--storage-driver=vfs --iptables=false` |
| SSH connection refused | Run `sshd` in Termux; check IP/port 8022 |
| Mac can’t open :8080 / :25565 | Same Wi‑Fi? Try phone IP; OEM firewall |
| OOM / server killed | Use `docker-compose.android.yml`; lower to `768M` in compose |
| Docker slow / hot phone | Normal on old hardware; reduce `VIEW_DISTANCE` |

### If Docker in proot won’t run

Some old phones block it. Fallback (still via SSH from Mac):

```bash
pkg install openjdk-21 tmux
cd ~/minecraft && java -Xmx1024M -jar server.jar nogui
```

You lose the web UI but keep “SSH from Mac + no Mac dependency.”

---

## Why this matches your plan

| Goal | How |
|------|-----|
| Terminal from Mac | SSH port 8022 → Termux |
| No dependency mess on phone | Java + server live in Docker images |
| Same Nexus project | `git clone` + same `docker compose` |
| 24/7 on old Android | Wake lock + Termux:Boot + charger + android compose overlay |

---

## Quick checklist

- [ ] Termux + openssh + `passwd` + `sshd`
- [ ] Mac SSH works: `ssh android`
- [ ] `proot-distro install ubuntu`
- [ ] Docker works: `dockerd` vfs + `docker info`
- [ ] Clone nexus, `.env`, `docker compose ... android.yml up -d`
- [ ] Connect Minecraft to `<phone-ip>:25565`
- [ ] Termux:Boot + battery unrestricted + charger
