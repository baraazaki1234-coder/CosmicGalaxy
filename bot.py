import os
import datetime
import asyncio
import random
from PIL import Image, ImageDraw, ImageFont
import io
import discord
from discord.ext import commands
import motor.motor_asyncio

# إعداد الصلاحيات
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command("help")  # إلغاء أمر المساعدة الافتراضي

# الاتصال بقاعدة البيانات
MONGO_URL = os.getenv("MONGO_URL")
cluster = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
db = cluster["CosmicGalaxyDB"]

users_col = db["users"]
guilds_col = db["guilds"]
warns_col = db["warns"]
commands_col = db["custom_commands"]

CURRENCY_NAME = "مجرات"
BAD_WORDS = ["شتيمة1", "شتيمة2"]  # ضيف الكلمات المحظورة هنا
user_message_timestamps = {}  # لمتابعة Anti-Spam

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} | All Cosmic Galaxy systems active!")
    await bot.change_presence(activity=discord.Game(name="Cosmic Galaxy | !help"))

# --- إرسال سجلات الحماية واللوج (Audit Log) ---
async def send_log(guild, embed):
    guild_data = await guilds_col.find_one({"_id": guild.id}) or {}
    log_channel_id = guild_data.get("log_channel")
    if log_channel_id:
        channel = guild.get_channel(log_channel_id)
        if channel:
            await channel.send(embed=embed)

