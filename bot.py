import os
import json
import datetime
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")
    await bot.change_presence(activity=discord.Game(name="Cosmic Galaxy | !help"))

@bot.command()
async def ping(ctx):
    await ctx.send(f"🏓 Pong! {round(bot.latency * 1000)}ms")

@bot.command()
async def daily(ctx):
    data = load_data()
    user_id = str(ctx.author.id)
    now = datetime.datetime.utcnow().timestamp()

    if user_id not in data:
        data[user_id] = {"credits": 0, "last_daily": 0}

    last_daily = data[user_id].get("last_daily", 0)
    cooldown = 86400  # 24 hours

    if now - last_daily < cooldown:
        remaining = int(cooldown - (now - last_daily))
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        await ctx.send(f"⏳ تقدر تاخد المكافأة بعد **{hours} ساعة و {minutes} دقيقة**.")
        return

    data[user_id]["credits"] += 100
    data[user_id]["last_daily"] = now
    save_data(data)
    await ctx.send(f"🎉 أخدت 100 كريدت اليومية! رصيدك الحالي: **{data[user_id]['credits']}**.")

@bot.command()
async def credits(ctx, member: discord.Member = None):
    member = member or ctx.author
    data = load_data()
    user_id = str(member.id)
    user_credits = data.get(user_id, {}).get("credits", 0)
    await ctx.send(f"💳 رصيد {member.mention} هو: **{user_credits}** كريدت.")

@bot.command()
@commands.is_owner()
async def addcredits(ctx, member: discord.Member, amount: int):
    data = load_data()
    user_id = str(member.id)
    if user_id not in data:
        data[user_id] = {"credits": 0, "last_daily": 0}

    data[user_id]["credits"] += amount
    save_data(data)
    await ctx.send(f"✅ تم إضافة {amount} كريدت لـ {member.mention}. رصيده الحالي: **{data[user_id]['credits']}**.")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int = 5):
    await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🧹 تم مسح {amount} رسائل.", delete_after=3)

@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="بدون سبب"):
    await member.kick(reason=reason)
    await ctx.send(f"🚨 تم طرد {member.mention} | السبب: {reason}")

token = os.getenv("DISCORD_TOKEN")
if token:
    bot.run(token)
else:
    print("Error: DISCORD_TOKEN variable is missing!")
      
