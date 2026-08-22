import discord
from discord.ext import commands
import datetime
import aiohttp
import random
import time
import os
import json
import asyncio

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ============================================================
#  نظام التخزين الدائم (JSON)
# ============================================================
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

LANGS_FILE = os.path.join(DATA_DIR, "langs.json")
GALAXIES_FILE = os.path.join(DATA_DIR, "galaxies.json")
DAILY_FILE = os.path.join(DATA_DIR, "daily.json")
WARNS_FILE = os.path.join(DATA_DIR, "warns.json")
TICKETS_FILE = os.path.join(DATA_DIR, "tickets.json")
WELCOME_FILE = os.path.join(DATA_DIR, "welcome.json")
LEAVE_FILE = os.path.join(DATA_DIR, "leave.json")
AUTOROLE_FILE = os.path.join(DATA_DIR, "autorole.json")


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


server_langs = {int(k): v for k, v in load_json(LANGS_FILE, {}).items()}
user_galaxies = {int(k): v for k, v in load_json(GALAXIES_FILE, {}).items()}
user_last_daily = {int(k): v for k, v in load_json(DAILY_FILE, {}).items()}
user_warns = {int(k): v for k, v in load_json(WARNS_FILE, {}).items()}
ticket_config = {int(k): v for k, v in load_json(TICKETS_FILE, {}).items()}
welcome_config = {int(k): v for k, v in load_json(WELCOME_FILE, {}).items()}
leave_config = {int(k): v for k, v in load_json(LEAVE_FILE, {}).items()}
autorole_config = {int(k): v for k, v in load_json(AUTOROLE_FILE, {}).items()}


def save_langs():
    save_json(LANGS_FILE, {str(k): v for k, v in server_langs.items()})


def save_galaxies():
    save_json(GALAXIES_FILE, {str(k): v for k, v in user_galaxies.items()})


def save_daily():
    save_json(DAILY_FILE, {str(k): v for k, v in user_last_daily.items()})


def save_warns():
    save_json(WARNS_FILE, {str(k): v for k, v in user_warns.items()})


def save_tickets():
    save_json(TICKETS_FILE, {str(k): v for k, v in ticket_config.items()})


def save_welcome():
    save_json(WELCOME_FILE, {str(k): v for k, v in welcome_config.items()})


def save_leave():
    save_json(LEAVE_FILE, {str(k): v for k, v in leave_config.items()})


def save_autorole():
    save_json(AUTOROLE_FILE, {str(k): v for k, v in autorole_config.items()})


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


# ============================================================
#  نظام التذاكر - أزرار دائمة (تشتغل حتى بعد إعادة تشغيل البوت)
# ============================================================
class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 فتح تذكرة", style=discord.ButtonStyle.green, custom_id="ticket_open_button")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        lang = get_lang(guild)
        config = ticket_config.get(guild.id)

        if not config:
            msg = "❌ نظام التذاكر غير مفعل بهذا السيرفر." if lang == "ar" else "❌ Ticket system is not set up here."
            return await interaction.response.send_message(msg, ephemeral=True)

        existing = discord.utils.get(guild.text_channels, topic=f"ticket-owner-{interaction.user.id}")
        if existing:
            msg = f"❌ لديك تذكرة مفتوحة بالفعل: {existing.mention}" if lang == "ar" else f"❌ You already have an open ticket: {existing.mention}"
            return await interaction.response.send_message(msg, ephemeral=True)

        category = guild.get_channel(config.get("category_id"))
        staff_role = guild.get_role(config["staff_role_id"]) if config.get("staff_role_id") else None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        safe_name = "".join(c for c in interaction.user.name.lower() if c.isalnum()) or "user"
        channel = await guild.create_text_channel(
            name=f"ticket-{safe_name}"[:90],
            category=category,
            overwrites=overwrites,
            topic=f"ticket-owner-{interaction.user.id}",
        )

        if lang == "ar":
            embed = discord.Embed(
                title="🎫 تذكرة دعم جديدة",
                description=f"مرحباً {interaction.user.mention}! اشرح مشكلتك وفريق الدعم راح يوصل قريباً.\nلإغلاق التذكرة اضغط الزر تحت.",
                color=discord.Color.green(),
            )
        else:
            embed = discord.Embed(
                title="🎫 New Support Ticket",
                description=f"Welcome {interaction.user.mention}! Describe your issue and staff will be with you shortly.\nPress the button below to close this ticket.",
                color=discord.Color.green(),
            )

        await channel.send(embed=embed, view=TicketCloseView())
        msg = f"✅ تم إنشاء تذكرتك: {channel.mention}" if lang == "ar" else f"✅ Your ticket was created: {channel.mention}"
        await interaction.response.send_message(msg, ephemeral=True)