# --- أحداث الحماية والردود التلقائية والـ Audit Log ---
@bot.event
async def on_member_join(member):
    guild = member.guild
    guild_data = await guilds_col.find_one({"_id": guild.id}) or {}

    # حماية من البوتات غير الموثوقة (Anti-Bots)
    if member.bot and guild_data.get("anti_bots", False):
        await member.kick(reason="الحماية: منع دخول البوتات التلقائي مفعل.")
        return

    # الرتبة التلقائية
    auto_role_id = guild_data.get("autorole")
    if auto_role_id:
        role = guild.get_role(auto_role_id)
        if role:
            await member.add_roles(role)

    # الترحيب
    welcome_channel_id = guild_data.get("welcome_channel")
    if welcome_channel_id:
        channel = guild.get_channel(welcome_channel_id)
        if channel:
            embed = discord.Embed(
                title="✨ عضو جديد انضم للمجرة!",
                description=f"أهلاً بك {member.mention} في **{guild.name}**!\nنتمنى لك وقتاً ممتعاً 🚀",
                color=discord.Color.purple()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            await channel.send(embed=embed)

    # تسجيل اللوج
    embed_log = discord.Embed(title="📥 انضمام عضو جديد", description=f"{member.mention} ({member.name})", color=discord.Color.green())
    await send_log(guild, embed_log)

@bot.event
async def on_member_remove(member):
    embed_log = discord.Embed(title="📤 مغادرة عضو", description=f"{member.name} غادر السيرفر.", color=discord.Color.red())
    await send_log(member.guild, embed_log)

@bot.event
async def on_message_delete(message):
    if message.author.bot or not message.guild:
        return
    embed = discord.Embed(title="🗑️ حذف رسالة", color=discord.Color.orange())
    embed.add_field(name="الكاتب", value=message.author.mention, inline=True)
    embed.add_field(name="القناة", value=message.channel.mention, inline=True)
    embed.add_field(name="المحتوى", value=message.content or "محتوى غير نصي", inline=False)
    await send_log(message.guild, embed)

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or not before.guild or before.content == after.content:
        return
    embed = discord.Embed(title="✏️ تعديل رسالة", color=discord.Color.blue())
    embed.add_field(name="الكاتب", value=before.author.mention, inline=True)
    embed.add_field(name="قبل", value=before.content, inline=False)
    embed.add_field(name="بعد", value=after.content, inline=False)
    await send_log(before.guild, embed)

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    content = message.content.lower()
    guild_id = message.guild.id
    user_id = message.author.id
    guild_data = await guilds_col.find_one({"_id": guild_id}) or {}

    # 1. نظام منع التكرار السريع (Anti-Spam)
    if guild_data.get("anti_spam", True):
        now = datetime.datetime.utcnow().timestamp()
        timestamps = user_message_timestamps.get(user_id, [])
        timestamps = [t for t in timestamps if now - t < 2]  # رسائل آخر ثانيتين
        timestamps.append(now)
        user_message_timestamps[user_id] = timestamps

        if len(timestamps) > 5:
            await message.author.timeout(datetime.timedelta(minutes=10), reason="Anti-Spam تلقائي")
            await message.channel.send(f"🔇 تم إسكات {message.author.mention} لمدة 10 دقائق بسبب السكام/التكرار السريع.", delete_after=5)
            return

    # 2. منع المنشن الجماعي بدون صلاحية
    if ("@everyone" in message.content or "@here" in message.content) and not message.author.guild_permissions.mention_everyone:
        await message.delete()
        await message.channel.send(f"⚠️ {message.author.mention} غير مسموح بالمنشن الجماعي!", delete_after=5)
        return

    # 3. فلترة الروابط والإعلانات
    if "discord.gg/" in content or "http://" in content or "https://" in content:
        if not message.author.guild_permissions.administrator:
            await message.delete()
            await message.channel.send(f"⚠️ {message.author.mention} ممنوع نشر الروابط الخارجية!", delete_after=5)
            return

    # 4. فلترة الكلمات المحظورة والشتائم
    if any(word in content for word in BAD_WORDS):
        if not message.author.guild_permissions.administrator:
            await message.delete()
            # تسجيل Warn تلقائي
            warn_data = await warns_col.find_one({"_id": user_id}) or {"count": 0}
            count = warn_data["count"] + 1
            await warns_col.update_one({"_id": user_id}, {"$set": {"count": count}}, upsert=True)
            await message.channel.send(f"⚠️ {message.author.mention} تم حذف الكلمة المحظورة وتسجيل تحذير تلقائي (إجمالي التحذيرات: {count}).", delete_after=5)
            return

    # 5. ردود الاقتراحات التلقائية
    sug_channel_id = guild_data.get("suggestion_channel")
    if sug_channel_id and message.channel.id == sug_channel_id:
        await message.delete()
        embed = discord.Embed(title="💡 اقتراح جديد", description=message.content, color=discord.Color.gold())
        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
        sug_msg = await message.channel.send(embed=embed)
        await sug_msg.add_reaction("👍")
        await sug_msg.add_reaction("👎")
        return

    # 6. رد منشن الأدمن أو الرتب العليا
    if message.mentions:
        for mentioned in message.mentions:
            if mentioned.guild_permissions.administrator:
                await message.channel.send("💬 فريق الدعم مشغول حالياً، يرجى فتح تذكرة من روم الدعم.", delete_after=7)
                break

    # 7. التحيات والردود التلقائية
    if content in ["السلام عليكم", "سلام عليكم", "مرحبا"]:
        await message.channel.send("وعليكم السلام ورحمة الله وبركاته! نورت السيرفر 🌹")
        return

    # 8. نظام اللفل والخبرة (Leveling)
    user_data = await users_col.find_one({"_id": user_id}) or {}
    xp = user_data.get("xp", 0) + 15
    level = user_data.get("level", 1)
    if xp >= level * 100:
        level += 1
        xp = 0
        await message.channel.send(f"🎉 مبروك {message.author.mention}! ارتفع مستواك إلى **المستوى {level}** 🚀")
    await users_col.update_one({"_id": user_id}, {"$set": {"xp": xp, "level": level}}, upsert=True)

    # 9. الأوامر المخصصة
    if message.content.startswith("!"):
        cmd_name = message.content[1:].strip().split()[0]
        custom_cmd = await commands_col.find_one({"name": cmd_name})
        if custom_cmd:
            await message.channel.send(custom_cmd["response"])
            return

    await bot.process_commands(message)

# ==================== أمر المساعدة الشامل (!help) ====================

@bot.command(name="help")
async def help_command(ctx):
    embed = discord.Embed(
        title="✨ قائمة أوامر بوت Cosmic Galaxy الشاملة",
        description="جميع أوامر البوت مقسمة حسب الفئات والصلاحيات:",
        color=discord.Color.purple()
    )

    embed.add_field(
        name="👤 أوامر الأعضاء والنظام المالي (Economy & XP)",
        value=(
            "`!daily` - استلام المكافأة اليومية من المجرات 🪙\n"
            "`!credits` / `!coins` - معرفة الرصيد الحالي 💳\n"
            "`!transfer <عضو> <المبلغ>` - تحويل مجرات لعضو آخر 💸\n"
            "`!rep <عضو>` - إعطاء نقطة سمعة كل 24 ساعة 🌟\n"
            "`!profile` / `!rank` - عرض بطاقتك الشخصية والمستوى 🚀\n"
            "`!leaderboard` / `!top` - قائمة أكثر الأعضاء تفاعلاً وثراءً 🏆"
        ),
        inline=False
    )

    embed.add_field(
        name="🛡️ أوامر الإدارة والرقابة (Moderation)",
        value=(
            "`!ban <عضو> [سبب]` / `!unban <ID>` - حظر أو فك حظر 🔨\n"
            "`!kick <عضو> [سبب]` - طرد عضو 👞\n"
            "`!mute` / `!timeout <عضو> <دقائق>` - إسكات عضو 🔇\n"
            "`!warn <عضو> [سبب]` - إعطاء تحذير ⚠️\n"
            "`!clear <عدد>` / `!purge` - مسح عدد من الرسائل 🧹\n"
            "`!lock` / `!unlock` - قفل أو فتح الكتابة في الروم 🔒\n"
            "`!addcmd <اسم> <رد>` / `!delcmd` - إدارة الأوامر المخصصة ➕"
        ),
        inline=False
    )

    embed.add_field(
        name="🎮 أوامر الألعاب والتسلية (Games & Fun)",
        value=(
            "`!xo <عضو>` - بدء لعبة إكس أوه مع صديق ❌⭕\n"
            "`!roll [اقصى رقم]` - سحب رقم عشوائي 🎲\n"
            "`!rps <حجر/ورقة/مقص>` - لعبة حجر ورقة مقص ✂️\n"
            "`!tweet <النص>` - إنشاء تغريدة وهمية احترافية 🐦\n"
            "`!math <مسألة>` - حل مسألة رياضية 🧮"
        ),
        inline=False
    )

    embed.add_field(
        name="🛠️ الأدوات والتذكيرات (Utility & Reminders)",
        value=(
            "`!userinfo <عضو>` - تفاصيل الحساب والانضمام ℹ️\n"
            "`!server` - معلومات السيرفر الكاملة 📊\n"
            "`!avatar <عضو>` - إظهار صورة البروفايل 🖼️\n"
            "`!poll <سؤال>` - إنشاء تصويت سريع 📊\n"
            "`!remind <وقت_بالدقائق> <السبب>` - ضبط تذكير ⏰\n"
            "`!giveaway <دقائق> <الجائزة>` - إنشاء مسابقة وسحب فائز 🎁\n"
            "`!embed <النص>` - إرسال رسالة منسقة أنيقة 📜"
        ),
        inline=False
    )

    embed.add_field(
        name="👑 أوامر المالك والإعدادات والحماية (Setup & Protection)",
        value=(
            "`!setwelcome <الروم>` - تحديد روم الترحيب 📑\n"
            "`!autorole <الرتبة>` - تحديد الرتبة التلقائية 🎖️\n"
            "`!ticket_setup` - إنشاء لوحة تذاكر الدعم الفني 🎫\n"
            "`!verify_setup` - إنشاء نظام التفعيل بزر كابتشا 🟢\n"
            "`!set-log <الروم>` - تحديد روم سجل الفعاليات (Audit Log) 📝\n"
            "`!anti-spam <on/off>` - تفعيل/تعطيل منع التكرار 🚫\n"
            "`!anti-bots <on/off>` - منع دخول البوتات غير الموثوقة 🤖"
        ),
        inline=False
    )

    embed.set_footer(text=f"تم الطلب بواسطة {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
    await ctx.send(embed=embed)

# ==================== أوامر الإدارة والرقابة ====================

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason=None):
    await member.ban(reason=reason)
    await ctx.send(f"🔨 تم حظر {member.mention} | السبب: {reason or 'غير محدد'}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int):
    user = await bot.fetch_user(user_id)
    await ctx.guild.unban(user)
    await ctx.send(f"✅ تم فك الحظر عن {user.name}")

@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason=None):
    await member.kick(reason=reason)
    await ctx.send(f"👞 تم طرد {member.mention} | السبب: {reason or 'غير محدد'}")

@bot.command(aliases=["mute"])
@commands.has_permissions(moderate_members=True)
async def timeout(ctx, member: discord.Member, minutes: int, *, reason=None):
    duration = datetime.timedelta(minutes=minutes)
    await member.timeout(duration, reason=reason)
    await ctx.send(f"🔇 تم إسكات {member.mention} لمدة {minutes} دقيقة.")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def warn(ctx, member: discord.Member, *, reason=None):
    warn_data = await warns_col.find_one({"_id": member.id}) or {"count": 0}
    count = warn_data["count"] + 1
    await warns_col.update_one({"_id": member.id}, {"$set": {"count": count}}, upsert=True)
    await ctx.send(f"⚠️ تم تحذير {member.mention}. إجمالي التحذيرات: **{count}** | السبب: {reason or 'لا يوجد'}")

@bot.command(aliases=["purge"])
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int = 10):
    await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🧹 تم مسح {amount} رسائل.", delete_after=3)

