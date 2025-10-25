
---

## 5) `lxc_vps_bot.py` (FULL CODE)
Save as `lxc_vps_bot.py` and run inside the venv.

```python
#!/usr/bin/env python3
"""
lxc_vps_bot.py
Full-featured LXC VPS Discord bot with credit system, plans, admin tools.
Designed for Ubuntu/Debian (real LXD/LXC). If no LXC found, runs in TEST MODE.
"""

import os
import json
import shlex
import asyncio
import sqlite3
from datetime import datetime
from typing import Optional, Tuple

import discord
from discord.ext import commands

BASE = os.path.dirname(os.path.abspath(__file__))

# --- config ---
CFG_PATH = os.path.join(BASE, "config.json")
PLANS_PATH = os.path.join(BASE, "plans.json")
DB_PATH = os.path.join(BASE, "bot_data.db")

if not os.path.exists(CFG_PATH):
    raise SystemExit("Missing config.json — please create it.")

with open(CFG_PATH, "r") as f:
    CFG = json.load(f)

TOKEN = CFG.get("BOT_TOKEN")
ADMIN_ROLE_ID = str(CFG.get("ADMIN_ROLE_ID", ""))
LXC_PATHS = CFG.get("LXC_PATHS", ["/usr/bin/lxc", "/snap/bin/lxc"])
LXC_DEFAULT_IMAGE = CFG.get("LXC_DEFAULT_IMAGE", "images:ubuntu/22.04")
FAKE_IF_NO_LXC = bool(CFG.get("FAKE_IF_NO_LXC", True))

if not TOKEN:
    raise SystemExit("BOT_TOKEN missing in config.json")

# load plans (create default if missing)
if not os.path.exists(PLANS_PATH):
    default_plans = {
        "basic": { "name": "Basic", "ram_mb": 512, "cpu": 1, "disk_gb": 10, "price": 1 },
        "small": { "name": "Small", "ram_mb": 1024, "cpu": 1, "disk_gb": 20, "price": 2 },
        "medium": { "name": "Medium", "ram_mb": 2048, "cpu": 2, "disk_gb": 40, "price": 4 },
        "large": { "name": "Large", "ram_mb": 4096, "cpu": 4, "disk_gb": 80, "price": 8 }
    }
    with open(PLANS_PATH, "w") as f:
        json.dump(default_plans, f, indent=2)

with open(PLANS_PATH, "r") as f:
    PLANS = json.load(f)

# --- sqlite DB ---
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    credits INTEGER DEFAULT 0
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS vps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    container_name TEXT,
    plan TEXT,
    ram_mb INTEGER,
    cpu_cores INTEGER,
    arch TEXT,
    status TEXT,
    created_at TEXT
)
""")
conn.commit()

# --- LXC detection ---
LXC_PATH = None
for p in LXC_PATHS:
    if os.path.exists(p):
        LXC_PATH = p
        break

if LXC_PATH is None:
    # try 'which lxc'
    from shutil import which
    found = which("lxc")
    if found:
        LXC_PATH = found

TEST_MODE = False
if LXC_PATH is None:
    if FAKE_IF_NO_LXC:
        print("⚠️ LXC not found. Running in TEST MODE (no real containers).")
        TEST_MODE = True
    else:
        raise SystemExit("LXC not found and FAKE_IF_NO_LXC is false. Install LXC or enable fake mode.")

NAME_RE = __import__('re').compile(r"[^a-z0-9-]")

# --- helper DB functions ---
def get_credits(uid:int)->int:
    cur = conn.cursor()
    cur.execute("SELECT credits FROM users WHERE user_id = ?", (uid,))
    r = cur.fetchone()
    return r[0] if r else 0

def set_credits(uid:int, amount:int):
    cur = conn.cursor()
    cur.execute("INSERT INTO users(user_id, credits) VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET credits = ?",
                (uid, amount, amount))
    conn.commit()

def add_credits(uid:int, amount:int):
    cur = conn.cursor()
    cur.execute("INSERT INTO users(user_id, credits) VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET credits = credits + ?",
                (uid, amount, amount))
    conn.commit()

def remove_credits(uid:int, amount:int)->bool:
    cur = conn.cursor()
    cur.execute("SELECT credits FROM users WHERE user_id = ?", (uid,))
    r = cur.fetchone()
    if not r: return False
    new = max(0, r[0] - amount)
    cur.execute("UPDATE users SET credits = ? WHERE user_id = ?", (new, uid))
    conn.commit()
    return True

def create_vps_record(uid:int, cname:str, plan:str, ram:int, cpu:int, arch:str):
    cur = conn.cursor()
    cur.execute("INSERT INTO vps (user_id, container_name, plan, ram_mb, cpu_cores, arch, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (uid, cname, plan, ram, cpu, arch, "running", datetime.utcnow().isoformat()))
    conn.commit()
    return cur.lastrowid

def get_user_vps(uid:int):
    cur = conn.cursor()
    cur.execute("SELECT * FROM vps WHERE user_id = ?", (uid,))
    return cur.fetchall()

def get_vps_by_id(vps_id:int):
    cur = conn.cursor()
    cur.execute("SELECT * FROM vps WHERE id = ?", (vps_id,))
    return cur.fetchone()

def delete_vps_record(vps_id:int):
    cur = conn.cursor()
    cur.execute("DELETE FROM vps WHERE id = ?", (vps_id,))
    conn.commit()

# --- async lxc runner ---
async def run_lxc(args:list[str], timeout:int=300) -> Tuple[int,str,str]:
    """
    runs lxc command (args as list). returns (rc, stdout, stderr).
    In TEST_MODE returns simulated success.
    """
    if TEST_MODE:
        await asyncio.sleep(0.1)
        return 0, "(test) " + " ".join(shlex.quote(a) for a in args), ""
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return 124, "", "timeout"
    return proc.returncode, (out.decode(errors="ignore") if out else ""), (err.decode(errors="ignore") if err else "")

async def create_container(name:str, image:str=None, profiles:str=None, ram_mb:Optional[int]=None, cpu_cores:Optional[int]=None) -> Tuple[bool,str]:
    image = image or LXC_DEFAULT_IMAGE
    profiles = profiles or "default"
    rc,out,err = await run_lxc([LXC_PATH, "launch", image, name, "-p", profiles])
    if rc != 0:
        return False, err or out
    if ram_mb is not None:
        await run_lxc([LXC_PATH, "config", "set", name, "limits.memory", str(ram_mb * 1024 * 1024)])
    if cpu_cores is not None:
        await run_lxc([LXC_PATH, "config", "set", name, "limits.cpu", str(cpu_cores)])
    return True, out or "created"

async def delete_container(name:str) -> Tuple[bool,str]:
    await run_lxc([LXC_PATH, "stop", name, "--force"])
    rc,out,err = await run_lxc([LXC_PATH, "delete", name])
    if rc != 0:
        return False, err or out
    return True, "deleted"

async def action_container(name:str, action:str) -> Tuple[bool,str]:
    if action not in ("start","stop","restart","info"):
        return False, "invalid action"
    if action == "info":
        rc,out,err = await run_lxc([LXC_PATH, "info", name])
    else:
        rc,out,err = await run_lxc([LXC_PATH, action, name])
    if rc != 0:
        return False, err or out
    return True, out or "OK"

# --- discord bot ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

def is_admin_ctx(ctx) -> bool:
    if ctx.author.guild_permissions.administrator:
        return True
    try:
        rid = int(ADMIN_ROLE_ID)
        return any(role.id == rid for role in ctx.author.roles)
    except Exception:
        return False

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} | LXC_path={LXC_PATH} | TEST_MODE={TEST_MODE}")

# ---------- Commands ----------

@bot.command(name="plans")
async def cmd_plans(ctx):
    embed = discord.Embed(title="Available Plans", color=discord.Color.green())
    for key,p in PLANS.items():
        embed.add_field(name=f"{key}", value=f"{p.get('name','')}\nRAM: {p['ram_mb']}MB\nCPU: {p['cpu']}\nDisk: {p['disk_gb']}GB\nPrice: {p['price']} credits", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="credits")
async def cmd_credits(ctx):
    amt = get_credits(ctx.author.id)
    await ctx.send(f"{ctx.author.mention} — you have **{amt}** credits.")

@bot.command(name="givecredits")
async def cmd_givecredits(ctx, member:discord.Member, amount:int):
    if not is_admin_ctx(ctx):
        return await ctx.send("❌ You are not authorized.")
    add_credits(member.id, amount)
    await ctx.send(f"✅ Added {amount} credits to {member.mention} (new balance: {get_credits(member.id)}).")

@bot.command(name="buyc")
async def cmd_buyc(ctx, plan:str):
    plan = plan.lower()
    if plan not in PLANS:
        return await ctx.send("Unknown plan. Use `!plans`.")
    cost = PLANS[plan]["price"]
    bal = get_credits(ctx.author.id)
    if bal < cost:
        return await ctx.send(f"You need {cost} credits but have {bal}.")
    # create container
    base = f"user{ctx.author.id}-{plan}"
    safe = NAME_RE.sub("", base.lower())
    suffix = datetime.utcnow().strftime("%y%m%d%H%M%S")
    container_name = f"{safe}-{suffix}"
    await ctx.send(f"Creating container `{container_name}` (plan {plan}) — this may take a minute...")
    ok,msg = await create_container(container_name, ram_mb=PLANS[plan]["ram_mb"], cpu_cores=PLANS[plan]["cpu"])
    if not ok:
        return await ctx.send(f"Failed to create container: ```{msg}```")
    remove_credits(ctx.author.id, cost)
    vid = create_vps_record(ctx.author.id, container_name, plan, PLANS[plan]["ram_mb"], PLANS[plan]["cpu"], "intel")
    await ctx.send(f"✅ Created `{container_name}` (ID {vid}). {cost} credits deducted.")

@bot.command(name="buywc")
async def cmd_buywc(ctx, plan:str):
    plan = plan.lower()
    if plan not in PLANS:
        return await ctx.send("Unknown plan. Use `!plans`.")
    # create container (no credit check)
    base = f"user{ctx.author.id}-{plan}"
    safe = NAME_RE.sub("", base.lower())
    suffix = datetime.utcnow().strftime("%y%m%d%H%M%S")
    container_name = f"{safe}-{suffix}"
    await ctx.send(f"Creating container `{container_name}` (plan {plan}) — this may take a minute...")
    ok,msg = await create_container(container_name, ram_mb=PLANS[plan]["ram_mb"], cpu_cores=PLANS[plan]["cpu"])
    if not ok:
        return await ctx.send(f"Failed to create container: ```{msg}```")
    vid = create_vps_record(ctx.author.id, container_name, plan, PLANS[plan]["ram_mb"], PLANS[plan]["cpu"], "intel")
    await ctx.send(f"✅ Created `{container_name}` (ID {vid}).")

@bot.command(name="myvps")
async def cmd_myvps(ctx):
    rows = get_user_vps(ctx.author.id)
    if not rows:
        return await ctx.send("You have no VPS.")
    lines=[]
    for r in rows:
        lines.append(f"ID {r['id']}: `{r['container_name']}` — {r['plan']} — {r['ram_mb']}MB/{r['cpu_cores']}cpu — {r['status']}")
    await ctx.send("Your VPS:\n" + "\n".join(lines))

@bot.command(name="create")
async def cmd_create(ctx, plan:str="basic"):
    # convenience: admin or user can run to create using own account (no credits)
    plan = plan.lower()
    if plan not in PLANS:
        return await ctx.send("Unknown plan. Use `!plans`.")
    base = f"user{ctx.author.id}-{plan}"
    safe = NAME_RE.sub("", base.lower())
    suffix = datetime.utcnow().strftime("%y%m%d%H%M%S")
    container_name = f"{safe}-{suffix}"
    await ctx.send(f"Creating container `{container_name}` (plan {plan}) ...")
    ok,msg = await create_container(container_name, ram_mb=PLANS[plan]["ram_mb"], cpu_cores=PLANS[plan]["cpu"])
    if not ok:
        return await ctx.send(f"Failed to create container: ```{msg}```")
    vid = create_vps_record(ctx.author.id, container_name, plan, PLANS[plan]["ram_mb"], PLANS[plan]["cpu"], "intel")
    await ctx.send(f"✅ Created `{container_name}` (ID {vid}).")

@bot.command(name="manage")
async def cmd_manage(ctx, action:str=None, vps_id:int=None):
    # Admin command: list or manage containers.
    if not is_admin_ctx(ctx):
        return await ctx.send("❌ You are not authorized.")
    if action is None:
        # list DB records
        cur = conn.cursor()
        cur.execute("SELECT * FROM vps")
        rows = cur.fetchall()
        if not rows:
            return await ctx.send("No vps records.")
        lines=[]
        for r in rows:
            lines.append(f"ID {r['id']}: {r['container_name']} (user {r['user_id']}) - {r['plan']}")
        return await ctx.send("VPS Records:\n" + "\n".join(lines))
    # manage single vps: action start|stop|restart|info|delete
    if vps_id is None:
        return await ctx.send("Usage: `!manage <start|stop|restart|info|delete> <vps_id>`")
    row = get_vps_by_id(vps_id)
    if not row:
        return await ctx.send("VPS not found.")
    name = row['container_name']
    action = action.lower()
    if action == "delete":
        await ctx.send(f"Deleting `{name}`...")
        ok,msg = await delete_container(name)
        if not ok:
            return await ctx.send(f"Failed: ```{msg}```")
        delete_vps_record(vps_id)
        return await ctx.send(f"✅ Deleted {name}.")
    if action not in ("start","stop","restart","info"):
        return await ctx.send("Invalid action.")
    ok,msg = await action_container(name, action)
    if not ok:
        return await ctx.send(f"Failed: ```{msg}```")
    return await ctx.send(f"Action `{action}` executed on `{name}`.\n```{msg[:1500]}```")

@bot.command(name="delete-vps")
async def cmd_delete_vps(ctx, vps_id:int):
    row = get_vps_by_id(vps_id)
    if not row:
        return await ctx.send("VPS not found.")
    if row['user_id'] != ctx.author.id and not is_admin_ctx(ctx):
        return await ctx.send("You don't have permission.")
    name = row['container_name']
    await ctx.send(f"Deleting `{name}`...")
    ok,msg = await delete_container(name)
    if not ok:
        return await ctx.send(f"Failed: ```{msg}```")
    delete_vps_record(vps_id)
    await ctx.send(f"✅ Deleted {name}.")

@bot.command(name="editplans")
async def cmd_editplans(ctx, plan_name:str, ram_mb:int, cpu:int, disk_gb:int, price:int=None):
    if not is_admin_ctx(ctx):
        return await ctx.send("Unauthorized.")
    key = plan_name.lower()
    if key not in PLANS:
        return await ctx.send("Plan not found.")
    PLANS[key].update({"ram_mb":ram_mb, "cpu":cpu, "disk_gb":disk_gb})
    if price is not None:
        PLANS[key]["price"] = price
    with open(PLANS_PATH, "w") as f:
        json.dump(PLANS, f, indent=2)
    await ctx.send(f"✅ Plan `{key}` updated: {ram_mb}MB RAM, {cpu} CPU, {disk_gb}GB disk. Price: {PLANS[key].get('price')}")

@bot.command(name="giveplan")
async def cmd_giveplan(ctx, member:discord.Member, plan_name:str):
    if not is_admin_ctx(ctx):
        return await ctx.send("Unauthorized.")
    key = plan_name.lower()
    if key not in PLANS:
        return await ctx.send("Plan not found.")
    plan = PLANS[key]
    base = f"user{member.id}-{key}"
    safe = NAME_RE.sub("", base.lower())
    suffix = datetime.utcnow().strftime("%y%m%d%H%M%S")
    container_name = f"{safe}-{suffix}"
    await ctx.send(f"Creating `{container_name}` for {member.mention} ...")
    ok,msg = await create_container(container_name, ram_mb=plan['ram_mb'], cpu_cores=plan['cpu'])
    if not ok:
        return await ctx.send(f"Failed to create: ```{msg}```")
    create_vps_record(member.id, container_name, key, plan['ram_mb'], plan['cpu'], "intel")
    await ctx.send(f"✅ Gave plan `{key}` to {member.mention}. Container: `{container_name}`")

# error handler
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Missing argument for that command.")
    elif isinstance(error, commands.CommandNotFound):
        await ctx.send("Command not found.")
    else:
        await ctx.send(f"Error: {error}")
        raise error

if __name__ == "__main__":
    bot.run(TOKEN)
