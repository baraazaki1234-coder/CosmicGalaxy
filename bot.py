import os
import datetime
import discord
from discord.ext import commands
import motor.motor_asyncio

# إعداد صلاحيات البوت
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# الاتصال بقاعدة البيانات السحابية عبر المتغير البيئي
MONGO_URL = os.getenv("MONGO_URL")
cluster = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
db = cluster["CosmicGalaxyDB"]
users_col = db["users"]
settings_col = db["settings"]

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} with MongoDB connected!")
    await bot.change_presence(activity=discord.Game(name="Cosmic Galaxy | !help"))

# أمر فحص السرعة
@bot.command()
async def ping(ctx):
    await ctx.send(f"🏓 Pong! {round(bot.latency * 1000)}ms")

# أمر المكافأة اليومية
@bot.command()
async def daily(ctx):
    user_id = ctx.author.id
    now = datetime.datetime.utcnow().timestamp()
    cooldown = 86400  # 24 ساعة بالثواني

    user_data = await users_col.find_one({"_id": user_id})

    if user_data:
        last_daily = user_data.get("last_daily", 0)
        if now - last_daily < cooldown:
            remaining = int(cooldown - (now - last_daily))
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            await ctx.send(f"⏳ تقدر تاخد المكافأة بعد **{hours} ساعة و {minutes} دقيقة**.")
            return
        
        new_credits = user_data.get("credits", 0) + 100
        await users_col.update_one({"_id": user_id}, {"$set": {"credits": new_credits, "last_daily": now}})
    else:
        new_credits = 100
        await users_col.insert_one({"_id": user_id, "credits": new_credits, "last_daily": now})

    await ctx.send(f"🎉 أخدت 100 كريدت اليومية! رصيدك الحالي: **{new_credits}**.")

# أمر عرض الرصيد
@bot.command()
async def credits(ctx, member: discord.Member = None):
    member = member or ctx.author
    user_data = await users_col.find_one({"_id": member.id})
    user_credits = user_data.get("credits", 0) if user_data else 0
    await ctx.send(f"💳 رصيد {member.mention} هو: **{user_credits}** كريدت.")

# أمر إضافة كريدت (لصاحب البوت)
@bot.command()
@commands.is_owner()
async def addcredits(ctx, member: discord.Member, amount: int):
    user_data = await users_col.find_one({"_id": member.id})
    current_credits = user_data.get("credits", 0) if user_data else 0
    new_credits = current_credits + amount

    await users_col.update_one({"_id": member.id}, {"$set": {"credits": new_credits}}, upsert=True)
    await ctx.send(f"✅ تم إضافة {amount} كريدت لـ {member.mention}. رصيده الحالي: **{new_credits}**.")

# أمر مسح الرسائل
@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int = 5):
    await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🧹 تم مسح {amount} رسائل.", delete_after=3)

# تشغيل البوت عبر الـ Token
token = os.getenv("DISCORD_TOKEN")
if token:
    bot.run(token)
else:
    print("Error: DISCORD_TOKEN missing!")
    
