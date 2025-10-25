#!/bin/bash
set -e

WORKDIR="$HOME/lxc_vps_bot"
SERVICE_NAME="lxc-vps-bot.service"

echo "=== LXC VPS Discord Bot installer for Ubuntu/Debian ==="

echo "[1/7] Update apt"
sudo apt update -y
sudo apt upgrade -y

echo "[2/7] Install prerequisites"
sudo apt install -y snapd python3 python3-venv python3-pip git curl jq squashfs-tools

echo "[3/7] Ensure snapd running"
sudo systemctl enable --now snapd.socket || true
sleep 2

# install LXD if not present
if ! command -v lxc >/dev/null 2>&1; then
  echo "[4/7] Installing LXD via snap..."
  sudo snap install lxd
  # add current user to lxd group
  sudo usermod -aG lxd $USER || true
  echo "[4.1] You may need to logout/login or run: newgrp lxd"
  # initialize LXD (non-interactive - default storage/network)
  sudo lxd init --auto || true
else
  echo "LXD already installed."
fi

echo "[5/7] Create working dir: $WORKDIR"
mkdir -p "$WORKDIR"
cd "$WORKDIR"

echo "[6/7] Create Python venv & install requirements"
if [ ! -d "venv" ]; then
  python3 -m venv venv
fi
source venv/bin/activate

# create default requirements if missing
if [ ! -f requirements.txt ]; then
  cat > requirements.txt <<'REQ'
discord.py==2.6.4
aiohttp==3.9.5
psutil==5.9.5
requests==2.32.3
aiosqlite==0.18.0
colorama==0.4.6
REQ
fi

pip install --upgrade pip
pip install -r requirements.txt

echo "[7/7] Create default config/plans if missing"
if [ ! -f config.json ]; then
  cat > config.json <<'JSON'
{
  "BOT_TOKEN": "YOUR_DISCORD_BOT_TOKEN_HERE",
  "ADMIN_ROLE_ID": "YOUR_ADMIN_ROLE_ID_HERE",
  "LXC_PATH": "/usr/bin/lxc",
  "FAKE_MODE_IF_NO_LXC": false
}
JSON
  echo "Created config.json template at $WORKDIR/config.json — edit it with your token & admin role id."
fi

if [ ! -f plans.json ]; then
  cat > plans.json <<'JSON'
{
  "basic": { "name": "Basic", "ram_mb": 512, "cpu": 1, "disk_gb": 10, "price": 1 },
  "small": { "name": "Small", "ram_mb": 1024, "cpu": 1, "disk_gb": 20, "price": 2 },
  "medium": { "name": "Medium", "ram_mb": 2048, "cpu": 2, "disk_gb": 40, "price": 4 },
  "large": { "name": "Large", "ram_mb": 4096, "cpu": 4, "disk_gb": 80, "price": 8 }
}
JSON
  echo "Created default plans.json"
fi

# create systemd service
SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME"
if [ ! -f "$SERVICE_PATH" ]; then
  sudo tee "$SERVICE_PATH" > /dev/null <<EOF
[Unit]
Description=LXC VPS Discord Bot
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$WORKDIR
Environment=PYTHONUNBUFFERED=1
ExecStart=$WORKDIR/venv/bin/python3 $WORKDIR/lxc_vps_bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

  sudo systemctl daemon-reload
  sudo systemctl enable --now "$SERVICE_NAME"
  echo "Created & started systemd service: $SERVICE_NAME"
else
  echo "Service already exists: $SERVICE_PATH"
fi

echo "=== Installer finished ==="
echo "Edit $WORKDIR/config.json to set BOT_TOKEN and ADMIN_ROLE_ID, then check logs:"
echo "sudo journalctl -u $SERVICE_NAME -f"
