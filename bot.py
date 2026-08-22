import os
import datetime
import discord
from discord.ext import commands
import motor.motor_asyncio

# إعداد صلاحيات البوت
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# الاتصال بقاعدة البيانات السحابية
MONGO_URL = os.getenv("MONGO_URL")
cluster = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
db = cluster["CosmicGalaxyDB"]
users_col = db["users"]
commands_col = db["custom_commands"]

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} with MongoDB connected!")
    await bot.change_presence(activity=discord.Game(name="Cosmic Galaxy | !help"))

# معالجة الرسائل والأوامر المخصصة تلقائياً
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # فحص الأوامر المخصصة من قاعدة البيانات
    if message.content.startswith("!"):
        cmd_name = message.content[1:].strip().split()[0]
        custom_cmd = await commands_col.find_one({"name": cmd_name})
        if custom_cmd:
            await message.channel.send(custom_cmd["response"])
            return

    await bot.process_commands(message)

# --- أوامر التحكم في الأوامر المخصصة (للأدمن فقط) ---

# 1. إضافة أو تعديل أمر مخصص
@bot.command()
@commands.has_permissions(administrator=True)
async def addcmd(ctx, name: str, *, response: str):
    name = name.replace("!", "").strip()
    await commands_col.update_one(
        {"name": name},
        {"$set": {"response": response}},
        upsert=True
    )
    await ctx.send(f"✅ تم إضافة/تعديل الأمر `!{name}` بنجاح!")

# 2. حذف أمر مخصص
@bot.command()
@commands.has_permissions(administrator=True)
async def delcmd(ctx, name: str):
    name = name.replace("!", "").strip()
    result = await commands_col.delete_one({"name": name})
    if result.deleted_count > 0:
        await ctx.send(f"🗑️ تم حذف الأمر `!{name}`.")
    else:
        await ctx.send(f"❌ الأمر `!{name}` غير موجود أصلاً.")

# 3. عرض قائمة الأوامر المخصصة
@bot.command()
async def cmdlist(ctx):
    cmds = await commands_col.find().to_list(100)
    if not cmds:
        await ctx.send("📋 لا توجد أوامر مخصصة مضافة حالياً.")
        return
    
    msg = "**📋 الأوامر المخصصة المتاحة:**\n"
    for c in cmds:
        msg += f"• `!{c['name']}`\n"
    await ctx.send(msg)

# --- الأوامر الأساسية ---

@bot.command()
async def ping(ctx):
    await ctx.send(f"🏓 Pong! {round(bot.latency * 1000)}ms")

@bot.command()
async def daily(ctx):
    user_id = ctx.author.id
    now = datetime.datetime.utcnow().timestamp()
    cooldown = 86400  # 24 ساعة

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

@bot.command()
async def credits(ctx, member: discord.Member = None):
    member = member or ctx.author
    user_data = await users_col.find_one({"_id": member.id})
    user_credits = user_data.get("credits", 0) if user_data else 0
    await ctx.send(f"💳 رصيد {member.mention} هو: **{user_credits}** كريدت.")

# تشغيل البوت
token = os.getenv("DISCORD_TOKEN")
if token:
    bot.run(token)
else:
    print("Error: DISCORD_TOKEN missing!")
    
