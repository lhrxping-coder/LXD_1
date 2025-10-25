#!/bin/bash
set -e
WORKDIR="$PWD"
echo "== LXC VPS Discord Bot installer =="
sudo apt update -y
sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git curl jq squashfs-tools

# Try to ensure snapd + lxd are available (only on real systems)
if ! command -v lxc >/dev/null 2>&1; then
  if command -v snap >/dev/null 2>&1 || command -v snapd >/dev/null 2>&1; then
    echo "snapd present — trying to install lxd via snap (may fail inside containers)"
    sudo snap install lxd || true
    sudo lxd init --auto || true
  else
    echo "snap not installed or not usable. Skipping LXD install (you can install later)."
  fi
else
  echo "LXC found at $(which lxc)"
fi

# Python venv
if [ ! -d "venv" ]; then
  python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "Bootstrapping complete. Edit config.json, then run:"
echo "  source venv/bin/activate"
echo "  python3 lxc_vps_bot.py"
