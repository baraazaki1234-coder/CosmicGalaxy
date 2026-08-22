import discord
from discord.ext import commands
import datetime
import aiohttp
import random
import time
import os
import json

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ============================================================
#  نظام التخزين الدائم (JSON) - عشان البيانات ما تروح لو البوت
#  عمل ريستارت أو توقف
# ============================================================
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

LANGS_FILE = os.path.join(DATA_DIR, "langs.json")
GALAXIES_FILE = os.path.join(DATA_DIR, "galaxies.json")
DAILY_FILE = os.path.join(DATA_DIR, "daily.json")
WARNS_FILE = os.path.join(DATA_DIR, "warns.json")


def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return default
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# البيانات محملة كـ dict بمفاتيح str (json ما يدعم int keys) - نحولها وقت الاستخدام
server_langs = {int(k): v for k, v in load_json(LANGS_FILE, {}).items()}
user_galaxies = {int(k): v for k, v in load_json(GALAXIES_FILE, {}).items()}
user_last_daily = {int(k): v for k, v in load_json(DAILY_FILE, {}).items()}
user_warns = {int(k): v for k, v in load_json(WARNS_FILE, {}).items()}


def save_langs():
    save_json(LANGS_FILE, {str(k): v for k, v in server_langs.items()})


def save_galaxies():
    save_json(GALAXIES_FILE, {str(k): v for k, v in user_galaxies.items()})


def save_daily():
    save_json(DAILY_FILE, {str(k): v for k, v in user_last_daily.items()})


def save_warns():
    save_json(WARNS_FILE, {str(k): v for k, v in user_warns.items()})


def get_lang(guild):
    return server_langs.get(guild.id, "ar") if guild else "ar"


# ============================================================
#  أزرار التنقل لقائمة Help
# ============================================================
class HelpPaginator(discord.ui.View):
    def __init__(self, ctx, pages, lang="ar"):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.pages = pages
        self.current_page = 0
        self.lang = lang
        self.update_buttons()

    def update_buttons(self):
        self.prev_button.disabled = (self.current_page == 0)
        self.next_button.disabled = (self.current_page == len(self.pages) - 1)

    @discord.ui.button(label="◀️ السابق", style=discord.ButtonStyle.blurple, custom_id="prev_btn")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            msg = "عذراً، هذا الزر لا يخصك." if self.lang == "ar" else "Sorry, this button is not for you."
            return await interaction.response.send_message(msg, ephemeral=True)

        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(label="التالي ▶️", style=discord.ButtonStyle.blurple, custom_id="next_btn")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            msg = "عذراً، هذا الزر لا يخصك." if self.lang == "ar" else "Sorry, this button is not for you."
            return await interaction.response.send_message(msg, ephemeral=True)

        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)


@bot.event
async def on_ready():
    print(f'✅ Bot active: {bot.user.name}')


