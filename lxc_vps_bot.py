import discord
from discord.ext import commands
import json
import os
import subprocess

CONFIG_FILE = "config.json"
DATA_FILE = "data.json"

# Load config
def load_config():
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

# Load data
def load_data():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w") as f:
            json.dump({"credits": {}}, f)
    with open(DATA_FILE, "r") as f:
        return json.load(f)

# Save data
def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

config = load_config()
BOT_TOKEN = config["BOT_TOKEN"]
ADMIN_ROLE_ID = int(config["ADMIN_ROLE_ID"])
plans = config["plans"]

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --------------------------- Helper ---------------------------

def is_admin(ctx):
    return any(role.id == ADMIN_ROLE_ID for role in ctx.author.roles)

# --------------------------- Commands ---------------------------

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await bot.change_presence(activity=discord.Game(name="VPS Control Panel"))

@bot.command()
async def plans(ctx):
    msg = "**📦 Available VPS Plans:**\n"
    for name, details in plans.items():
        msg += f"**{name.capitalize()}** — RAM: {details['ram']}, CPU: {details['cpu']}, Disk: {details['disk']}\n"
    await ctx.send(msg)

@bot.command()
async def credits(ctx):
    data = load_data()
    user_id = str(ctx.author.id)
    balance = data.get("credits", {}).get(user_id, 0)
    await ctx.send(f"💰 You have **{balance} credits.**")

@bot.command()
@commands.has_role(ADMIN_ROLE_ID)
async def givecredits(ctx, member: discord.Member, amount: int):
    data = load_data()
    user_id = str(member.id)
    credits = data.get("credits", {})

    old_balance = credits.get(user_id, 0)
    new_balance = old_balance + amount
    credits[user_id] = new_balance
    data["credits"] = credits
    save_data(data)

    await ctx.send(f"✅ Gave **{amount} credits** to {member.mention}. New balance: **{new_balance} credits**")

@bot.command()
@commands.has_role(ADMIN_ROLE_ID)
async def editplans(ctx, plan_name: str, ram: str, cpu: str, disk: str):
    plan_name = plan_name.lower()
    if plan_name in plans:
        plans[plan_name] = {"ram": ram, "cpu": cpu, "disk": disk}
        config["plans"] = plans
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
        await ctx.send(f"✅ Plan **{plan_name}** updated successfully.")
    else:
        await ctx.send("❌ Plan not found!")

@bot.command()
@commands.has_role(ADMIN_ROLE_ID)
async def giveplan(ctx, member: discord.Member, plan_name: str):
    plan_name = plan_name.lower()
    if plan_name not in plans:
        await ctx.send("❌ Invalid plan name.")
        return
    data = load_data()
    user_id = str(member.id)
    user_plans = data.get("user_plans", {})
    user_plans[user_id] = plan_name
    data["user_plans"] = user_plans
    save_data(data)
    await ctx.send(f"✅ Assigned plan **{plan_name}** to {member.mention}")

@bot.command()
@commands.has_role(ADMIN_ROLE_ID)
async def manage(ctx):
    data = load_data()
    user_plans = data.get("user_plans", {})
    if not user_plans:
        await ctx.send("No active containers found.")
        return
    msg = "**🧾 Active Containers:**\n"
    for uid, plan in user_plans.items():
        msg += f"<@{uid}> — {plan}\n"
    await ctx.send(msg)

@bot.command()
async def buyc(ctx, plan_name: str):
    plan_name = plan_name.lower()
    if plan_name not in plans:
        await ctx.send("❌ Invalid plan name.")
        return
    data = load_data()
    user_id = str(ctx.author.id)
    credits = data.get("credits", {}).get(user_id, 0)

    cost = 50  # Example price
    if credits < cost:
        await ctx.send(f"❌ You need {cost} credits but you only have {credits}.")
        return

    data["credits"][user_id] = credits - cost
    user_plans = data.get("user_plans", {})
    user_plans[user_id] = plan_name
    data["user_plans"] = user_plans
    save_data(data)
    await ctx.send(f"✅ VPS purchased successfully with plan **{plan_name}**!")

bot.run(BOT_TOKEN)