class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 إغلاق التذكرة", style=discord.ButtonStyle.red, custom_id="ticket_close_button")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        lang = get_lang(interaction.guild)
        msg = "🔒 سيتم إغلاق التذكرة خلال 5 ثواني..." if lang == "ar" else "🔒 This ticket will close in 5 seconds..."
        await interaction.response.send_message(msg)
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except discord.Forbidden:
            pass


@bot.event
async def on_ready():
    bot.add_view(TicketPanelView())
    bot.add_view(TicketCloseView())
    print(f'✅ Bot active: {bot.user.name}')


# ============================================================
#  نظام الترحيب والوداع + الرتبة التلقائية
# ============================================================
@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    config = welcome_config.get(guild.id)
    if config:
        channel = guild.get_channel(config["channel_id"])
        if channel:
            text = config["message"].format(
                user=member.mention, server=guild.name, count=guild.member_count
            )
            embed = discord.Embed(description=text, color=discord.Color.green())
            embed.set_thumbnail(url=member.display_avatar.url)
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                pass

    role_id = autorole_config.get(guild.id)
    if role_id:
        role = guild.get_role(role_id)
        if role:
            try:
                await member.add_roles(role)
            except discord.Forbidden:
                pass


@bot.event
async def on_member_remove(member: discord.Member):
    guild = member.guild
    config = leave_config.get(guild.id)
    if config:
        channel = guild.get_channel(config["channel_id"])
        if channel:
            text = config["message"].format(user=member.name, server=guild.name, count=guild.member_count)
            embed = discord.Embed(description=text, color=discord.Color.red())
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                pass