# ============================================================
#  1. أمر قائمة المساعدة (Help)
# ============================================================
@bot.command(aliases=["هيلب", "الأوامر"])
async def help(ctx):
    lang = get_lang(ctx.guild)

    if lang == "ar":
        p1 = discord.Embed(title="🌌 قائمة الأوامر - (1/4) أوامر الأعضاء", color=discord.Color.purple())
        p1.add_field(name="`!galaxies`", value="عرض رصيدك من المجرات.", inline=False)
        p1.add_field(name="`!daily`", value="استلام المكافأة اليومية (عشوائية بين 50 و 200).", inline=False)
        p1.add_field(name="`!transfer @user <عدد>`", value="تحويل مجرات لعضو آخر.", inline=False)
        p1.add_field(name="`!leaderboard`", value="عرض أغنى 10 أعضاء بالمجرات.", inline=False)
        p1.add_field(name="`!profile [@user]`", value="عرض البروفايل وصورة الشخص ومجراته.", inline=False)
        p1.add_field(name="`!avatar [@user]`", value="عرض صورة العضو بحجم كبير.", inline=False)
        p1.add_field(name="`!ping`", value="عرض سرعة استجابة البوت.", inline=False)
        p1.add_field(name="`!setlang <ar/en>`", value="تغيير لغة البوت داخل السيرفر.", inline=False)

        p2 = discord.Embed(title="🛡️ قائمة الأوامر - (2/4) أوامر الإدارة", color=discord.Color.dark_red())
        p2.add_field(name="`!clear <عدد>`", value="مسح عدد محدد من الرسائل.", inline=False)
        p2.add_field(name="`!kick @user [سبب]`", value="طرد عضو من السيرفر.", inline=False)
        p2.add_field(name="`!ban @user [سبب]`", value="حظر عضو من السيرفر.", inline=False)
        p2.add_field(name="`!unban <ID>`", value="فك الحظر عن عضو عن طريق الآيدي.", inline=False)
        p2.add_field(name="`!timeout @user <دقائق>`", value="إعطاء تايم أوت (ميوت مؤقت) لعضو.", inline=False)
        p2.add_field(name="`!untimeout @user`", value="إلغاء التايم أوت عن عضو.", inline=False)

        p3 = discord.Embed(title="⚠️ قائمة الأوامر - (3/4) أوامر التحذيرات والاقتصاد", color=discord.Color.orange())
        p3.add_field(name="`!warn @user [سبب]`", value="إعطاء تحذير لعضو.", inline=False)
        p3.add_field(name="`!warnings [@user]`", value="عرض تحذيرات عضو.", inline=False)
        p3.add_field(name="`!clearwarnings @user`", value="مسح كل تحذيرات عضو.", inline=False)
        p3.add_field(name="`!addgalaxies @user <عدد>`", value="إضافة مجرات لعضو معين.", inline=False)
        p3.add_field(name="`!removegalaxies @user <عدد>`", value="خصم مجرات من عضو معين.", inline=False)

        p4 = discord.Embed(title="👑 قائمة الأوامر - (4/4) أوامر المالك", color=discord.Color.gold())
        p4.add_field(name="`!setname <الاسم الجديد>`", value="تغيير اسم البوت.", inline=False)
        p4.add_field(name="`!setavatar <رابط/صورة>`", value="تغيير صورة البوت الشخصية.", inline=False)
        p4.add_field(name="`!setstatus <النص>`", value="تغيير الحالة (Activity) الخاصة بالبوت.", inline=False)
    else:
        p1 = discord.Embed(title="🌌 Help Menu - (1/4) Member Commands", color=discord.Color.purple())
        p1.add_field(name="`!galaxies`", value="Check your Galaxies balance.", inline=False)
        p1.add_field(name="`!daily`", value="Claim daily reward (Random 50 to 200).", inline=False)
        p1.add_field(name="`!transfer @user <amount>`", value="Transfer Galaxies to another member.", inline=False)
        p1.add_field(name="`!leaderboard`", value="Show top 10 richest members.", inline=False)
        p1.add_field(name="`!profile [@user]`", value="View member profile & Galaxies.", inline=False)
        p1.add_field(name="`!avatar [@user]`", value="Show member's avatar in full size.", inline=False)
        p1.add_field(name="`!ping`", value="Check bot latency.", inline=False)
        p1.add_field(name="`!setlang <ar/en>`", value="Change server language.", inline=False)

        p2 = discord.Embed(title="🛡️ Help Menu - (2/4) Admin Commands", color=discord.Color.dark_red())
        p2.add_field(name="`!clear <amount>`", value="Clear chat messages.", inline=False)
        p2.add_field(name="`!kick @user [reason]`", value="Kick a member.", inline=False)
        p2.add_field(name="`!ban @user [reason]`", value="Ban a member.", inline=False)
        p2.add_field(name="`!unban <ID>`", value="Unban a member by ID.", inline=False)
        p2.add_field(name="`!timeout @user <minutes>`", value="Mute member temporarily.", inline=False)
        p2.add_field(name="`!untimeout @user`", value="Remove a member's timeout.", inline=False)

        p3 = discord.Embed(title="⚠️ Help Menu - (3/4) Warnings & Economy", color=discord.Color.orange())
        p3.add_field(name="`!warn @user [reason]`", value="Warn a member.", inline=False)
        p3.add_field(name="`!warnings [@user]`", value="Show a member's warnings.", inline=False)
        p3.add_field(name="`!clearwarnings @user`", value="Clear all warnings for a member.", inline=False)
        p3.add_field(name="`!addgalaxies @user <amount>`", value="Add Galaxies to a user.", inline=False)
        p3.add_field(name="`!removegalaxies @user <amount>`", value="Remove Galaxies from a user.", inline=False)

        p4 = discord.Embed(title="👑 Help Menu - (4/4) Owner Commands", color=discord.Color.gold())
        p4.add_field(name="`!setname <name>`", value="Change bot username.", inline=False)
        p4.add_field(name="`!setavatar <url/file>`", value="Change bot avatar.", inline=False)
        p4.add_field(name="`!setstatus <text>`", value="Change bot activity status.", inline=False)

    pages = [p1, p2, p3, p4]
    view = HelpPaginator(ctx, pages, lang)
    await ctx.send(embed=pages[0], view=view)


