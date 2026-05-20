#!/bin/bash
# Run inside: proot-distro login ubuntu
# Install: cp to /usr/local/bin/start-docker.sh && chmod +x
if docker info >/dev/null 2>&1; then
  echo "Docker already running"
  exit 0
fi
mkdir -p /var/run/docker
dockerd --storage-driver=vfs --iptables=false --ip6tables=false \
  -H unix:///var/run/docker.sock &
for i in $(seq 1 30); do
  docker info >/dev/null 2>&1 && echo "Docker ready" && exit 0
  sleep 1
done
echo "Docker failed to start" >&2
exit 1