@bot.command()
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send("🔒 تم قفل الروم.")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
    await ctx.send("🔓 تم فتح الروم.")

@bot.command()
@commands.has_permissions(administrator=True)
async def addcmd(ctx, name: str, *, response: str):
    name = name.replace("!", "").strip()
    await commands_col.update_one({"name": name}, {"$set": {"response": response}}, upsert=True)
    await ctx.send(f"✅ تم إضافة/تعديل الأمر `!{name}` بنجاح!")

@bot.command()
@commands.has_permissions(administrator=True)
async def delcmd(ctx, name: str):
    name = name.replace("!", "").strip()
    res = await commands_col.delete_one({"name": name})
    if res.deleted_count > 0:
        await ctx.send(f"🗑️ تم حذف الأمر `!{name}`.")
    else:
        await ctx.send("❌ الأمر غير موجود.")

# ==================== النظام المالي والمستويات ====================

@bot.command()
async def daily(ctx):
    user_id = ctx.author.id
    now = datetime.datetime.utcnow().timestamp()
    user_data = await users_col.find_one({"_id": user_id}) or {}
    last_daily = user_data.get("last_daily", 0)

    if now - last_daily < 86400:
        rem = int(86400 - (now - last_daily))
        await ctx.send(f"⏳ تقدر تاخد المكافأة بعد **{rem // 3600} ساعة و {(rem % 3600) // 60} دقيقة**.")
        return

    coins = user_data.get("coins", 0) + 100
    await users_col.update_one({"_id": user_id}, {"$set": {"coins": coins, "last_daily": now}}, upsert=True)
    await ctx.send(f"🎉 أخدت 100 **{CURRENCY_NAME}**! رصيدك الحالي: **{coins}**.")