# ============================================================
#  2. أوامر الأعضاء (Members)
# ============================================================
@bot.command(aliases=["galaxies", "galaxy", "مجرات", "مجرة"])
async def check_galaxies(ctx, member: discord.Member = None):
    target = member or ctx.author
    amount = user_galaxies.get(target.id, 0)
    lang = get_lang(ctx.guild)

    if lang == "ar":
        await ctx.send(f"🌌 رصيد **{target.mention}** هو: **{amount}** مجرة.")
    else:
        await ctx.send(f"🌌 **{target.mention}**'s balance is: **{amount}** Galaxies.")


@bot.command(aliases=["دايلي", "يومي"])
async def daily(ctx):
    user_id = ctx.author.id
    now = time.time()
    last_claim = user_last_daily.get(user_id, 0)
    cooldown = 86400  # 24 ساعة بالثواني
    lang = get_lang(ctx.guild)

    if now - last_claim < cooldown:
        remaining = int(cooldown - (now - last_claim))
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        seconds = remaining % 60

        if lang == "ar":
            await ctx.send(f"⏳ أخذت مكافأتك اليومية بالفعل! يرجى الانتظار **{hours} ساعة و {minutes} دقيقة و {seconds} ثانية**.")
        else:
            await ctx.send(f"⏳ You already claimed your daily reward! Wait **{hours}h {minutes}m {seconds}s**.")
        return

    reward = random.randint(50, 200)
    user_galaxies[user_id] = user_galaxies.get(user_id, 0) + reward
    user_last_daily[user_id] = now
    save_galaxies()
    save_daily()

    if lang == "ar":
        await ctx.send(f"🎉 حصلت على **{reward}** مجرة هدية اليوم! رصيدك الحالي: **{user_galaxies[user_id]}** مجرة 🌌")
    else:
        await ctx.send(f"🎉 You claimed **{reward}** random Galaxies today! Current balance: **{user_galaxies[user_id]}** Galaxies 🌌")


@bot.command(aliases=["تحويل", "pay"])
async def transfer(ctx, member: discord.Member = None, amount: int = None):
    lang = get_lang(ctx.guild)
    if member is None or amount is None:
        msg = "❌ الاستخدام الصحيح: `!transfer @user <عدد>`" if lang == "ar" else "❌ Usage: `!transfer @user <amount>`"
        return await ctx.send(msg)

    if member.id == ctx.author.id:
        msg = "❌ لا يمكنك تحويل مجرات لنفسك." if lang == "ar" else "❌ You can't transfer Galaxies to yourself."
        return await ctx.send(msg)

    if member.bot:
        msg = "❌ لا يمكنك تحويل مجرات لبوت." if lang == "ar" else "❌ You can't transfer Galaxies to a bot."
        return await ctx.send(msg)

    if amount <= 0:
        msg = "❌ المبلغ يجب أن يكون أكبر من 0." if lang == "ar" else "❌ The amount must be greater than 0."
        return await ctx.send(msg)

    sender_bal = user_galaxies.get(ctx.author.id, 0)
    if sender_bal < amount:
        msg = "❌ لا تملك مجرات كافية للتحويل!" if lang == "ar" else "❌ You don't have enough Galaxies!"
        return await ctx.send(msg)

    user_galaxies[ctx.author.id] -= amount
    user_galaxies[member.id] = user_galaxies.get(member.id, 0) + amount
    save_galaxies()

    if lang == "ar":
        await ctx.send(f"🌌 تم تحويل **{amount}** مجرة بنجاح إلى {member.mention}!")
    else:
        await ctx.send(f"🌌 Successfully transferred **{amount}** Galaxies to {member.mention}!")


