import os
import random
import discord
from discord.ext import commands

# إعداد الصلاحيات
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# تخزين مؤقت للرصيد
balances = {}

def get_balance(user_id):
    return balances.get(user_id, 100)

def add_balance(user_id, amount):
    balances[user_id] = get_balance(user_id) + amount

@bot.event
async def on_ready():
    print(f"تم تسجيل الدخول بنجاح باسم: {bot.user.name}")

# ================= 1. أوامر الأعضاء العامة =================

@bot.command()
async def ping(ctx):
    latency = round(bot.latency * 1000)
    await ctx.send(f"🏓 Pong! سرعة الاستجابة: **{latency}ms**")

@bot.command()
async def credits(ctx):
    user_balance = get_balance(ctx.author.id)
    await ctx.send(f"🪙 رصيد {ctx.author.mention}: **{user_balance}** كريدت")

@bot.command()
@commands.cooldown(1, 86400, commands.BucketType.user)  # 24 ساعة (86400 ثانية)
async def daily(ctx):
    add_balance(ctx.author.id, 100)
    await ctx.send(f"🎉 {ctx.author.mention}، أخذت مكافأتك اليومية بنجاح! (+100 كريدت)")

@daily.error
async def daily_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        seconds = int(error.retry_after)
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        await ctx.send(f"⏳ {ctx.author.mention}، انت أخذت المكافأة اليومية خلاص! فاضل **{hours} ساعة و {minutes} دقيقة**.")

@bot.command()
async def roll(ctx):
    number = random.randint(1, 100)
    await ctx.send(f"🎲 الرقم العشوائي لـ {ctx.author.mention} هو: **{number}**")

# ================= 2. أوامر إدارة السيرفر =================

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int = 5):
    await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🧹 تم مسح {amount} رسالة.", delete_after=3)

@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="بدون سبب"):
    await member.kick(reason=reason)
    await ctx.send(f"👢 تم طرد {member.mention} | السبب: {reason}")

# ================= 3. أوامر المالك (صاحب البوت فقط) =================

@bot.command()
@commands.is_owner()
async def restart(ctx):
    await ctx.send("🔄 جاري إعادة تشغيل البوت...")
    await bot.close()

@bot.command()
@commands.is_owner()
async def addcredits(ctx, member: discord.Member, amount: int):
    add_balance(member.id, amount)
    await ctx.send(f"✅ تم إضافة **{amount}** كريدت لحساب {member.mention}")

# ================= معالجة الأخطاء العامة =================

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ معندكش صلاحية لاستخدام الأمر ده!")
    elif isinstance(error, commands.NotOwner):
        await ctx.send("❌ الأمر ده مخصص لمالك البوت فقط!")

# تشغيل البوت عبر متغيرات البيئة
TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("BOT_TOKEN")
bot.run(TOKEN)
    
