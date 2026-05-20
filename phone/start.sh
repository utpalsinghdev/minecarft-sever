#!/bin/bash
# Start upload website on phone (port 8080)
cd "$(dirname "$0")/.."
export NEXUS_HOME="$HOME/minecarft-sever"
export DEFAULT_PLAYER="${DEFAULT_PLAYER:-whiterose}"
pip3 install -q -r phone/requirements.txt 2>/dev/null || pip install -q -r phone/requirements.txt
exec python3 -m uvicorn phone.app:app --host 0.0.0.0 --port 8080