@bot.command(aliases=["المتصدرين", "لوحة", "lb"])
async def leaderboard(ctx):
    lang = get_lang(ctx.guild)
    if not user_galaxies:
        msg = "لا يوجد أي رصيد مسجل بعد." if lang == "ar" else "No Galaxies recorded yet."
        return await ctx.send(msg)

    top = sorted(user_galaxies.items(), key=lambda x: x[1], reverse=True)[:10]
    title = "🏆 أغنى 10 أعضاء بالمجرات" if lang == "ar" else "🏆 Top 10 Richest Members"
    embed = discord.Embed(title=title, color=discord.Color.purple())

    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, (uid, amount) in enumerate(top):
        member = ctx.guild.get_member(uid) if ctx.guild else None
        name = member.display_name if member else f"User {uid}"
        prefix = medals[i] if i < 3 else f"`{i + 1}.`"
        lines.append(f"{prefix} **{name}** — {amount} 🌌")

    embed.description = "\n".join(lines)
    await ctx.send(embed=embed)


@bot.command(aliases=["بروفايل", "p"])
async def profile(ctx, member: discord.Member = None):
    target = member or ctx.author
    amount = user_galaxies.get(target.id, 0)
    lang = get_lang(ctx.guild)
    warns_count = len(user_warns.get(target.id, []))

    title = f"👤 بروفايل {target.display_name}" if lang == "ar" else f"👤 {target.display_name}'s Profile"
    embed = discord.Embed(title=title, color=discord.Color.purple())
    embed.set_thumbnail(url=target.display_avatar.url)

    if lang == "ar":
        embed.add_field(name="🌌 المجرات (Galaxies):", value=f"`{amount}`", inline=True)
        embed.add_field(name="⚠️ التحذيرات:", value=f"`{warns_count}`", inline=True)
        embed.add_field(name="📅 تاريخ إنشاء الحساب:", value=f"<t:{int(target.created_at.timestamp())}:R>", inline=False)
        if getattr(target, "joined_at", None):
            embed.add_field(name="📥 انضمامه للسيرفر:", value=f"<t:{int(target.joined_at.timestamp())}:R>", inline=False)
    else:
        embed.add_field(name="🌌 Galaxies:", value=f"`{amount}`", inline=True)
        embed.add_field(name="⚠️ Warnings:", value=f"`{warns_count}`", inline=True)
        embed.add_field(name="📅 Account Created:", value=f"<t:{int(target.created_at.timestamp())}:R>", inline=False)
        if getattr(target, "joined_at", None):
            embed.add_field(name="📥 Joined Server:", value=f"<t:{int(target.joined_at.timestamp())}:R>", inline=False)

    embed.set_footer(text=f"User ID: {target.id}")
    await ctx.send(embed=embed)


@bot.command(aliases=["افاتار", "صورة"])
async def avatar(ctx, member: discord.Member = None):
    target = member or ctx.author
    lang = get_lang(ctx.guild)
    title = f"🖼️ صورة {target.display_name}" if lang == "ar" else f"🖼️ {target.display_name}'s Avatar"
    embed = discord.Embed(title=title, color=discord.Color.purple())
    embed.set_image(url=target.display_avatar.url)
    await ctx.send(embed=embed)


@bot.command()
async def ping(ctx):
    ms = round(bot.latency * 1000)
    await ctx.send(f"🏓 Latency: **{ms}ms**")


@bot.command()
@commands.has_permissions(administrator=True)
async def setlang(ctx, lang: str = None):
    if not lang or lang.lower() not in ["ar", "en"]:
        return await ctx.send("❌ Usage: `!setlang ar` or `!setlang en`")

    server_langs[ctx.guild.id] = lang.lower()
    save_langs()
    await ctx.send(f"✅ Language updated to **{lang.upper()}**")


