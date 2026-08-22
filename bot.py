import os
import datetime
import asyncio
import discord
from discord.ext import commands
import motor.motor_asyncio

# إعداد الصلاحيات
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

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

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} | All systems ready!")
    await bot.change_presence(activity=discord.Game(name="Cosmic Galaxy | !help"))

# --- الترحيب والرتب التلقائية ---
@bot.event
async def on_member_join(member):
    guild_data = await guilds_col.find_one({"_id": member.guild.id})
    if not guild_data:
        return

    # الرتبة التلقائية
    auto_role_id = guild_data.get("autorole")
    if auto_role_id:
        role = member.guild.get_role(auto_role_id)
        if role:
            await member.add_roles(role)

    # قنواة الترحيب
    welcome_channel_id = guild_data.get("welcome_channel")
    if welcome_channel_id:
        channel = member.guild.get_channel(welcome_channel_id)
        if channel:
            embed = discord.Embed(
                title="✨ عضو جديد انضم للمجرة!",
                description=f"أهلاً بك {member.mention} في **{member.guild.name}**!\nنتمنى لك وقتاً ممتعاً 🚀",
                color=discord.Color.purple()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            await channel.send(embed=embed)

# --- الفلترة والردود والتفاعل ---
@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    content = message.content.lower()

    # 1. فلترة الروابط الإعلانية
    if "discord.gg/" in content or "http://" in content or "https://" in content:
        if not message.author.guild_permissions.administrator:
            await message.delete()
            await message.channel.send(f"⚠️ {message.author.mention} ممنوع نشر الروابط الخارجية!", delete_after=5)
            return

    # 2. فلترة الكلمات المحظورة
    if any(word in content for word in BAD_WORDS):
        await message.delete()
        await message.channel.send(f"⚠️ {message.author.mention} تم حذف رسالتك لاحتوائها على كلمات غير لطبقة.", delete_after=5)
        return

    # 3. الردود التلقائية
    if content in ["السلام عليكم", "سلام عليكم"]:
        await message.channel.send("وعليكم السلام ورحمة الله وبركاته! نورت السيرفر 🌹")
        return

    # 4. نظام اللفل والخبرة (XP)
    user_id = message.author.id
    user_data = await users_col.find_one({"_id": user_id}) or {}
    xp = user_data.get("xp", 0) + 15
    level = user_data.get("level", 1)
    
    if xp >= level * 100:
        level += 1
        xp = 0
        await message.channel.send(f"🎉 مبروك {message.author.mention}! ارتفع مستواك إلى **المستوى {level}** 🚀")

    await users_col.update_one({"_id": user_id}, {"$set": {"xp": xp, "level": level}}, upsert=True)

    # الأوامر المخصصة
    if message.content.startswith("!"):
        cmd_name = message.content[1:].strip().split()[0]
        custom_cmd = await commands_col.find_one({"name": cmd_name})
        if custom_cmd:
            await message.channel.send(custom_cmd["response"])
            return

    await bot.process_commands(message)

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

@bot.command()
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

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int = 10):
    await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🧹 تم مسح {amount} رسائل.", delete_after=3)

@bot.command()
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send("🔒 تم قفل القناة.")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
    await ctx.send("🔓 تم فتح القناة.")

# ==================== النظام المالي والمستويات ====================

@bot.command()
async def daily(ctx):
    user_id = ctx.author.id
    now = datetime.datetime.utcnow().timestamp()
    user_data = await users_col.find_one({"_id": user_id}) or {}
    
    last_daily = user_data.get("last_daily", 0)
    if now - last_daily < 86400:
        rem = int(86400 - (now - last_daily))
        await ctx.send(f"⏳ تعالي بعد **{rem // 3600} ساعة و {(rem % 3600) // 60} دقيقة**.")
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
        await ctx.send("❌ م ينفعش تدي سمعة لنفسك!")
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
        user_obj = await bot.fetch_user(u["_id"])
        embed.add_field(name=f"#{idx} {user_obj.name}", value=f"{u.get('coins', 0)} {CURRENCY_NAME}", inline=False)
    await ctx.send(embed=embed)

# ==================== المعلومات والأدوات ====================

@bot.command()
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=f"معلومات {member.name}", color=discord.Color.green())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="الـ ID", value=member.id, inline=True)
    embed.add_field(name="تاريخ إنشاء الحساب", value=member.created_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name="تاريخ الانضمام", value=member.joined_at.strftime("%Y-%m-%d"), inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def server(ctx):
    guild = ctx.guild
    embed = discord.Embed(title=f"معلومات {guild.name}", color=discord.Color.orange())
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="عدد الأعضاء", value=guild.member_count, inline=True)
    embed.add_field(name="عدد الرومات", value=len(guild.channels), inline=True)
    embed.add_field(name="عدد الرتب", value=len(guild.roles), inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    await ctx.send(member.display_avatar.url)

@bot.command()
async def poll(ctx, *, question: str):
    embed = discord.Embed(title="📊 تصويت جديد", description=question, color=discord.Color.blue())
    msg = await ctx.send(embed=embed)
    await msg.add_reaction("👍")
    await msg.add_reaction("👎")

# ==================== التذاكر والإعدادات ====================

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📩 فتح تذكرة دعم", style=discord.ButtonStyle.primary, custom_id="create_ticket")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        channel = await guild.create_text_channel(name=f"ticket-{interaction.user.name}", overwrites=overwrites)
        await channel.send(f"أهلاً بك {interaction.user.mention}، يرجى كتابة مشكلتك وسيرد عليك فريق الدعم.")
        await interaction.response.send_message(f"✅ تم إنشاء تذكرتك: {channel.mention}", ephemeral=True)

@bot.command()
@commands.has_permissions(administrator=True)
async def ticket_setup(ctx):
    embed = discord.Embed(title="🎫 الدعم الفني", description="اضغط على الزر لفتح تذكرة وسيتم مساعدتك فوراً.", color=discord.Color.green())
    await ctx.send(embed=embed, view=TicketView())

@bot.command()
@commands.has_permissions(administrator=True)
async def setwelcome(ctx, channel: discord.TextChannel):
    await guilds_col.update_one({"_id": ctx.guild.id}, {"$set": {"welcome_channel": channel.id}}, upsert=True)
    await ctx.send(f"✅ تم تحديد قناة الترحيب: {channel.mention}")

@bot.command()
@commands.has_permissions(administrator=True)
async def autorole(ctx, role: discord.Role):
    await guilds_col.update_one({"_id": ctx.guild.id}, {"$set": {"autorole": role.id}}, upsert=True)
    await ctx.send(f"✅ تم تحديد الرتبة التلقائية: **{role.name}**")

# تشغيل البوت
token = os.getenv("DISCORD_TOKEN")
if token:
    bot.run(token)
else:
    print("Error: DISCORD_TOKEN missing!")
            
