#!/data/data/com.termux/files/usr/bin/bash
# Install: ~/.termux/boot/nexus (after sshd script)
# Edit NEXUS_DIR to where you cloned the repo in Termux home
NEXUS_DIR="${NEXUS_DIR:-$HOME/nexus}"
sleep 45
proot-distro login ubuntu -- bash -lc "
  /usr/local/bin/start-docker.sh
  cd '$NEXUS_DIR' && docker compose -f docker-compose.yml -f docker-compose.android.yml up -d
"