@bot.command(aliases=["coins", "balance"])
async def credits(ctx, member: discord.Member = None):
    member = member or ctx.author
    user_data = await users_col.find_one({"_id": member.id}) or {}
    coins = user_data.get("coins", 0)
    await ctx.send(f"💳 رصيد {member.mention} هو: **{coins}** {CURRENCY_NAME}.")

@bot.command()
async def transfer(ctx, member: discord.Member, amount: int):
    if amount <= 0 or member.id == ctx.author.id:
        await ctx.send("❌ المبلغ غير صالح.")
        return
    sender_data = await users_col.find_one({"_id": ctx.author.id}) or {}
    sender_coins = sender_data.get("coins", 0)

    if sender_coins < amount:
        await ctx.send(f"❌ معندكش رصيد كافي من الـ **{CURRENCY_NAME}**.")
        return

    receiver_data = await users_col.find_one({"_id": member.id}) or {}
    receiver_coins = receiver_data.get("coins", 0)

    await users_col.update_one({"_id": ctx.author.id}, {"$set": {"coins": sender_coins - amount}})
    await users_col.update_one({"_id": member.id}, {"$set": {"coins": receiver_coins + amount}}, upsert=True)
    await ctx.send(f"💸 تم تحويل **{amount}** {CURRENCY_NAME} إلى {member.mention} بنجاح!")

