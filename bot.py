import os
import random
import aiosqlite
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

DB_NAME = "database.db"

# إنشاء وتجهيز قاعدة البيانات
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                credits INTEGER DEFAULT 0,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1
            )
        """)
        await db.commit()

@bot.event
async def on_ready():
    await init_db()
    print(f"تم تشغيل البوت بنجاح باسم: {bot.user.name}")

# الترحيب بالأعضاء الجدد
@bot.event
async def on_member_join(member):
    channel = member.guild.system_channel
    if channel:
        await channel.send(f"أهلاً بك يا {member.mention} في السيرفر! 🎉")

# نظام الخبرة واللفل مع كل رسالة
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    user_id = message.author.id

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT credits, xp, level FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()

        if row is None:
            await db.execute("INSERT INTO users (user_id, credits, xp, level) VALUES (?, 100, 10, 1)", (user_id,))
        else:
            credits, xp, level = row
            new_xp = xp + 5
            new_level = level
            needed_xp = level * 100

            if new_xp >= needed_xp:
                new_level += 1
                await message.channel.send(f"🎉 مبروك {message.author.mention}! ارتفع مستواك إلى Level **{new_level}**!")

            await db.execute("UPDATE users SET xp = ?, level = ? WHERE user_id = ?", (new_xp, new_level, user_id))

        await db.commit()

    await bot.process_commands(message)

# الأوامر المالية (الاقتصاد)
@bot.command(name="credits", aliases=["balance", "رصيد", "فلوس"])
async def credits(ctx, member: discord.Member = None):
    target = member or ctx.author
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT credits FROM users WHERE user_id = ?", (target.id,)) as cursor:
            row = await cursor.fetchone()
            amount = row[0] if row else 0
    await ctx.send(f"🪙 رصيد **{target.display_name}**: `{amount}` كريدت")

@bot.command(name="daily", aliases=["راتب"])
async def daily(ctx):
    user_id = ctx.author.id
    reward = 200
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO users (user_id, credits) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET credits = credits + ?
        """, (user_id, reward, reward))
        await db.commit()
    await ctx.send(f"🎁 أخذت راتبك اليومي بقيمة **{reward}** كريدت!")

# أوامر البروفايل والمستوى
@bot.command(name="profile", aliases=["rank", "مستوى", "بروفايل"])
async def profile(ctx, member: discord.Member = None):
    target = member or ctx.author
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT xp, level FROM users WHERE user_id = ?", (target.id,)) as cursor:
            row = await cursor.fetchone()
            xp = row[0] if row else 0
            level = row[1] if row else 1
    await ctx.send(f"📊 **بروفايل {target.display_name}**:\nالمستوى: `{level}` | الخبرة: `{xp}/{level * 100}`")

# لعبة حظ رهانات بسيطة
@bot.command(name="roll", aliases=["رول", "حظ"])
async def roll(ctx, bet: int):
    if bet <= 0:
        await ctx.send("اكتب مبلغ أكبر من صفر!")
        return

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT credits FROM users WHERE user_id = ?", (ctx.author.id,)) as cursor:
            row = await cursor.fetchone()
            user_credits = row[0] if row else 0

        if user_credits < bet:
            await ctx.send("رصيدك لا يكفي لهذه الرهان!")
            return

        won = random.choice([True, False])
        if won:
            new_credits = user_credits + bet
            msg = f"🎉 كسبت الرهان وتربحت **{bet}** كريدت!"
        else:
            new_credits = user_credits - bet
            msg = f"❌ خسرت الرهان وضاع منك **{bet}** كريدت."

        await db.execute("UPDATE users SET credits = ? WHERE user_id = ?", (new_credits, ctx.author.id))
        await db.commit()

    await ctx.send(msg)

# استدعاء التوكن الخاص بالبوت من متغيرات البيئة أو استبداله بالتوكن المباشر
TOKEN = os.getenv("DISCORD_TOKEN", "ضع_التوكن_الخاص_بكبوتك_هنا")
bot.run(TOKEN)
             