# ============================================================
#  1. أمر قائمة المساعدة (Help) - مقسمة لـ 3 أقسام واضحة
# ============================================================
@bot.command(aliases=["هيلب", "الأوامر"])
async def help(ctx):
    lang = get_lang(ctx.guild)

    if lang == "ar":
        p1 = discord.Embed(title="🌌 أوامر الأعضاء - (1/5) الاقتصاد والبروفايل", color=discord.Color.purple())
        p1.add_field(name="`!galaxies`", value="عرض رصيدك من المجرات.", inline=False)
        p1.add_field(name="`!daily`", value="استلام المكافأة اليومية (عشوائية بين 50 و 200).", inline=False)
        p1.add_field(name="`!transfer @user <عدد>`", value="تحويل مجرات لعضو آخر.", inline=False)
        p1.add_field(name="`!leaderboard`", value="عرض أغنى 10 أعضاء بالمجرات.", inline=False)
        p1.add_field(name="`!profile [@user]`", value="عرض البروفايل والمجرات والتحذيرات.", inline=False)
        p1.add_field(name="`!avatar [@user]`", value="عرض صورة العضو بحجم كبير.", inline=False)
        p1.add_field(name="`!ping`", value="عرض سرعة استجابة البوت.", inline=False)

        p2 = discord.Embed(title="🎉 أوامر الأعضاء - (2/5) الترفيه والتذاكر", color=discord.Color.teal())
        p2.add_field(name="`!8ball <سؤال>`", value="اسأل الكرة السحرية.", inline=False)
        p2.add_field(name="`!roll [عدد]`", value="رمي نرد (افتراضي 6 أوجه).", inline=False)
        p2.add_field(name="`!coinflip`", value="رمي عملة.", inline=False)
        p2.add_field(name="`!rps <حجر/ورقة/مقص>`", value="العب حجر ورقة مقص ضد البوت.", inline=False)
        p2.add_field(name="`!joke`", value="نكتة عشوائية.", inline=False)
        p2.add_field(name="`!ship @user1 [@user2]`", value="نسبة التوافق بين عضوين.", inline=False)
        p2.add_field(name="`!poll <سؤال>`", value="عمل تصويت سريع بالريأكشن.", inline=False)
        p2.add_field(name="🎫 فتح تذكرة", value="اضغط الزر الأخضر في قناة التذاكر (إذا مفعّلة).", inline=False)

        p3 = discord.Embed(title="🛡️ أوامر الإدارة - (3/5) الإشراف والتحذيرات", color=discord.Color.dark_red())
        p3.add_field(name="`!clear <عدد>`", value="مسح عدد محدد من الرسائل.", inline=False)
        p3.add_field(name="`!kick @user [سبب]`", value="طرد عضو من السيرفر.", inline=False)
        p3.add_field(name="`!ban @user [سبب]`", value="حظر عضو من السيرفر.", inline=False)
        p3.add_field(name="`!unban <ID>`", value="فك الحظر عن عضو عن طريق الآيدي.", inline=False)
        p3.add_field(name="`!timeout @user <دقائق>`", value="تايم أوت (ميوت مؤقت) لعضو.", inline=False)
        p3.add_field(name="`!untimeout @user`", value="إلغاء التايم أوت عن عضو.", inline=False)
        p3.add_field(name="`!warn @user [سبب]`", value="إعطاء تحذير لعضو.", inline=False)
        p3.add_field(name="`!warnings [@user]`", value="عرض تحذيرات عضو.", inline=False)
        p3.add_field(name="`!clearwarnings @user`", value="مسح كل تحذيرات عضو.", inline=False)
        p3.add_field(name="`!nickname @user <اسم>`", value="تغيير اسم عضو داخل السيرفر.", inline=False)
        p3.add_field(name="`!lock` / `!unlock`", value="قفل/فتح القناة الحالية للأعضاء.", inline=False)
        p3.add_field(name="`!slowmode <ثواني>`", value="ضبط وضع الإبطاء بالقناة.", inline=False)
        p3.add_field(name="`!addgalaxies @user <عدد>`", value="إضافة مجرات لعضو.", inline=False)
        p3.add_field(name="`!removegalaxies @user <عدد>`", value="خصم مجرات من عضو.", inline=False)

        p4 = discord.Embed(title="⚙️ أوامر الإدارة - (4/5) إعداد السيرفر", color=discord.Color.orange())
        p4.add_field(name="`!setlang <ar/en>`", value="تغيير لغة البوت داخل السيرفر.", inline=False)
        p4.add_field(name="`!setwelcome #قناة <رسالة>`", value="تفعيل رسالة الترحيب. استخدم `{user} {server} {count}`.\n`!setwelcome` بدون قناة = إيقاف.", inline=False)
        p4.add_field(name="`!setleave #قناة <رسالة>`", value="تفعيل رسالة الوداع.\n`!setleave` بدون قناة = إيقاف.", inline=False)
        p4.add_field(name="`!setautorole @رتبة`", value="رتبة تلقائية لكل عضو جديد.", inline=False)
        p4.add_field(name="`!ticketsetup #قناة [@رتبة_الدعم]`", value="إعداد نظام التذاكر ونشر لوحة الفتح.", inline=False)

        p5 = discord.Embed(title="👑 أوامر المالك - (5/5) خاصة بمالك البوت", color=discord.Color.gold())
        p5.add_field(name="`!setname <الاسم الجديد>`", value="تغيير اسم البوت.", inline=False)
        p5.add_field(name="`!setavatar <رابط/صورة>`", value="تغيير صورة البوت الشخصية.", inline=False)
        p5.add_field(name="`!setstatus <النص>`", value="تغيير الحالة (Activity) الخاصة بالبوت.", inline=False)
    else:
        p1 = discord.Embed(title="🌌 Member Commands - (1/5) Economy & Profile", color=discord.Color.purple())
        p1.add_field(name="`!galaxies`", value="Check your Galaxies balance.", inline=False)
        p1.add_field(name="`!daily`", value="Claim daily reward (50-200 random).", inline=False)
        p1.add_field(name="`!transfer @user <amount>`", value="Transfer Galaxies to another member.", inline=False)
        p1.add_field(name="`!leaderboard`", value="Top 10 richest members.", inline=False)
        p1.add_field(name="`!profile [@user]`", value="View profile, Galaxies & warnings.", inline=False)
        p1.add_field(name="`!avatar [@user]`", value="Show a member's full-size avatar.", inline=False)
        p1.add_field(name="`!ping`", value="Check bot latency.", inline=False)

        p2 = discord.Embed(title="🎉 Member Commands - (2/5) Fun & Tickets", color=discord.Color.teal())
        p2.add_field(name="`!8ball <question>`", value="Ask the magic 8-ball.", inline=False)
        p2.add_field(name="`!roll [sides]`", value="Roll a die (default 6 sides).", inline=False)
        p2.add_field(name="`!coinflip`", value="Flip a coin.", inline=False)
        p2.add_field(name="`!rps <rock/paper/scissors>`", value="Play rock-paper-scissors vs the bot.", inline=False)
        p2.add_field(name="`!joke`", value="Random joke.", inline=False)
        p2.add_field(name="`!ship @user1 [@user2]`", value="Compatibility percentage between two members.", inline=False)
        p2.add_field(name="`!poll <question>`", value="Quick reaction poll.", inline=False)
        p2.add_field(name="🎫 Open a ticket", value="Click the green button in the tickets channel (if enabled).", inline=False)

        p3 = discord.Embed(title="🛡️ Admin Commands - (3/5) Moderation & Warnings", color=discord.Color.dark_red())
        p3.add_field(name="`!clear <amount>`", value="Clear messages.", inline=False)
        p3.add_field(name="`!kick @user [reason]`", value="Kick a member.", inline=False)
        p3.add_field(name="`!ban @user [reason]`", value="Ban a member.", inline=False)
        p3.add_field(name="`!unban <ID>`", value="Unban a member by ID.", inline=False)
        p3.add_field(name="`!timeout @user <minutes>`", value="Timeout a member.", inline=False)
        p3.add_field(name="`!untimeout @user`", value="Remove a timeout.", inline=False)
        p3.add_field(name="`!warn @user [reason]`", value="Warn a member.", inline=False)
        p3.add_field(name="`!warnings [@user]`", value="Show a member's warnings.", inline=False)
        p3.add_field(name="`!clearwarnings @user`", value="Clear all warnings for a member.", inline=False)
        p3.add_field(name="`!nickname @user <name>`", value="Change a member's nickname.", inline=False)
        p3.add_field(name="`!lock` / `!unlock`", value="Lock/unlock the current channel.", inline=False)
        p3.add_field(name="`!slowmode <seconds>`", value="Set channel slowmode.", inline=False)
        p3.add_field(name="`!addgalaxies @user <amount>`", value="Add Galaxies to a user.", inline=False)
        p3.add_field(name="`!removegalaxies @user <amount>`", value="Remove Galaxies from a user.", inline=False)

        p4 = discord.Embed(title="⚙️ Admin Commands - (4/5) Server Setup", color=discord.Color.orange())
        p4.add_field(name="`!setlang <ar/en>`", value="Change server language.", inline=False)
        p4.add_field(name="`!setwelcome #channel <message>`", value="Enable welcome messages. Use `{user} {server} {count}`.\n`!setwelcome` with no channel = disable.", inline=False)
        p4.add_field(name="`!setleave #channel <message>`", value="Enable leave messages.\n`!setleave` with no channel = disable.", inline=False)
        p4.add_field(name="`!setautorole @role`", value="Auto-role for new members.", inline=False)
        p4.add_field(name="`!ticketsetup #channel [@staff_role]`", value="Set up the ticket system and post the panel.", inline=False)

        p5 = discord.Embed(title="👑 Owner Commands - (5/5) Bot owner only", color=discord.Color.gold())
        p5.add_field(name="`!setname <name>`", value="Change bot username.", inline=False)
        p5.add_field(name="`!setavatar <url/file>`", value="Change bot avatar.", inline=False)
        p5.add_field(name="`!setstatus <text>`", value="Change bot activity status.", inline=False)

    pages = [p1, p2, p3, p4, p5]
    view = HelpPaginator(ctx, pages, lang)
    await ctx.send(embed=pages[0], view=view)


# ============================================================
#  2. أوامر الاقتصاد والبروفايل
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
    cooldown = 86400
    lang = get_lang(ctx.guild)

    if now - last_claim < cooldown:
        remaining = int(cooldown - (now - last_claim))
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        seconds = remaining % 60
        if