# ============================================================
#  3. أوامر الإدارة (Admin)
# ============================================================
@bot.command()
@commands.has_permissions(administrator=True)
async def addgalaxies(ctx, member: discord.Member = None, amount: int = None):
    lang = get_lang(ctx.guild)
    if member is None or amount is None or amount <= 0:
        msg = "❌ الاستخدام الصحيح: `!addgalaxies @user <عدد>`" if lang == "ar" else "❌ Usage: `!addgalaxies @user <amount>`"
        return await ctx.send(msg)

    user_galaxies[member.id] = user_galaxies.get(member.id, 0) + amount
    save_galaxies()
    await ctx.send(f"✅ تم إضافة **{amount}** مجرة إلى {member.mention}.")


@bot.command(aliases=["takegalaxies"])
@commands.has_permissions(administrator=True)
async def removegalaxies(ctx, member: discord.Member = None, amount: int = None):
    lang = get_lang(ctx.guild)
    if member is None or amount is None or amount <= 0:
        msg = "❌ الاستخدام الصحيح: `!removegalaxies @user <عدد>`" if lang == "ar" else "❌ Usage: `!removegalaxies @user <amount>`"
        return await ctx.send(msg)

    current = user_galaxies.get(member.id, 0)
    user_galaxies[member.id] = max(0, current - amount)
    save_galaxies()
    await ctx.send(f"✅ تم خصم **{amount}** مجرة من {member.mention}. الرصيد الحالي: **{user_galaxies[member.id]}**.")


@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int = 5):
    lang = get_lang(ctx.guild)
    if amount < 1 or amount > 100:
        msg = "❌ الرجاء اختيار عدد بين 1 و 100." if lang == "ar" else "❌ Please choose a number between 1 and 100."
        return await ctx.send(msg, delete_after=5)

    deleted = await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🧹 تم مسح **{len(deleted) - 1}** رسالة.", delete_after=3)


@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member = None, *, reason=None):
    lang = get_lang(ctx.guild)
    if member is None:
        msg = "❌ الاستخدام الصحيح: `!kick @user [سبب]`" if lang == "ar" else "❌ Usage: `!kick @user [reason]`"
        return await ctx.send(msg)
    try:
        await member.kick(reason=reason)
        await ctx.send(f"👢 تم طرد {member.mention}.")
    except discord.Forbidden:
        msg = "❌ لا أملك صلاحية كافية لطرد هذا العضو." if lang == "ar" else "❌ I don't have permission to kick this member."
        await ctx.send(msg)


@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member = None, *, reason=None):
    lang = get_lang(ctx.guild)
    if member is None:
        msg = "❌ الاستخدام الصحيح: `!ban @user [سبب]`" if lang == "ar" else "❌ Usage: `!ban @user [reason]`"
        return await ctx.send(msg)
    try:
        await member.ban(reason=reason)
        await ctx.send(f"🔨 تم حظر {member.mention}.")
    except discord.Forbidden:
        msg = "❌ لا أملك صلاحية كافية لحظر هذا العضو." if lang == "ar" else "❌ I don't have permission to ban this member."
        await ctx.send(msg)


@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int = None):
    lang = get_lang(ctx.guild)
    if user_id is None:
        msg = "❌ الاستخدام الصحيح: `!unban <ID>`" if lang == "ar" else "❌ Usage: `!unban <user_id>`"
        return await ctx.send(msg)
    try:
        user = await bot.fetch_user(user_id)
        await ctx.guild.unban(user)
        await ctx.send(f"✅ تم فك الحظر عن **{user}**.")
    except discord.NotFound:
        msg = "❌ هذا العضو غير محظور أو الآيدي غير صحيح." if lang == "ar" else "❌ This user is not banned or the ID is invalid."
        await ctx.send(msg)


@bot.command()
@commands.has_permissions(moderate_members=True)
async def timeout(ctx, member: discord.Member = None, minutes: int = None):
    lang = get_lang(ctx.guild)
    if member is None or minutes is None or minutes <= 0:
        msg = "❌ الاستخدام الصحيح: `!timeout @user <دقائق>`" if lang == "ar" else "❌ Usage: `!timeout @user <
