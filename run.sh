#!/bin/bash
echo "🔧 Setting up VPS Discord Bot..."

# Update packages
sudo apt update -y
sudo apt install -y python3 python3-venv python3-pip

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install requirements
pip install --upgrade pip
pip install -r requirements.txt

# Run the bot
echo "🚀 Starting bot..."
python3 lxc_vps_bot.py