@bot.command()
async def rep(ctx, member: discord.Member):
    if member.id == ctx.author.id:
        await ctx.send("❌ ما ينفعش تدي سمعة لنفسك!")
        return
    now = datetime.datetime.utcnow().timestamp()
    sender_data = await users_col.find_one({"_id": ctx.author.id}) or {}
    last_rep = sender_data.get("last_rep", 0)

    if now - last_rep < 86400:
        await ctx.send("⏳ تقدر تدي نقطة سمعة مرة واحدة كل 24 ساعة.")
        return

    receiver_data = await users_col.find_one({"_id": member.id}) or {}
    rep_points = receiver_data.get("rep", 0) + 1

    await users_col.update_one({"_id": ctx.author.id}, {"$set": {"last_rep": now}}, upsert=True)
    await users_col.update_one({"_id": member.id}, {"$set": {"rep": rep_points}}, upsert=True)
    await ctx.send(f"🌟 أعطيت نقطة سمعة لـ {member.mention}! إجمالي سمعته: **+{rep_points}**")

@bot.command(aliases=["rank", "level"])
async def profile(ctx, member: discord.Member = None):
    member = member or ctx.author
    user_data = await users_col.find_one({"_id": member.id}) or {}
    coins = user_data.get("coins", 0)
    level = user_data.get("level", 1)
    xp = user_data.get("xp", 0)
    rep_points = user_data.get("rep", 0)

    embed = discord.Embed(title=f"👤 بطاقة {member.display_name}", color=discord.Color.blue())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name=f"💰 الـ {CURRENCY_NAME}", value=f"**{coins}**", inline=True)
    embed.add_field(name="🚀 المستوى", value=f"**{level}** (XP: {xp}/{level*100})", inline=True)
    embed.add_field(name="🌟 السمعة", value=f"**+{rep_points}**", inline=True)
    await ctx.send(embed=embed)

@bot.command(aliases=["top"])
async def leaderboard(ctx):
    top_users = await users_col.find().sort("coins", -1).limit(5).to_list(5)
    embed = discord.Embed(title=f"🏆 أثرى 5 أعضاء بالـ {CURRENCY_NAME}", color=discord.Color.gold())
    for idx, u in enumerate(top_users, start=1):
        try:
            user_obj = await bot.fetch_user(u["_id"])
            embed.add_field(name=f"#{idx} {user_obj.name}", value=f"{u.get('coins', 0)} {CURRENCY_NAME}", inline=False)
        except:
            continue
    await ctx.send(embed=embed)

# ==================== أوامر الألعاب والتسلية ====================

@bot.command()
async def roll(ctx, max_num: int = 100):
    res = random.randint(1, max_num)
    await ctx.send(f"🎲 الرقم العشوائي هو: **{res}**")

@bot.command()
async def rps(ctx, choice: str):
    options = ["حجر", "ورقة", "مقص"]
    bot_choice = random.choice(options)
    choice = choice.strip()

    if choice not in options:
        await ctx.send("❌ اختر إما: `حجر` أو `ورقة` أو `مقص`.")
        return

    if choice == bot_choice:
        res = "🤝 تعادل!"
    elif (choice == "حجر" and bot_choice == "مقص") or (choice == "ورقة" and bot_choice == "حجر") or (choice == "مقص" and bot_choice == "ورقة"):
        res = "🎉 أنت فزت!"
    else:
        res = "🤖 البوت فاز!"

    await ctx.send(f"اخترت: **{choice}** | البوت اختار: **{bot_choice}**\nResult: **{res}**")

@bot.command()
async def math(ctx, *, expression: str):
    try:
        allowed = "0123456789+-*/(). "
        if all(c in allowed for c in expression):
            res = eval(expression)
            await ctx.send(f"🧮 النتيجة: `{res}`")
        else:
            await ctx.send("❌ تعبير رياضي غير مسموح.")
    except:
        await ctx.send("❌ مسألة رياضية غير صالحة.")

@bot.command()
async def tweet(ctx, *, text: str):
    img = Image.new('RGB', (600, 200), color=(21, 32, 43))
    d = ImageDraw.Draw(img)
    d.text((30, 40), f"{ctx.author.name} @{ctx.author.name}", fill=(255, 255, 255))
    d.text((30, 90), text, fill=(255, 255, 255))
    
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    await ctx.send(file=discord.File(buf, 'tweet.png'))

# ==================== المعلومات والأدوات والتذكيرات ====================

@bot.command(aliases=["user"])
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=f"معلومات {member.name}", color=discord.Color.green())
    embed.set_thumbnail(ur
