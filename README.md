🧠README.md
# 🧰 LXC VPS Discord Bot (Ubuntu/Debian)

This bot allows Discord admins to manage LXC containers directly from a Discord server — create VPS, assign plans, manage users, and more.

---

## 🧩 Requirements
- Ubuntu/Debian (no Docker, real VPS)
- Python 3.10+
- LXD/LXC installed and configured
- Discord Bot Token
- Admin Role ID

---

## ⚙️ Installation & Setup

### 1️⃣ Install Required Packages

# bash

```sudo apt update && sudo apt upgrade -y```
```sudo apt install -y git python3 python3-venv python3-pip lxd lxc```

### 2️⃣ Initialize LXD

```sudo lxd init```


# (Press Enter for defaults or configure manually.)

### 3️⃣ Clone Bot Repository

```git clone https://github.com/yourname/LXC-Discord-Bot.git```
``cd LXD_1``

### 4️⃣ Create and Activate Python Virtual Environment
```python3 -m venv venv```
```source venv/bin/activate```

### 5️⃣ Install Python Dependencies
```pip install -r requirements.txt```

### 6️⃣ Configure Your Bot

# Edit config.json:

```nano config.json```
# then 

{
  "BOT_TOKEN": " here pest your bot token ",
  "ADMIN_ROLE_ID": " here pest your admin roll ID "
}

### 7️⃣ Run the Bot
```bash run.sh```
------------------------------------------------------->
                 BOT  Functions 
------------------------------------------------------->
| Command                                | Description                 |
| -------------------------------------- | --------------------------- |
| `!create`                              | Create a new VPS            |
| `!delete-vps`                          | Delete a user's VPS         |
| `!myvps`                               | View your VPS info          |
| `!plans`                               | View available plans        |
| `!editplans <PLAN> <RAM> <CPU> <DISK>` | Admin: edit existing plan   |
| `!giveplan <USER> <PLAN>`              | Admin: assign plan manually |
| `!credits`                             | Show available credits      |
| `!buyc`                                | Buy a VPS with credits      |
| `!buywc`                               | Buy VPS without credits     |
| `!manage`                              | Admin: list all containers  |
