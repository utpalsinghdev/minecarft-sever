#!/data/data/com.termux/files/usr/bin/bash
# Install: copy to ~/.termux/boot/sshd on the phone
#   mkdir -p ~/.termux/boot
#   cp termux-boot-sshd.sh ~/.termux/boot/sshd
#   chmod +x ~/.termux/boot/sshd
sshd
if command -v termux-wake-lock >/dev/null 2>&1; then
  termux-wake-lock
fi
