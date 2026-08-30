import discord
from discord.ext import commands, tasks
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

# بريفكس ديناميكي - "!" افتراضياً، أو بريفكس مخصص لو السيرفر عنده Server Premium فعّال
# (premium_servers بتتملى فعلياً من نظام البريميوم تحت، هنا مجرد إعلان مبدئي)
premium_servers = {}
premium_users = {}


def get_dynamic_prefix(bot_instance, message):
    if message.guild and message.guild.id in premium_servers:
        data = premium_servers[message.guild.id]
        if data.get("expires", 0) > time.time() and data.get("prefix"):
            return commands.when_mentioned_or(data["prefix"])(bot_instance, message)
    return commands.when_mentioned_or("!")(bot_instance, message)


bot = commands.Bot(command_prefix=get_dynamic_prefix, intents=intents, help_command=None, owner_id=1387471174602326077, max_messages=100)
_data_loaded = False
_slash_synced = False

# آيدي سيرفر الدعم الرسمي - الأوامر الحساسة (حالة البوت/الصيانة) تشتغل هنا بس
# عشان محدش يقدر يستخدمها في أي سيرفر تاني حتى لو هو نفسه المالك.
# ⚠️ لازم تحط آيدي سيرفرك هنا (Server Settings > Widget > Server ID، أو
# فعّل Developer Mode وكبس ضغط طويل على أيقونة السيرفر > Copy Server ID)
HOME_GUILD_ID = 1541152235084455958  # سيرفر الدعم الرسمي


def home_guild_only():
    async def predicate(ctx):
        if HOME_GUILD_ID is None:
            return True  # لسه ما اتحددش، ما نمنعش حاجة عشان ما نقفلش الأمر بالغلط
        if ctx.guild is None or ctx.guild.id != HOME_GUILD_ID:
            lang = get_lang(ctx.guild) if ctx.guild else "ar"
            msg = "❌ الأمر ده يشتغل بس في سيرفر الدعم الرسمي." if lang == "ar" else "❌ This command only works in the official support server."
            await ctx.send(msg)
            return False
        return True
    return commands.check(predicate)

# ============================================================
#  نظام التخزين الدائم (JSON)
# ============================================================
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# ============================================================
#  نظام التخزين الدائم - MongoDB أساسي، وJSON محلي كـ fallback
#  تلقائي لو متغير MONGO_URI مش موجود (عشان البوت ما يتوقفش)
# ============================================================
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

MONGO_URI = os.getenv("MONGO_URI")
USE_MONGO = bool(MONGO_URI)
mongo_client = None
mongo_db = None

if USE_MONGO:
    try:
        import certifi
        from motor.motor_asyncio import AsyncIOMotorClient
        mongo_client = AsyncIOMotorClient(MONGO_URI, tlsCAFile=certifi.where())
        mongo_db = mongo_client["cosmic_galaxy"]
    except Exception as e:
        print(f"⚠️ MongoDB connection failed, falling back to local JSON files: {e}")
        USE_MONGO = False


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


async def storage_load(key, default):
    if USE_MONGO:
        try:
            doc = await mongo_db["kv_store"].find_one({"_id": key})
            return doc["data"] if doc else default
        except Exception as e:
            print(f"⚠️ MongoDB load failed for '{key}', using local fallback: {e}")
    return load_json(os.path.join(DATA_DIR, f"{key}.json"), default)


async def storage_save(key, data):
    if USE_MONGO:
        try:
            await mongo_db["kv_store"].update_one({"_id": key}, {"$set": {"data": data}}, upsert=True)
            return
        except Exception as e:
            print(f"⚠️ MongoDB save failed for '{key}', writing local fallback instead: {e}")
    save_json(os.path.join(DATA_DIR, f"{key}.json"), data)


# القواميس الفعلية تتملى لاحقاً في load_all_data() لما البوت يشتغل
# (مينفعش تحميل غير متزامن (async) وقت استيراد الملف)
server_langs = {}
user_galaxies = {}
user_last_daily = {}
user_warns = {}
ticket_config = {}
welcome_config = {}
leave_config = {}
autorole_config = {}
user_stardust = {}
blacklist_data = {}
known_users = {}


def save_langs():
    return storage_save("langs", {str(k): v for k, v in server_langs.items()})


def save_galaxies():
    return storage_save("galaxies", {str(k): v for k, v in user_galaxies.items()})


def save_daily():
    return storage_save("daily", {str(k): v for k, v in user_last_daily.items()})


def save_warns():
    return storage_save("warns", {str(k): v for k, v in user_warns.items()})


def save_tickets():
    return storage_save("tickets", {str(k): v for k, v in ticket_config.items()})


def save_welcome():
    return storage_save("welcome", {str(k): v for k, v in welcome_config.items()})


def save_leave():
    return storage_save("leave", {str(k): v for k, v in leave_config.items()})


def save_autorole():
    return storage_save("autorole", {str(k): v for k, v in autorole_config.items()})


def save_stardust():
    return storage_save("stardust", {str(gk): {str(uk): v for uk, v in uv.items()} for gk, uv in user_stardust.items()})


def save_blacklist():
    return storage_save("blacklist", {str(k): v for k, v in blacklist_data.items()})


def save_known_users():
    return storage_save("known_users", {str(k): v for k, v in known_users.items()})


class Blacklisted(commands.CheckFailure):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(f"Blacklisted: {reason}")


@bot.check
async def global_checks(ctx):
    known_users[ctx.author.id] = {"name": str(ctx.author), "last_seen": time.time()}
    await save_known_users()

    if ctx.author.id in blacklist_data and not await bot.is_owner(ctx.author):
        raise Blacklisted(blacklist_data[ctx.author.id])
    return True


def get_lang(guild):
    return server_langs.get(guild.id, "en") if guild else "en"


# ============================================================
#  أزرار التنقل لقائمة Help
# ============================================================
class HelpJumpSelect(discord.ui.Select):
    def __init__(self, section_labels, lang="ar"):
        placeholder = "📂 انتقل لقسم مباشرة..." if lang == "ar" else "📂 Jump to a section..."
        options = [discord.SelectOption(label=label, value=str(i)) for i, label in enumerate(section_labels)]
        super().__init__(placeholder=placeholder, options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        view: HelpPaginator = self.view
        if interaction.user.id != view.ctx.author.id:
            msg = "عذراً، هذا الزر لا يخصك." if view.lang == "ar" else "Sorry, this isn't for you."
            return await interaction.response.send_message(msg, ephemeral=True)
        view.current_page = int(self.values[0])
        view.update_buttons()
        await interaction.response.edit_message(embed=view.pages[view.current_page], view=view)


class HelpPaginator(discord.ui.View):
    def __init__(self, ctx, pages, lang="ar", section_labels=None):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.pages = pages
        self.current_page = 0
        self.lang = lang
        if section_labels:
            self.add_item(HelpJumpSelect(section_labels, lang))
        self.update_buttons()

    def update_buttons(self):
        self.prev_button.disabled = (self.current_page == 0)
        self.next_button.disabled = (self.current_page == len(self.pages) - 1)

    @discord.ui.button(label="◀️ السابق", style=discord.ButtonStyle.blurple, custom_id="prev_btn", row=1)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            msg = "عذراً، هذا الزر لا يخصك." if self.lang == "ar" else "Sorry, this button is not for you."
            return await interaction.response.send_message(msg, ephemeral=True)
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(label="التالي ▶️", style=discord.ButtonStyle.blurple, custom_id="next_btn", row=1)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            msg = "عذراً، هذا الزر لا يخصك." if self.lang == "ar" else "Sorry, this button is not for you."
            return await interaction.response.send_message(msg, ephemeral=True)
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)


# ============================================================
#  نظام التذاكر المتقدم - قائمة أسباب، نافذة تفاصيل، ترقيم تسلسلي،
#  أزرار (إضافة عضو / استدعاء الإدارة / إغلاق / حذف نهائي)
#  كلها دائمة (تشتغل حتى بعد إعادة تشغيل البوت)
# ============================================================
TICKET_COUNTER_FILE = os.path.join(DATA_DIR, "ticket_counter.json")
ACTIVE_TICKETS_FILE = os.path.join(DATA_DIR, "active_tickets.json")

ticket_counters = {}
active_tickets = {}
ticket_call_cooldowns = {}  # في الذاكرة بس، مؤقت وما يحتاج حفظ دائم


def save_ticket_counters():
    return storage_save("ticket_counter", {str(k): v for k, v in ticket_counters.items()})


def save_active_tickets():
    return storage_save("active_tickets", {str(k): v for k, v in active_tickets.items()})


TICKET_CATEGORY_LABELS = {
    "support": ("🛠️ دعم فني", "🛠️ Technical Support"),
    "report": ("🚨 إبلاغ عن مشكلة", "🚨 Report an Issue"),
    "prize": ("🎁 استلام جائزة فعالية", "🎁 Claim an Event Prize"),
    "donate": ("💝 تبرع لدعم البوت", "💝 Donate to Support the Bot"),
    "premium_personal": ("💎 اشتراك بريميوم شخصي", "💎 Personal Premium Subscription"),
    "premium_server": ("🏛️ اشتراك بريميوم للسيرفر", "🏛️ Server Premium Subscription"),
    "other": ("❓ أخرى", "❓ Other"),
}

# الفئات دي حصرية على سيرفر الدعم الرسمي بس - أي سيرفر تاني يشوف الأساسيات فقط
HOME_GUILD_ONLY_CATEGORIES = {"donate", "premium_personal", "premium_server"}


def _get_staff_role_ids(config: dict) -> list:
    ids = list(config.get("staff_role_ids", []))
    legacy = config.get("staff_role_id")
    if legacy and legacy not in ids:
        ids.append(legacy)
    return ids


def _is_ticket_staff(interaction: discord.Interaction) -> bool:
    if interaction.user.guild_permissions.administrator:
        return True
    config = ticket_config.get(interaction.guild.id, {})
    staff_ids = _get_staff_role_ids(config)
    if any(r.id in staff_ids for r in interaction.user.roles):
        return True
    return False


async def create_ticket_channel(interaction: discord.Interaction, category_value: str, reason: str, lang: str):
    guild = interaction.guild
    config = ticket_config.get(guild.id)
    category_channel = guild.get_channel(config.get("category_id")) if config else None
    staff_role_ids = _get_staff_role_ids(config) if config else []
    staff_roles = [guild.get_role(rid) for rid in staff_role_ids]
    staff_roles = [r for r in staff_roles if r]

    counter = ticket_counters.get(guild.id, 0) + 1
    ticket_counters[guild.id] = counter
    await save_ticket_counters()

    safe_name = "".join(c for c in interaction.user.name.lower() if c.isalnum()) or "user"
    channel_name = f"ticket-{safe_name}-{counter:02d}"[:90]

    # نحدد صلاحية كل رتبة بالسيرفر صراحةً (مش بس @everyone) عشان نضمن
    # مفيش أي رتبة تانية بتشوف التذكرة عن طريق صلاحية موروثة من الفئة (Category).
    # المسموح لهم: اللي فتح التذكرة، أي رتبة دعم محددة، وأي رتبة "أعلى" منهم
    # في ترتيب السيرفر (زي رتبة المالك/الأدمن الأساسية).
    highest_staff_position = max((r.position for r in staff_roles), default=-1)
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
    }

    for role in guild.roles:
        if role.is_default():
            continue  # already handled via guild.default_role above
        is_staff_role = role.id in staff_role_ids
        is_above_staff = highest_staff_position >= 0 and role.position > highest_staff_position
        if is_staff_role or is_above_staff:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        else:
            overwrites[role] = discord.PermissionOverwrite(view_channel=False)

    channel = await guild.create_text_channel(name=channel_name, category=category_channel, overwrites=overwrites)

    active_tickets[channel.id] = {
        "guild_id": guild.id,
        "opener_id": interaction.user.id,
        "category": category_value,
        "number": counter,
        "closed": False,
    }
    await save_active_tickets()

    label_ar, label_en = TICKET_CATEGORY_LABELS.get(category_value, ("❓ أخرى", "❓ Other"))
    category_label = label_ar if lang == "ar" else label_en

    if lang == "ar":
        embed = discord.Embed(
            title=f"🎫 تذكرة #{counter:02d}",
            description=(
                f"مرحباً {interaction.user.mention}!\n\n"
                f"**السبب:** {category_label}\n**التفاصيل:** {reason}\n\n"
                "فريق الدعم هيوصل قريباً، من فضلك استنى 🙏"
            ),
            color=discord.Color.green(),
        )
    else:
        embed = discord.Embed(
            title=f"🎫 Ticket #{counter:02d}",
            description=(
                f"Welcome {interaction.user.mention}!\n\n"
                f"**Reason:** {category_label}\n**Details:** {reason}\n\n"
                "Our staff will be with you shortly, please wait 🙏"
            ),
            color=discord.Color.green(),
        )
    embed.set_footer(text=f"Opened by {interaction.user}")

    ping = " ".join(r.mention for r in staff_roles) if staff_roles else None
    await channel.send(content=ping, embed=embed, view=TicketControlView())

    confirm = f"✅ تم إنشاء تذكرتك: {channel.mention}" if lang == "ar" else f"✅ Your ticket was created: {channel.mention}"
    await interaction.response.send_message(confirm, ephemeral=True)


class TicketReasonModal(discord.ui.Modal):
    def __init__(self, category_value: str, lang: str):
        title = "فتح تذكرة" if lang == "ar" else "Open a Ticket"
        super().__init__(title=title)
        self.category_value = category_value
        self.lang = lang

        if category_value == "donate":
            label = "قد إيه حابب تتبرع؟ وأي طريقة تفضلها؟" if lang == "ar" else "How much would you like to donate, and which method?"
        else:
            label = "اشرح مشكلتك بالتفصيل" if lang == "ar" else "Describe your issue in detail"

        self.reason_input = discord.ui.TextInput(label=label, style=discord.TextStyle.paragraph, max_length=500, required=True)
        self.add_item(self.reason_input)

    async def on_submit(self, interaction: discord.Interaction):
        await create_ticket_channel(interaction, self.category_value, self.reason_input.value, self.lang)


class TicketCategorySelect(discord.ui.Select):
    def __init__(self, is_home_guild: bool = False):
        options = [
            discord.SelectOption(label="🛠️ دعم فني / Technical Support", value="support"),
            discord.SelectOption(label="🚨 إبلاغ / Report an Issue", value="report"),
            discord.SelectOption(label="🎁 استلام جائزة / Claim Prize", value="prize"),
        ]
        if is_home_guild:
            options.append(discord.SelectOption(label="💝 تبرع للبوت / Donate", value="donate"))
            options.append(discord.SelectOption(label="💎 اشتراك بريميوم شخصي / Personal Premium", value="premium_personal"))
            options.append(discord.SelectOption(label="🏛️ اشتراك بريميوم للسيرفر / Server Premium", value="premium_server"))
        options.append(discord.SelectOption(label="❓ أخرى / Other", value="other"))
        super().__init__(placeholder="اختر سبب فتح التذكرة / Choose a reason...", options=options, custom_id="ticket_category_select")

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        lang = get_lang(guild)
        config = ticket_config.get(guild.id)
        if not config:
            msg = "❌ نظام التذاكر غير مفعل بهذا السيرفر." if lang == "ar" else "❌ Ticket system is not set up here."
            return await interaction.response.send_message(msg, ephemeral=True)

        for channel_id, data in active_tickets.items():
            if data["guild_id"] == guild.id and data["opener_id"] == interaction.user.id and not data.get("closed", False):
                existing = guild.get_channel(channel_id)
                msg = "❌ لديك تذكرة مفتوحة بالفعل." if lang == "ar" else "❌ You already have an open ticket."
                if existing:
                    msg = f"❌ لديك تذكرة مفتوحة بالفعل: {existing.mention}" if lang == "ar" else f"❌ You already have an open ticket: {existing.mention}"
                return await interaction.response.send_message(msg, ephemeral=True)

        if self.values[0] in HOME_GUILD_ONLY_CATEGORIES and guild.id != HOME_GUILD_ID:
            msg = "❌ الفئة دي متاحة بس في سيرفر الدعم الرسمي." if lang == "ar" else "❌ This category is only available on the official support server."
            return await interaction.response.send_message(msg, ephemeral=True)

        modal = TicketReasonModal(self.values[0], lang)
        await interaction.response.send_modal(modal)


class TicketPanelView(discord.ui.View):
    def __init__(self, is_home_guild: bool = False):
        super().__init__(timeout=None)
        self.add_item(TicketCategorySelect(is_home_guild))


class AddMemberSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="اختر عضو تضيفه / Select a member to add...")
    async def select_member(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        lang = get_lang(interaction.guild)
        member = select.values[0]
        try:
            await interaction.channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
            msg = f"✅ تم إضافة {member.mention} للتذكرة." if lang == "ar" else f"✅ Added {member.mention} to the ticket."
            await interaction.response.edit_message(content=msg, view=None)
        except discord.Forbidden:
            msg = "❌ مش قادر أضيف العضو." if lang == "ar" else "❌ Couldn't add that member."
            await interaction.response.edit_message(content=msg, view=None)


class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="➕ Add Member", style=discord.ButtonStyle.blurple, custom_id="ticket_add_member")
    async def add_member(self, interaction: discord.Interaction, button: discord.ui.Button):
        lang = get_lang(interaction.guild)
        data = active_tickets.get(interaction.channel.id)
        if not data:
            return await interaction.response.send_message("❌", ephemeral=True)
        if interaction.user.id != data["opener_id"] and not _is_ticket_staff(interaction):
            msg = "❌ الزر ده مو ليك." if lang == "ar" else "❌ This isn't for you."
            return await interaction.response.send_message(msg, ephemeral=True)
        msg = "اختر العضو اللي عايز تضيفه:" if lang == "ar" else "Pick the member to add:"
        await interaction.response.send_message(msg, view=AddMemberSelectView(), ephemeral=True)

    @discord.ui.button(label="📣 Call Staff", style=discord.ButtonStyle.gray, custom_id="ticket_call_staff")
    async def call_staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        lang = get_lang(interaction.guild)
        data = active_tickets.get(interaction.channel.id)
        if not data:
            return await interaction.response.send_message("❌", ephemeral=True)

        now = time.time()
        last_call = ticket_call_cooldowns.get(interaction.channel.id, 0)
        if now - last_call < 60:
            msg = "⏳ استنى شوية قبل ما تنادي تاني." if lang == "ar" else "⏳ Please wait a bit before calling again."
            return await interaction.response.send_message(msg, ephemeral=True)
        ticket_call_cooldowns[interaction.channel.id] = now

        config = ticket_config.get(interaction.guild.id, {})
        staff_ids = _get_staff_role_ids(config)
        staff_roles_here = [interaction.guild.get_role(rid) for rid in staff_ids]
        staff_roles_here = [r for r in staff_roles_here if r]
        mention = " ".join(r.mention for r in staff_roles_here) if staff_roles_here else "@here"
        msg = f"📣 {mention} — {interaction.user.mention} محتاج مساعدة!" if lang == "ar" else f"📣 {mention} — {interaction.user.mention} needs help!"
        await interaction.response.send_message(msg)

    @discord.ui.button(label="🔒 Close", style=discord.ButtonStyle.red, custom_id="ticket_close_button")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        lang = get_lang(interaction.guild)
        data = active_tickets.get(interaction.channel.id)
        if not data:
            return await interaction.response.send_message("❌", ephemeral=True)
        if interaction.user.id != data["opener_id"] and not _is_ticket_staff(interaction):
            msg = "❌ الزر ده مو ليك." if lang == "ar" else "❌ This isn't for you."
            return await interaction.response.send_message(msg, ephemeral=True)

        opener = interaction.guild.get_member(data["opener_id"])
        if opener:
            try:
                await interaction.channel.set_permissions(opener, overwrite=None)
            except discord.Forbidden:
                pass

        data["closed"] = True
        await save_active_tickets()

        try:
            if not interaction.channel.name.startswith("closed-"):
                await interaction.channel.edit(name=f"closed-{interaction.channel.name}"[:90])
        except discord.Forbidden:
            pass

        msg = "🔒 تم إغلاق التذكرة. صاحبها يقدر يفتح تذكرة جديدة لو احتاج، والإدارة لسه تشوفها." if lang == "ar" else "🔒 Ticket closed. The opener can start a new one if needed — staff can still see this."
        await interaction.response.send_message(msg)

    @discord.ui.button(label="🗑️ Delete", style=discord.ButtonStyle.gray, custom_id="ticket_delete_button")
    async def delete_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        lang = get_lang(interaction.guild)
        if not _is_ticket_staff(interaction):
            msg = "❌ الحذف النهائي للإدارة بس." if lang == "ar" else "❌ Only staff can permanently delete a ticket."
            return await interaction.response.send_message(msg, ephemeral=True)

        msg = "🗑️ سيتم حذف التذكرة نهائياً خلال 5 ثواني..." if lang == "ar" else "🗑️ Permanently deleting this ticket in 5 seconds..."
        await interaction.response.send_message(msg)
        if interaction.channel.id in active_tickets:
            del active_tickets[interaction.channel.id]
            await save_active_tickets()
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except discord.Forbidden:
            pass


@bot.event
async def on_ready():
    global _data_loaded, _slash_synced
    if not _data_loaded:
        await load_all_data()
        _data_loaded = True

    if not _slash_synced:
        try:
            if HOME_GUILD_ID:
                home_guild_obj = discord.Object(id=HOME_GUILD_ID)
                bot.tree.copy_global_to(guild=home_guild_obj)
                await bot.tree.sync(guild=home_guild_obj)
            await bot.tree.sync()
            _slash_synced = True
            print("✅ Slash commands synced.")
        except Exception as e:
            print(f"⚠️ Slash command sync failed: {e}")

    bot.add_view(TicketPanelView())
    bot.add_view(TicketControlView())
    for message_id, data in active_giveaways.items():
        if not data.get("ended"):
            bot.add_view(GiveawayJoinView(message_id), message_id=message_id)
    if not check_giveaways.is_running():
        check_giveaways.start()
    if not check_premium_expiry.is_running():
        check_premium_expiry.start()

    for guild in bot.guilds:
        state = "maintenance" if maintenance_state.get(guild.id, {}).get("on") else "online"
        await update_status_channel(guild, state)

    print(f'✅ Bot active: {bot.user.name}')


@bot.event
async def on_guild_join(guild: discord.Guild):
    channel = guild.system_channel
    if channel is None or not channel.permissions_for(guild.me).send_messages:
        channel = None
        for ch in guild.text_channels:
            if ch.permissions_for(guild.me).send_messages:
                channel = ch
                break
    if channel is None:
        return

    embed = discord.Embed(
        title="🌌 Welcome to Cosmic Galaxy!",
        description=(
            f"**{guild.name}** is now part of the cosmic galaxy! 🚀✨\n\n"
            "This bot gives your members a full economy (Galaxies & Stardust), fun games, "
            "a support ticket system, automatic welcome/leave messages, giveaways, and "
            "complete moderation — everything in one place.\n\n"
            "🔹 Type `!help` to see every command\n"
            "🔹 **This bot defaults to English.** Type `!setlang ar` to switch to Arabic\n"
            "🔹 Try `!daily` and start collecting your first Galaxies!\n\n"
            "Enjoy the ride, astronauts 🌠"
        ),
        color=discord.Color.purple(),
    )
    if bot.user.display_avatar:
        embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.set_footer(text="Type !help to get started 🌌")

    try:
        await channel.send(embed=embed)
    except discord.Forbidden:
        pass


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
@bot.hybrid_command(name="help", aliases=["هيلب", "الأوامر"], description="عرض كل أوامر البوت / Show all bot commands")
async def help(ctx):
    lang = get_lang(ctx.guild)

    if lang == "ar":
        p1 = discord.Embed(title="🌌 أوامر الأعضاء - (1/9) الاقتصاد", color=discord.Color.purple())
        p1.add_field(name="`!galaxies`", value="عرض رصيدك من المجرات.", inline=False)
        p1.add_field(name="`!daily`", value="استلام المكافأة اليومية (عشوائية بين 50 و 200، تتضاعف لمشتركي Premium 💎).", inline=False)
        p1.add_field(name="`!transfer @user <عدد>`", value="تحويل مجرات لعضو آخر.", inline=False)
        p1.add_field(name="`!leaderboard`", value="عرض أغنى 10 أعضاء بالمجرات (عالمي).", inline=False)
        p1.add_field(name="`!stardust [@user]`", value="عرض رصيدك من الغبار النجمي 💫 (عملة هذا السيرفر فقط).", inline=False)
        p1.add_field(name="`!serverleaderboard`", value="أغنى 10 أعضاء بالغبار النجمي بهذا السيرفر.", inline=False)

        p1b = discord.Embed(title="👤 أوامر الأعضاء - (2/9) البروفايل والأدوات", color=discord.Color.purple())
        p1b.add_field(name="`!profile [@user]`", value="عرض البروفايل والمجرات والغبار النجمي والتحذيرات.", inline=False)
        p1b.add_field(name="`!avatar [@user]`", value="عرض صورة العضو بحجم كبير.", inline=False)
        p1b.add_field(name="`!ping`", value="عرض سرعة استجابة البوت.", inline=False)
        p1b.add_field(name="`!uptime`", value="من إمتى البوت شغال بدون توقف.", inline=False)
        p1b.add_field(name="`!note save <نص>`", value="احفظ ملاحظة شخصية (عالمية، متاحة من أي سيرفر).", inline=False)
        p1b.add_field(name="`!note list`", value="عرض كل ملاحظاتك المحفوظة (تتبعت لك في الخاص).", inline=False)
        p1b.add_field(name="`!note delete <رقم>`", value="مسح ملاحظة معينة.", inline=False)

        p6 = discord.Embed(title="💎 أوامر الأعضاء - (3/9) البريميوم", color=discord.Color.gold())
        p6.add_field(name="`!premium`", value="شرح كامل لمميزات البريميوم الشخصي والسيرفر (بيتبعت في الخاص).", inline=False)
        p6.add_field(name="`!premiumcheck [@user]`", value="تفحص حالة اشتراك عضو، وزرار اشتراك لو مش مشترك.", inline=False)
        p6.add_field(name="`!premiumsettings color <#hex>`", value="غيّر لون رسايلك الشخصية (لمشتركي Premium بس).", inline=False)
        p6.add_field(name="`!premiumsettings title <نص>`", value="حط لقب مخصص جنب اسمك (لمشتركي Premium بس).", inline=False)
        p6.add_field(name="`!premiumgift @user`", value="أهدي أسبوع تجريبي من Premium لصديق (مرة واحدة، لمشتركي Premium الأساسيين بس).", inline=False)
        p6.add_field(name="`!setprefix <رمز>`", value="غيّر بريفكس السيرفر (لسيرفرات Server Premium بس).", inline=False)

        p2 = discord.Embed(title="🎉 أوامر الأعضاء - (4/9) الترفيه والتذاكر", color=discord.Color.teal())
        p2.add_field(name="`!8ball <سؤال>`", value="اسأل الكرة السحرية.", inline=False)
        p2.add_field(name="`!roll [عدد]`", value="رمي نرد (افتراضي 6 أوجه).", inline=False)
        p2.add_field(name="`!coinflip`", value="رمي عملة.", inline=False)
        p2.add_field(name="`!rps <حجر/ورقة/مقص>`", value="العب حجر ورقة مقص ضد البوت.", inline=False)
        p2.add_field(name="`!joke`", value="نكتة عشوائية.", inline=False)
        p2.add_field(name="`!ship @user1 [@user2]`", value="نسبة التوافق بين عضوين.", inline=False)
        p2.add_field(name="`!poll <سؤال>`", value="عمل تصويت سريع بالريأكشن.", inline=False)
        p2.add_field(name="`!afk [سبب]`", value="تفعيل وضع الغياب — البوت يرد بدلك لو حد نادى عليك.", inline=False)
        p2.add_field(name="🎫 فتح تذكرة", value="اضغط الزر الأخضر في قناة التذاكر (إذا مفعّلة).", inline=False)

        p3 = discord.Embed(title="🛡️ أوامر الإدارة - (5/9) الإشراف الأساسي", color=discord.Color.dark_red())
        p3.add_field(name="`!clear <عدد>`", value="مسح عدد محدد من الرسائل.", inline=False)
        p3.add_field(name="`!kick @user [سبب]`", value="طرد عضو من السيرفر.", inline=False)
        p3.add_field(name="`!ban @user [سبب]`", value="حظر عضو من السيرفر.", inline=False)
        p3.add_field(name="`!unban <ID>`", value="فك الحظر عن عضو عن طريق الآيدي.", inline=False)
        p3.add_field(name="`!timeout @user <دقائق>`", value="تايم أوت (ميوت مؤقت) لعضو.", inline=False)
        p3.add_field(name="`!untimeout @user`", value="إلغاء التايم أوت عن عضو.", inline=False)
        p3.add_field(name="`!lock` / `!unlock`", value="قفل/فتح القناة الحالية للأعضاء.", inline=False)
        p3.add_field(name="`!slowmode <ثواني>`", value="ضبط وضع الإبطاء بالقناة.", inline=False)

        p3c = discord.Embed(title="⚠️ أوامر الإدارة - (6/9) التحذيرات والاقتصاد", color=discord.Color.dark_red())
        p3c.add_field(name="`!warn @user [سبب]`", value="إعطاء تحذير لعضو.", inline=False)
        p3c.add_field(name="`!warnings [@user]`", value="عرض تحذيرات عضو.", inline=False)
        p3c.add_field(name="`!clearwarnings @user`", value="مسح كل تحذيرات عضو.", inline=False)
        p3c.add_field(name="`!nickname @user <اسم>`", value="تغيير اسم عضو داخل السيرفر.", inline=False)
        p3c.add_field(name="`!addstardust @user <عدد>`", value="إضافة غبار نجمي 💫 لعضو (عملة سيرفرك فقط، مو عالمية).", inline=False)
        p3c.add_field(name="`!removestardust @user <عدد>`", value="خصم غبار نجمي من عضو.", inline=False)

        p3b = discord.Embed(title="🎭 أوامر الإدارة - (7/9) الرتب والرومات", color=discord.Color.dark_red())
        p3b.add_field(name="`!createrole <اسم> [#لون]`", value="إنشاء رتبة جديدة.", inline=False)
        p3b.add_field(name="`!deleterole @رتبة`", value="حذف رتبة.", inline=False)
        p3b.add_field(name="`!addrole @user @رتبة`", value="إعطاء رتبة لعضو.", inline=False)
        p3b.add_field(name="`!removerole @user @رتبة`", value="سحب رتبة من عضو.", inline=False)
        p3b.add_field(name="`!createchannel <اسم> [text/voice]`", value="إنشاء روم جديد.", inline=False)
        p3b.add_field(name="`!deletechannel #روم`", value="حذف روم.", inline=False)
        p3b.add_field(name="`!renamechannel #روم <اسم>`", value="تغيير اسم روم.", inline=False)
        p3b.add_field(name="`!purgeuser @user [عدد]`", value="مسح رسائل عضو معين بس من الروم الحالي.", inline=False)
        p3b.add_field(name="`!announce #روم <رسالة>`", value="بعث رسالة رسمية من البوت بروم معين.", inline=False)
        p3b.add_field(name="`!serverinfo`", value="عرض معلومات كاملة عن السيرفر.", inline=False)

        p4 = discord.Embed(title="⚙️ أوامر الإدارة - (8/9) إعداد السيرفر", color=discord.Color.orange())
        p4.add_field(name="`!setlang <ar/en>`", value="تغيير لغة البوت داخل السيرفر.", inline=False)
        p4.add_field(name="`!setwelcome #قناة <رسالة>`", value="تفعيل رسالة الترحيب. استخدم `{user} {server} {count}`.\n`!setwelcome` بدون قناة = إيقاف.", inline=False)
        p4.add_field(name="`!setleave #قناة <رسالة>`", value="تفعيل رسالة الوداع.\n`!setleave` بدون قناة = إيقاف.", inline=False)
        p4.add_field(name="`!setautorole @رتبة`", value="رتبة تلقائية لكل عضو جديد.", inline=False)
        p4.add_field(name="`!ticketsetup #قناة [@رتبة_الدعم]`", value="إعداد نظام التذاكر ونشر لوحة الفتح (فيه اختيار سبب + تفاصيل).", inline=False)
        p4.add_field(name="`!setmodlog #قناة`", value="تفعيل سجل تلقائي لعمليات الإدارة (كيك/بان/تحذير).", inline=False)
        p4.add_field(name="`!giveaway <مدة> <عدد_الفايزين> <الجائزة>`", value="بدء جيف أواي (مثال: `!giveaway 1h 1 نيترو`).", inline=False)
        p4.add_field(name="`!gend <آيدي_الرسالة>`", value="إنهاء جيف أواي فوراً قبل ميعاده.", inline=False)

        p5 = discord.Embed(title="👑 أوامر المالك - (9/9) خاصة بمالك البوت بس", color=discord.Color.gold())
        p5.add_field(name="`!addgalaxies @user <عدد>`", value="🌌 إضافة مجرات (عملة عالمية) لأي عضو بأي سيرفر. حصري عليك.", inline=False)
        p5.add_field(name="`!removegalaxies @user <عدد>`", value="🌌 خصم مجرات من أي عضو. حصري عليك.", inline=False)
        p5.add_field(name="`!blacklist add/remove/list @user [سبب]`", value="حظر/فك حظر عضو من استخدام البوت بكل السيرفرات.", inline=False)
        p5.add_field(name="`!botusers`", value="عرض كل الأعضاء اللي استخدموا البوت ولو مرة (بكل السيرفرات).", inline=False)
        p5.add_field(name="`!servers`", value="عرض كل السيرفرات اللي فيها البوت (الاسم، الآيدي، عدد الأعضاء، المالك).", inline=False)
        p5.add_field(name="`!leaveserver <آيدي السيرفر>`", value="خلي البوت يغادر سيرفر معين.", inline=False)
        p5.add_field(name="`!setstatuschannel #قناة`", value="🔒 حصري عليك — روم يتغيّر اسمه تلقائي حسب حالة البوت (🟢 شغال / 🟡 صيانة). محدش يقدر يفعّلها في سيرفرات تانية.", inline=False)
        p5.add_field(name="`!maintenance on/off [سبب]`", value="🔒 حصري عليك — تفعيل/إلغاء وضع الصيانة.", inline=False)
        p5.add_field(name="`!grantpremium @user <أيام>`", value="🔒 حصري عليك — فعّل بريميوم شخصي لأي عضو.", inline=False)
        p5.add_field(name="`!revokepremium @user`", value="🔒 حصري عليك — ألغي بريميوم عضو.", inline=False)
        p5.add_field(name="`!serverpremium <آيدي_السيرفر> <أيام>`", value="🔒 حصري عليك — فعّل بريميوم لسيرفر كامل.", inline=False)
        p5.add_field(name="`!revokeserverpremium <آيدي_السيرفر>`", value="🔒 حصري عليك — ألغي بريميوم سيرفر.", inline=False)
        p5.add_field(name="`!setname <الاسم الجديد>`", value="تغيير اسم البوت.", inline=False)
        p5.add_field(name="`!setavatar <رابط/صورة>`", value="تغيير صورة البوت الشخصية.", inline=False)
        p5.add_field(name="`!setstatus <النص>`", value="تغيير الحالة (Activity) الخاصة بالبوت.", inline=False)
    else:
        p1 = discord.Embed(title="🌌 Member Commands - (1/9) Economy", color=discord.Color.purple())
        p1.add_field(name="`!galaxies`", value="Check your Galaxies balance.", inline=False)
        p1.add_field(name="`!daily`", value="Claim daily reward (50-200 random, doubled for Premium 💎).", inline=False)
        p1.add_field(name="`!transfer @user <amount>`", value="Transfer Galaxies to another member.", inline=False)
        p1.add_field(name="`!leaderboard`", value="Top 10 richest members (global Galaxies).", inline=False)
        p1.add_field(name="`!stardust [@user]`", value="Check your Stardust 💫 balance (this server's own currency).", inline=False)
        p1.add_field(name="`!serverleaderboard`", value="Top 10 Stardust holders in this server.", inline=False)

        p1b = discord.Embed(title="👤 Member Commands - (2/9) Profile & Utility", color=discord.Color.purple())
        p1b.add_field(name="`!profile [@user]`", value="View profile, Galaxies, Stardust & warnings.", inline=False)
        p1b.add_field(name="`!avatar [@user]`", value="Show a member's full-size avatar.", inline=False)
        p1b.add_field(name="`!ping`", value="Check bot latency.", inline=False)
        p1b.add_field(name="`!uptime`", value="How long the bot has been running without interruption.", inline=False)
        p1b.add_field(name="`!note save <text>`", value="Save a personal note (global, works across every server).", inline=False)
        p1b.add_field(name="`!note list`", value="Show all your saved notes.", inline=False)
        p1b.add_field(name="`!note delete <number>`", value="Delete a specific note.", inline=False)

        p6 = discord.Embed(title="💎 Member Commands - (3/9) Premium", color=discord.Color.gold())
        p6.add_field(name="`!premium`", value="Full breakdown of personal & server Premium perks (sent via DM).", inline=False)
        p6.add_field(name="`!premiumcheck [@user]`", value="Check a member's Premium status, with a subscribe button if not active.", inline=False)
        p6.add_field(name="`!premiumsettings color <#hex>`", value="Change your message color (Premium subscribers only).", inline=False)
        p6.add_field(name="`!premiumsettings title <text>`", value="Set a custom title next to your name (Premium subscribers only).", inline=False)
        p6.add_field(name="`!premiumgift @user`", value="Gift a friend a 1-week Premium trial (once, original subscribers only).", inline=False)
        p6.add_field(name="`!setprefix <symbol>`", value="Change the server's prefix (Server Premium only).", inline=False)

        p2 = discord.Embed(title="🎉 Member Commands - (4/9) Fun & Tickets", color=discord.Color.teal())
        p2.add_field(name="`!8ball <question>`", value="Ask the magic 8-ball.", inline=False)
        p2.add_field(name="`!roll [sides]`", value="Roll a die (default 6 sides).", inline=False)
        p2.add_field(name="`!coinflip`", value="Flip a coin.", inline=False)
        p2.add_field(name="`!rps <rock/paper/scissors>`", value="Play rock-paper-scissors vs the bot.", inline=False)
        p2.add_field(name="`!joke`", value="Random joke.", inline=False)
        p2.add_field(name="`!ship @user1 [@user2]`", value="Compatibility percentage between two members.", inline=False)
        p2.add_field(name="`!poll <question>`", value="Quick reaction poll.", inline=False)
        p2.add_field(name="`!afk [reason]`", value="Go AFK — the bot replies for you if someone pings you.", inline=False)
        p2.add_field(name="🎫 Open a ticket", value="Click the green button in the tickets channel (if enabled).", inline=False)

        p3 = discord.Embed(title="🛡️ Admin Commands - (5/9) Basic Moderation", color=discord.Color.dark_red())
        p3.add_field(name="`!clear <amount>`", value="Clear messages.", inline=False)
        p3.add_field(name="`!kick @user [reason]`", value="Kick a member.", inline=False)
        p3.add_field(name="`!ban @user [reason]`", value="Ban a member.", inline=False)
        p3.add_field(name="`!unban <ID>`", value="Unban a member by ID.", inline=False)
        p3.add_field(name="`!timeout @user <minutes>`", value="Timeout a member.", inline=False)
        p3.add_field(name="`!untimeout @user`", value="Remove a timeout.", inline=False)
        p3.add_field(name="`!lock` / `!unlock`", value="Lock/unlock the current channel.", inline=False)
        p3.add_field(name="`!slowmode <seconds>`", value="Set channel slowmode.", inline=False)

        p3c = discord.Embed(title="⚠️ Admin Commands - (6/9) Warnings & Economy", color=discord.Color.dark_red())
        p3c.add_field(name="`!warn @user [reason]`", value="Warn a member.", inline=False)
        p3c.add_field(name="`!warnings [@user]`", value="Show a member's warnings.", inline=False)
        p3c.add_field(name="`!clearwarnings @user`", value="Clear all warnings for a member.", inline=False)
        p3c.add_field(name="`!nickname @user <name>`", value="Change a member's nickname.", inline=False)
        p3c.add_field(name="`!addstardust @user <amount>`", value="Add Stardust 💫 to a user (your server's own currency, not global).", inline=False)
        p3c.add_field(name="`!removestardust @user <amount>`", value="Remove Stardust from a user.", inline=False)

        p3b = discord.Embed(title="🎭 Admin Commands - (7/9) Roles & Channels", color=discord.Color.dark_red())
        p3b.add_field(name="`!createrole <name> [#color]`", value="Create a new role.", inline=False)
        p3b.add_field(name="`!deleterole @role`", value="Delete a role.", inline=False)
        p3b.add_field(name="`!addrole @user @role`", value="Give a role to a member.", inline=False)
        p3b.add_field(name="`!removerole @user @role`", value="Remove a role from a member.", inline=False)
        p3b.add_field(name="`!createchannel <name> [text/voice]`", value="Create a new channel.", inline=False)
        p3b.add_field(name="`!deletechannel #channel`", value="Delete a channel.", inline=False)
        p3b.add_field(name="`!renamechannel #channel <name>`", value="Rename a channel.", inline=False)
        p3b.add_field(name="`!purgeuser @user [amount]`", value="Delete a specific member's messages in this channel only.", inline=False)
        p3b.add_field(name="`!announce #channel <message>`", value="Send an official message from the bot to a channel.", inline=False)
        p3b.add_field(name="`!serverinfo`", value="Show full server information.", inline=False)

        p4 = discord.Embed(title="⚙️ Admin Commands - (8/9) Server Setup", color=discord.Color.orange())
        p4.add_field(name="`!setlang <ar/en>`", value="Change server language.", inline=False)
        p4.add_field(name="`!setwelcome #channel <message>`", value="Enable welcome messages. Use `{user} {server} {count}`.\n`!setwelcome` with no channel = disable.", inline=False)
        p4.add_field(name="`!setleave #channel <message>`", value="Enable leave messages.\n`!setleave` with no channel = disable.", inline=False)
        p4.add_field(name="`!setautorole @role`", value="Auto-role for new members.", inline=False)
        p4.add_field(name="`!ticketsetup #channel [@staff_role]`", value="Set up the ticket system and post the panel (with reason + detail flow).", inline=False)
        p4.add_field(name="`!setmodlog #channel`", value="Auto-log moderation actions (kicks/bans/warnings).", inline=False)
        p4.add_field(name="`!giveaway <duration> <winners> <prize>`", value="Start a giveaway (e.g. `!giveaway 1h 1 Nitro`).", inline=False)
        p4.add_field(name="`!gend <message_id>`", value="End a giveaway early.", inline=False)

        p5 = discord.Embed(title="👑 Owner Commands - (9/9) Bot owner only", color=discord.Color.gold())
        p5.add_field(name="`!addgalaxies @user <amount>`", value="🌌 Add Galaxies (global currency) to any user in any server. Owner-only.", inline=False)
        p5.add_field(name="`!removegalaxies @user <amount>`", value="🌌 Remove Galaxies from any user. Owner-only.", inline=False)
        p5.add_field(name="`!blacklist add/remove/list @user [reason]`", value="Block/unblock a user from the bot across every server.", inline=False)
        p5.add_field(name="`!botusers`", value="List every user who has ever used the bot (across all servers).", inline=False)
        p5.add_field(name="`!servers`", value="List every server the bot is in (name, ID, member count, owner).", inline=False)
        p5.add_field(name="`!leaveserver <guild ID>`", value="Make the bot leave a specific server.", inline=False)
        p5.add_field(name="`!setstatuschannel #channel`", value="🔒 Owner-only — a channel that auto-renames based on bot status. No other server can enable this.", inline=False)
        p5.add_field(name="`!maintenance on/off [reason]`", value="🔒 Owner-only — toggle maintenance mode.", inline=False)
        p5.add_field(name="`!grantpremium @user <days>`", value="🔒 Owner-only — activate personal Premium for a user.", inline=False)
        p5.add_field(name="`!revokepremium @user`", value="🔒 Owner-only — revoke a user's Premium.", inline=False)
        p5.add_field(name="`!serverpremium <guild_id> <days>`", value="🔒 Owner-only — activate Premium for an entire server.", inline=False)
        p5.add_field(name="`!revokeserverpremium <guild_id>`", value="🔒 Owner-only — revoke a server's Premium.", inline=False)
        p5.add_field(name="`!setname <name>`", value="Change bot username.", inline=False)
        p5.add_field(name="`!setavatar <url/file>`", value="Change bot avatar.", inline=False)
        p5.add_field(name="`!setstatus <text>`", value="Change bot activity status.", inline=False)

    pages = [p1, p1b, p6, p2, p3, p3c, p3b, p4, p5]

    if lang == "ar":
        section_labels = [
            "🌌 الاقتصاد",
            "👤 البروفايل والأدوات",
            "💎 البريميوم",
            "🎉 الترفيه والتذاكر",
            "🛡️ الإشراف الأساسي",
            "⚠️ التحذيرات والاقتصاد",
            "🎭 الرتب والرومات",
            "⚙️ إعداد السيرفر",
            "👑 أوامر المالك",
        ]
    else:
        section_labels = [
            "🌌 Economy",
            "👤 Profile & Utility",
            "💎 Premium",
            "🎉 Fun & Tickets",
            "🛡️ Basic Moderation",
            "⚠️ Warnings & Economy",
            "🎭 Roles & Channels",
            "⚙️ Server Setup",
            "👑 Owner Commands",
        ]

    view = HelpPaginator(ctx, pages, lang, section_labels)
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
        if lang == "ar":
            await ctx.send(f"⏳ أخذت مكافأتك اليومية بالفعل! يرجى الانتظار **{hours} ساعة و {minutes} دقيقة و {seconds} ثانية**.")
        else:
            await ctx.send(f"⏳ You already claimed your daily reward! Wait **{hours}h {minutes}m {seconds}s**.")
        return

    base_reward = random.randint(50, 200)
    reward = base_reward
    is_premium = is_premium_active(user_id)
    if is_premium:
        reward = base_reward * 2

    user_galaxies[user_id] = user_galaxies.get(user_id, 0) + reward
    user_last_daily[user_id] = now
    await save_galaxies()
    await save_daily()

    if is_premium:
        if lang == "ar":
            await ctx.send(f"🎉 حصلت على **{base_reward}** مجرة، اتضاعفت لـ **{reward}** 💎 بسبب اشتراكك في Premium! رصيدك الحالي: **{user_galaxies[user_id]}** مجرة 🌌")
        else:
            await ctx.send(f"🎉 You got **{base_reward}** Galaxies, doubled to **{reward}** 💎 thanks to your Premium subscription! Current balance: **{user_galaxies[user_id]}** Galaxies 🌌")
    else:
        if lang == "ar":
            await ctx.send(f"🎉 حصلت على **{reward}** مجرة هدية اليوم! رصيدك الحالي: **{user_galaxies[user_id]}** مجرة 🌌")
        else:
            await ctx.send(f"🎉 You claimed **{reward}** Galaxies today! Current balance: **{user_galaxies[user_id]}** Galaxies 🌌")


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
    await save_galaxies()

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


@bot.hybrid_command(name="profile", aliases=["بروفايل", "p"], description="عرض بروفايلك أو بروفايل عضو / View your profile or a member's profile")
@discord.app_commands.describe(member="العضو (اختياري) / The member (optional)")
async def profile(ctx, member: discord.Member = None):
    target = member or ctx.author
    amount = user_galaxies.get(target.id, 0)
    lang = get_lang(ctx.guild)
    warns_count = len(user_warns.get(target.id, []))

    premium_data = premium_users.get(target.id)
    is_premium = is_premium_active(target.id)
    is_gift_active = bool(is_premium and premium_data and premium_data.get("is_gift"))
    was_premium_ever = bool(premium_data and premium_data.get("was_premium_ever"))
    custom_title = premium_data.get("custom_title") if premium_data else None
    embed_color = discord.Color.purple()
    if is_premium and premium_data and premium_data.get("embed_color"):
        try:
            embed_color = discord.Color(int(premium_data["embed_color"], 16))
        except ValueError:
            pass

    badge = ""
    if is_premium and not is_gift_active:
        badge = " 💎"
    elif was_premium_ever and not is_premium:
        badge = " 🔘"  # بادچ باهت - كان مشترك أساسي قبل كده وانتهى اشتراكه

    title_line = f"👤 بروفايل {target.display_name}{badge}" if lang == "ar" else f"👤 {target.display_name}'s Profile{badge}"
    if custom_title:
        title_line += f" • {custom_title}"

    embed = discord.Embed(title=title_line, color=embed_color)
    embed.set_thumbnail(url=target.display_avatar.url)

    stardust_amount = user_stardust.get(ctx.guild.id, {}).get(target.id, 0) if ctx.guild else 0

    if lang == "ar":
        embed.add_field(name="🌌 المجرات:", value=f"`{amount}`", inline=True)
        embed.add_field(name="💫 الغبار النجمي (هذا السيرفر):", value=f"`{stardust_amount}`", inline=True)
        embed.add_field(name="⚠️ التحذيرات:", value=f"`{warns_count}`", inline=True)
        if was_premium_ever:
            months = max(1, int((time.time() - premium_data["first_subscribed"]) // 2592000))
            status_line = f"🏆 مشترك Premium من {months} شهر" if is_premium else "🔘 اشتراك Premium سابق (منتهي)"
            embed.add_field(name="💎 Premium:", value=status_line, inline=False)
        embed.add_field(name="📅 تاريخ إنشاء الحساب:", value=f"<t:{int(target.created_at.timestamp())}:R>", inline=False)
        if getattr(target, "joined_at", None):
            embed.add_field(name="📥 انضمامه للسيرفر:", value=f"<t:{int(target.joined_at.timestamp())}:R>", inline=False)
    else:
        embed.add_field(name="🌌 Galaxies:", value=f"`{amount}`", inline=True)
        embed.add_field(name="💫 Stardust (this server):", value=f"`{stardust_amount}`", inline=True)
        embed.add_field(name="⚠️ Warnings:", value=f"`{warns_count}`", inline=True)
        if was_premium_ever:
            months = max(1, int((time.time() - premium_data["first_subscribed"]) // 2592000))
            status_line = f"🏆 Premium member for {months} month(s)" if is_premium else "🔘 Former Premium (expired)"
            embed.add_field(name="💎 Premium:", value=status_line, inline=False)
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


# ============================================================
#  3. أوامر الترفيه
# ============================================================
EIGHT_BALL_AR = [
    "نعم أكيد 🌟", "من المحتمل 🙂", "غير متأكد، جرب تسأل بعدين 🤔",
    "لا أعتقد ذلك ❌", "بالتأكيد لا 🚫", "الاحتمالات جيدة ✅",
    "اسأل مرة ثانية بعدين 🔄", "لا تعتمد عليه ⚠️", "أكيد 100% 💯", "مستحيل ❌",
]
EIGHT_BALL_EN = [
    "Yes, definitely 🌟", "It is likely 🙂", "Unclear, try again later 🤔",
    "I don't think so ❌", "Absolutely not 🚫", "Signs point to yes ✅",
    "Ask again later 🔄", "Don't count on it ⚠️", "Without a doubt 💯", "No way ❌",
]

JOKES_AR = [
    "ليش الكمبيوتر تعبان؟ لأنه فاقد الذاكرة! 😂",
    "واحد سأل صاحبه: ليش تلبس نظارتين؟ قال: عشان أشوف مضاعف! 😂",
    "ليش السمكة ما تحب تلعب تنس؟ لأنها تخاف من الشبكة! 🐟",
]
JOKES_EN = [
    "Why don't programmers like nature? Too many bugs. 😂",
    "Why did the scarecrow win an award? He was outstanding in his field! 😂",
    "Why don't skeletons fight each other? They don't have the guts. 💀",
]


@bot.command(name="8ball", aliases=["ايت_بول", "سؤال"])
async def eightball(ctx, *, question: str = None):
    lang = get_lang(ctx.guild)
    if not question:
        msg = "❌ لازم تسأل سؤال! مثال: `!8ball هل بكرة يوم حلو؟`" if lang == "ar" else "❌ Ask a question! Example: `!8ball will today be good?`"
        return await ctx.send(msg)

    answer = random.choice(EIGHT_BALL_AR if lang == "ar" else EIGHT_BALL_EN)
    title = "🎱 الكرة السحرية" if lang == "ar" else "🎱 Magic 8-Ball"
    q_label = "❓ السؤال" if lang == "ar" else "❓ Question"
    a_label = "💬 الجواب" if lang == "ar" else "💬 Answer"
    embed = discord.Embed(title=title, color=discord.Color.dark_purple())
    embed.add_field(name=q_label, value=question, inline=False)
    embed.add_field(name=a_label, value=answer, inline=False)
    await ctx.send(embed=embed)


@bot.command(aliases=["نرد", "دحرجة"])
async def roll(ctx, sides: int = 6):
    lang = get_lang(ctx.guild)
    if sides < 2 or sides > 1000:
        msg = "❌ اختر رقم بين 2 و 1000." if lang == "ar" else "❌ Choose a number between 2 and 1000."
        return await ctx.send(msg)
    result = random.randint(1, sides)
    msg = f"🎲 طلع لك: **{result}** (من 1 إلى {sides})" if lang == "ar" else f"🎲 You rolled: **{result}** (out of {sides})"
    await ctx.send(msg)


@bot.command(aliases=["عملة", "فلب"])
async def coinflip(ctx):
    lang = get_lang(ctx.guild)
    if lang == "ar":
        result = random.choice(["👑 صورة", "🪙 كتابة"])
        await ctx.send(f"🪙 رميت العملة... طلعت: **{result}**")
    else:
        result = random.choice(["Heads", "Tails"])
        await ctx.send(f"🪙 Flipping the coin... It's **{result}**!")


@bot.command(name="rps", aliases=["حجر"])
async def rock_paper_scissors(ctx, choice: str = None):
    lang = get_lang(ctx.guild)
    mapping = {
        "rock": "rock", "حجر": "rock",
        "paper": "paper", "ورقة": "paper",
        "scissors": "scissors", "مقص": "scissors",
    }
    if not choice or choice.lower() not in mapping:
        msg = "❌ الاستخدام: `!rps <حجر/ورقة/مقص>`" if lang == "ar" else "❌ Usage: `!rps <rock/paper/scissors>`"
        return await ctx.send(msg)

    user_choice = mapping[choice.lower()]
    bot_choice = random.choice(["rock", "paper", "scissors"])
    emojis = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}
    names_ar = {"rock": "حجر", "paper": "ورقة", "scissors": "مقص"}

    if user_choice == bot_choice:
        result = "🤝 تعادل!" if lang == "ar" else "🤝 It's a tie!"
    elif (user_choice == "rock" and bot_choice == "scissors") or \
         (user_choice == "paper" and bot_choice == "rock") or \
         (user_choice == "scissors" and bot_choice == "paper"):
        result = "🎉 فزت!" if lang == "ar" else "🎉 You win!"
    else:
        result = "😢 خسرت!" if lang == "ar" else "😢 You lose!"

    if lang == "ar":
        await ctx.send(f"أنت: {emojis[user_choice]} {names_ar[user_choice]} | البوت: {emojis[bot_choice]} {names_ar[bot_choice]}\n{result}")
    else:
        await ctx.send(f"You: {emojis[user_choice]} {user_choice} | Bot: {emojis[bot_choice]} {bot_choice}\n{result}")


@bot.command(aliases=["نكتة"])
async def joke(ctx):
    lang = get_lang(ctx.guild)
    j = random.choice(JOKES_AR if lang == "ar" else JOKES_EN)
    await ctx.send(f"😂 {j}")


@bot.command(aliases=["زواج", "توافق"])
async def ship(ctx, member1: discord.Member = None, member2: discord.Member = None):
    lang = get_lang(ctx.guild)
    if member1 is not None and member2 is None:
        member2 = member1
        member1 = ctx.author

    if member1 is None or member2 is None:
        msg = "❌ الاستخدام: `!ship @user1 [@user2]`" if lang == "ar" else "❌ Usage: `!ship @user1 [@user2]`"
        return await ctx.send(msg)

    combined = str(member1.id) + str(member2.id)
    percent = sum(ord(c) for c in combined) % 101
    hearts = "❤️" * (percent // 20) + "🖤" * (5 - percent // 20)

    title = "💘 نسبة التوافق" if lang == "ar" else "💘 Compatibility"
    embed = discord.Embed(title=title, color=discord.Color.magenta())
    embed.description = f"{member1.mention} 💞 {member2.mention}\n\n**{percent}%**\n{hearts}"
    await ctx.send(embed=embed)


@bot.command(aliases=["تصويت"])
async def poll(ctx, *, question: str = None):
    lang = get_lang(ctx.guild)
    if not question:
        msg = "❌ الاستخدام: `!poll <سؤال>`" if lang == "ar" else "❌ Usage: `!poll <question>`"
        return await ctx.send(msg)

    title = "📊 تصويت" if lang == "ar" else "📊 Poll"
    footer = f"بدأه {ctx.author.display_name}" if lang == "ar" else f"Started by {ctx.author.display_name}"
    embed = discord.Embed(title=title, description=question, color=discord.Color.blue())
    embed.set_footer(text=footer)
    poll_msg = await ctx.send(embed=embed)
    await poll_msg.add_reaction("👍")
    await poll_msg.add_reaction("👎")


# ============================================================
#  4. أوامر الإدارة - الإشراف والتحذيرات
# ============================================================
@bot.command(aliases=["givegalaxies", "منح_مجرات"])
@commands.is_owner()
async def addgalaxies(ctx, member: discord.User = None, amount: int = None):
    """🌌 المجرات عملة عالمية - إضافتها حصراً على مالك البوت مهما كان أدمن أي سيرفر."""
    lang = get_lang(ctx.guild)
    if member is None or amount is None or amount <= 0:
        msg = "❌ الاستخدام الصحيح: `!addgalaxies @user <عدد>`" if lang == "ar" else "❌ Usage: `!addgalaxies @user <amount>`"
        return await ctx.send(msg)
    user_galaxies[member.id] = user_galaxies.get(member.id, 0) + amount
    await save_galaxies()
    await ctx.send(f"✅ تم إضافة **{amount}** مجرة 🌌 إلى **{member}**. رصيده الآن: **{user_galaxies[member.id]}**.")


@bot.command(aliases=["takegalaxies", "سحب_مجرات"])
@commands.is_owner()
async def removegalaxies(ctx, member: discord.User = None, amount: int = None):
    """🌌 المجرات عملة عالمية - خصمها حصراً على مالك البوت."""
    lang = get_lang(ctx.guild)
    if member is None or amount is None or amount <= 0:
        msg = "❌ الاستخدام الصحيح: `!removegalaxies @user <عدد>`" if lang == "ar" else "❌ Usage: `!removegalaxies @user <amount>`"
        return await ctx.send(msg)
    current = user_galaxies.get(member.id, 0)
    user_galaxies[member.id] = max(0, current - amount)
    await save_galaxies()
    await ctx.send(f"✅ تم خصم **{amount}** مجرة 🌌 من **{member}**. الرصيد الحالي: **{user_galaxies[member.id]}**.")


# ============================================================
#  عملة السيرفرات (Stardust) - منفصلة عن المجرات، كل أدمن يتحكم فيها
#  بسيرفره بس، وما تدخل قائمة أغنى 10 لأنها مو عملة عالمية
# ============================================================
@bot.command(aliases=["addstars", "منح_نجوم"])
@commands.has_permissions(administrator=True)
async def addstardust(ctx, member: discord.Member = None, amount: int = None):
    lang = get_lang(ctx.guild)
    if member is None or amount is None or amount <= 0:
        msg = "❌ الاستخدام الصحيح: `!addstardust @user <عدد>`" if lang == "ar" else "❌ Usage: `!addstardust @user <amount>`"
        return await ctx.send(msg)
    guild_wallet = user_stardust.setdefault(ctx.guild.id, {})
    guild_wallet[member.id] = guild_wallet.get(member.id, 0) + amount
    await save_stardust()
    msg = f"✅ تم إضافة **{amount}** 💫 (غبار نجمي) إلى {member.mention}. رصيده بهذا السيرفر: **{guild_wallet[member.id]}**." if lang == "ar" else f"✅ Added **{amount}** 💫 Stardust to {member.mention}. Their balance here: **{guild_wallet[member.id]}**."
    await ctx.send(msg)


@bot.command(aliases=["removestars", "سحب_نجوم"])
@commands.has_permissions(administrator=True)
async def removestardust(ctx, member: discord.Member = None, amount: int = None):
    lang = get_lang(ctx.guild)
    if member is None or amount is None or amount <= 0:
        msg = "❌ الاستخدام الصحيح: `!removestardust @user <عدد>`" if lang == "ar" else "❌ Usage: `!removestardust @user <amount>`"
        return await ctx.send(msg)
    guild_wallet = user_stardust.setdefault(ctx.guild.id, {})
    current = guild_wallet.get(member.id, 0)
    guild_wallet[member.id] = max(0, current - amount)
    await save_stardust()
    msg = f"✅ تم خصم **{amount}** 💫 من {member.mention}. الرصيد الحالي: **{guild_wallet[member.id]}**." if lang == "ar" else f"✅ Removed **{amount}** 💫 from {member.mention}. Current balance: **{guild_wallet[member.id]}**."
    await ctx.send(msg)


@bot.command(aliases=["stars", "نجوم", "غبار"])
async def stardust(ctx, member: discord.Member = None):
    target = member or ctx.author
    lang = get_lang(ctx.guild)
    amount = user_stardust.get(ctx.guild.id, {}).get(target.id, 0)
    msg = f"💫 رصيد **{target.mention}** بهذا السيرفر: **{amount}** غبار نجمي." if lang == "ar" else f"💫 **{target.mention}**'s Stardust balance in this server: **{amount}**."
    await ctx.send(msg)


@bot.command(aliases=["أغنى_السيرفر", "serverlb"])
async def serverleaderboard(ctx):
    lang = get_lang(ctx.guild)
    guild_wallet = user_stardust.get(ctx.guild.id, {})
    if not guild_wallet:
        msg = "لا يوجد أي رصيد غبار نجمي مسجل بهذا السيرفر بعد." if lang == "ar" else "No Stardust recorded in this server yet."
        return await ctx.send(msg)

    top = sorted(guild_wallet.items(), key=lambda x: x[1], reverse=True)[:10]
    title = "💫 أغنى 10 أعضاء بالغبار النجمي (هذا السيرفر)" if lang == "ar" else "💫 Top 10 Stardust Holders (This Server)"
    embed = discord.Embed(title=title, color=discord.Color.blue())
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, (uid, amount) in enumerate(top):
        member = ctx.guild.get_member(uid)
        name = member.display_name if member else f"User {uid}"
        prefix = medals[i] if i < 3 else f"`{i + 1}.`"
        lines.append(f"{prefix} **{name}** — {amount} 💫")
    embed.description = "\n".join(lines)
    await ctx.send(embed=embed)


# ============================================================
#  نظام متجر السيرفر (Shop) - كل سيرفر بمتجره الخاص، بيشتري
#  بالغبار النجمي (Stardust) عشان يفضل خاص بالسيرفر مش عالمي
# ============================================================
shop_items = {}  # {guild_id: {item_name_lower: {"name":, "price":, "role_id": int|None}}}


def save_shop():
    return storage_save("shop", {str(gk): iv for gk, iv in shop_items.items()})


@bot.command(aliases=["اضافة_منتج"])
@commands.has_permissions(administrator=True)
async def additem(ctx, price: int = None, role: discord.Role = None, *, name: str = None):
    lang = get_lang(ctx.guild)
    if price is None or not name:
        msg = "❌ الاستخدام: `!additem <السعر> [@رتبة] <اسم المنتج>`\nمثال: `!additem 500 @VIP رتبة VIP`" if lang == "ar" else "❌ Usage: `!additem <price> [@role] <item name>`\nExample: `!additem 500 @VIP VIP Role`"
        return await ctx.send(msg)
    if price <= 0:
        msg = "❌ السعر لازم يكون أكبر من 0." if lang == "ar" else "❌ Price must be greater than 0."
        return await ctx.send(msg)

    guild_shop = shop_items.setdefault(ctx.guild.id, {})
    guild_shop[name.lower()] = {"name": name, "price": price, "role_id": role.id if role else None}
    await save_shop()

    msg = f"✅ تم إضافة **{name}** للمتجر بسعر **{price}** 💫." if lang == "ar" else f"✅ Added **{name}** to the shop for **{price}** 💫."
    await ctx.send(msg)


@bot.command(aliases=["حذف_منتج"])
@commands.has_permissions(administrator=True)
async def removeitem(ctx, *, name: str = None):
    lang = get_lang(ctx.guild)
    guild_shop = shop_items.get(ctx.guild.id, {})
    if not name or name.lower() not in guild_shop:
        msg = "❌ المنتج ده مش موجود في المتجر." if lang == "ar" else "❌ That item isn't in the shop."
        return await ctx.send(msg)

    del guild_shop[name.lower()]
    await save_shop()
    msg = f"✅ تم حذف **{name}** من المتجر." if lang == "ar" else f"✅ Removed **{name}** from the shop."
    await ctx.send(msg)


@bot.command(aliases=["متجر"])
async def shop(ctx):
    lang = get_lang(ctx.guild)
    guild_shop = shop_items.get(ctx.guild.id, {})
    if not guild_shop:
        msg = "❌ المتجر فاضي دلوقتي، محدش ضاف منتجات لسه." if lang == "ar" else "❌ The shop is empty right now."
        return await ctx.send(msg)

    title = "🛒 متجر السيرفر" if lang == "ar" else "🛒 Server Shop"
    embed = discord.Embed(title=title, color=discord.Color.blue())
    for item in guild_shop.values():
        role_note = " (🎭 يمنح رتبة)" if lang == "ar" and item.get("role_id") else (" (🎭 grants a role)" if item.get("role_id") else "")
        embed.add_field(name=f"{item['name']} — {item['price']} 💫", value=f"`!buy {item['name']}`{role_note}", inline=False)
    footer = "استخدم !stardust عشان تشوف رصيدك" if lang == "ar" else "Use !stardust to check your balance"
    embed.set_footer(text=footer)
    await ctx.send(embed=embed)


@bot.command(aliases=["شراء"])
async def buy(ctx, *, name: str = None):
    lang = get_lang(ctx.guild)
    guild_shop = shop_items.get(ctx.guild.id, {})
    if not name or name.lower() not in guild_shop:
        msg = "❌ المنتج ده مش موجود في المتجر. استخدم `!shop` عشان تشوف المتاح." if lang == "ar" else "❌ That item isn't in the shop. Use `!shop` to see what's available."
        return await ctx.send(msg)

    item = guild_shop[name.lower()]
    guild_wallet = user_stardust.setdefault(ctx.guild.id, {})
    balance = guild_wallet.get(ctx.author.id, 0)

    if balance < item["price"]:
        msg = f"❌ رصيدك مش كافي. تحتاج **{item['price']}** 💫 وعندك **{balance}** بس." if lang == "ar" else f"❌ Not enough Stardust. You need **{item['price']}** 💫 but only have **{balance}**."
        return await ctx.send(msg)

    guild_wallet[ctx.author.id] = balance - item["price"]
    await save_stardust()

    role_msg = ""
    if item.get("role_id"):
        role = ctx.guild.get_role(item["role_id"])
        if role:
            try:
                await ctx.author.add_roles(role)
                role_msg = f" وتم إعطاؤك رتبة {role.mention}!" if lang == "ar" else f" and you received {role.mention}!"
            except discord.Forbidden:
                role_msg = " (⚠️ لكن مقدرتش أعطيك الرتبة، كلم الإدارة)" if lang == "ar" else " (⚠️ but I couldn't grant the role, contact staff)"

    msg = f"✅ اشتريت **{item['name']}**!{role_msg} رصيدك الحالي: **{guild_wallet[ctx.author.id]}** 💫" if lang == "ar" else f"✅ You bought **{item['name']}**!{role_msg} Your balance: **{guild_wallet[ctx.author.id]}** 💫"
    await ctx.send(msg)


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
        await send_modlog(ctx.guild, "👢 Kick", f"**العضو:** {member} (`{member.id}`)\n**بواسطة:** {ctx.author}\n**السبب:** {reason or 'بدون سبب'}")
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
        await send_modlog(ctx.guild, "🔨 Ban", f"**العضو:** {member} (`{member.id}`)\n**بواسطة:** {ctx.author}\n**السبب:** {reason or 'بدون سبب'}")
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
        msg = "❌ الاستخدام الصحيح: `!timeout @user <دقائق>`" if lang == "ar" else "❌ Usage: `!timeout @user <minutes>`"
        return await ctx.send(msg)
    duration = datetime.timedelta(minutes=minutes)
    try:
        await member.timeout(duration)
        await ctx.send(f"⏳ تم تطبيق تايم أوت على {member.mention} لمدة {minutes} دقيقة.")
        await send_modlog(ctx.guild, "⏳ Timeout", f"**العضو:** {member} (`{member.id}`)\n**بواسطة:** {ctx.author}\n**المدة:** {minutes} دقيقة")
    except discord.Forbidden:
        msg = "❌ لا أملك صلاحية كافية لعمل تايم أوت لهذا العضو." if lang == "ar" else "❌ I don't have permission to timeout this member."
        await ctx.send(msg)


@bot.command(aliases=["removetimeout"])
@commands.has_permissions(moderate_members=True)
async def untimeout(ctx, member: discord.Member = None):
    lang = get_lang(ctx.guild)
    if member is None:
        msg = "❌ الاستخدام الصحيح: `!untimeout @user`" if lang == "ar" else "❌ Usage: `!untimeout @user`"
        return await ctx.send(msg)
    try:
        await member.timeout(None)
        await ctx.send(f"✅ تم إلغاء التايم أوت عن {member.mention}.")
    except discord.Forbidden:
        msg = "❌ لا أملك صلاحية كافية." if lang == "ar" else "❌ I don't have permission for that."
        await ctx.send(msg)


@bot.command(aliases=["تحذير"])
@commands.has_permissions(manage_messages=True)
async def warn(ctx, member: discord.Member = None, *, reason="بدون سبب"):
    lang = get_lang(ctx.guild)
    if member is None:
        msg = "❌ الاستخدام الصحيح: `!warn @user [سبب]`" if lang == "ar" else "❌ Usage: `!warn @user [reason]`"
        return await ctx.send(msg)

    entry = {"reason": reason, "moderator_id": ctx.author.id, "timestamp": time.time()}
    user_warns.setdefault(member.id, []).append(entry)
    await save_warns()

    count = len(user_warns[member.id])
    if lang == "ar":
        await ctx.send(f"⚠️ تم تحذير {member.mention}. السبب: {reason}\nإجمالي التحذيرات: **{count}**")
    else:
        await ctx.send(f"⚠️ {member.mention} has been warned. Reason: {reason}\nTotal warnings: **{count}**")
    await send_modlog(ctx.guild, "⚠️ Warn", f"**العضو:** {member} (`{member.id}`)\n**بواسطة:** {ctx.author}\n**السبب:** {reason}\n**الإجمالي:** {count}")


@bot.command(aliases=["تحذيرات"])
async def warnings(ctx, member: discord.Member = None):
    target = member or ctx.author
    lang = get_lang(ctx.guild)
    entries = user_warns.get(target.id, [])

    if not entries:
        msg = f"✅ لا يوجد أي تحذيرات لـ {target.mention}." if lang == "ar" else f"✅ {target.mention} has no warnings."
        return await ctx.send(msg)

    title = f"⚠️ تحذيرات {target.display_name}" if lang == "ar" else f"⚠️ {target.display_name}'s Warnings"
    embed = discord.Embed(title=title, color=discord.Color.orange())
    for i, entry in enumerate(entries, start=1):
        mod = ctx.guild.get_member(entry["moderator_id"]) if ctx.guild else None
        mod_name = mod.display_name if mod else "Unknown"
        date = datetime.datetime.fromtimestamp(entry["timestamp"]).strftime("%Y-%m-%d")
        embed.add_field(name=f"#{i} — {date}", value=f"السبب: {entry['reason']} | بواسطة: {mod_name}", inline=False)

    await ctx.send(embed=embed)


@bot.command(aliases=["مسح_تحذيرات"])
@commands.has_permissions(administrator=True)
async def clearwarnings(ctx, member: discord.Member = None):
    lang = get_lang(ctx.guild)
    if member is None:
        msg = "❌ الاستخدام الصحيح: `!clearwarnings @user`" if lang == "ar" else "❌ Usage: `!clearwarnings @user`"
        return await ctx.send(msg)
    user_warns[member.id] = []
    await save_warns()
    msg = f"✅ تم مسح جميع تحذيرات {member.mention}." if lang == "ar" else f"✅ Cleared all warnings for {member.mention}."
    await ctx.send(msg)


@bot.command(aliases=["nick", "اسم_مستعار"])
@commands.has_permissions(manage_nicknames=True)
async def nickname(ctx, member: discord.Member = None, *, new_nick: str = None):
    lang = get_lang(ctx.guild)
    if member is None:
        msg = "❌ الاستخدام: `!nickname @user <اسم جديد>`" if lang == "ar" else "❌ Usage: `!nickname @user <new name>`"
        return await ctx.send(msg)
    try:
        await member.edit(nick=new_nick)
        msg = f"✅ تم تغيير اسم {member.mention}." if lang == "ar" else f"✅ Changed {member.mention}'s nickname."
        await ctx.send(msg)
    except discord.Forbidden:
        msg = "❌ لا أملك صلاحية كافية." if lang == "ar" else "❌ I don't have permission for that."
        await ctx.send(msg)


@bot.command(aliases=["قفل"])
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    lang = get_lang(ctx.guild)
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
    msg = "🔒 تم قفل القناة." if lang == "ar" else "🔒 Channel locked."
    await ctx.send(msg)


@bot.command(aliases=["فتح"])
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    lang = get_lang(ctx.guild)
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
    msg = "🔓 تم فتح القناة." if lang == "ar" else "🔓 Channel unlocked."
    await ctx.send(msg)


@bot.command(aliases=["إبطاء"])
@commands.has_permissions(manage_channels=True)
async def slowmode(ctx, seconds: int = 0):
    lang = get_lang(ctx.guild)
    if seconds < 0 or seconds > 21600:
        msg = "❌ اختر رقم بين 0 و 21600 ثانية." if lang == "ar" else "❌ Choose between 0 and 21600 seconds."
        return await ctx.send(msg)
    await ctx.channel.edit(slowmode_delay=seconds)
    if seconds == 0:
        msg = "✅ تم إلغاء وضع الإبطاء." if lang == "ar" else "✅ Slowmode disabled."
    else:
        msg = f"✅ تم ضبط الإبطاء على {seconds} ثانية." if lang == "ar" else f"✅ Slowmode set to {seconds}s."
    await ctx.send(msg)


# ============================================================
#  4.5 إدارة الرتب والرومات والإعلانات (تحكم شامل بالسيرفر)
# ============================================================
@bot.command(aliases=["إنشاء_رتبة"])
@commands.has_permissions(manage_roles=True)
async def createrole(ctx, name: str = None, color: str = None):
    lang = get_lang(ctx.guild)
    if not name:
        msg = "❌ الاستخدام: `!createrole <اسم> [#كود_اللون]`" if lang == "ar" else "❌ Usage: `!createrole <name> [#hex_color]`"
        return await ctx.send(msg)

    role_color = discord.Color.default()
    if color:
        try:
            role_color = discord.Color(int(color.lstrip("#"), 16))
        except ValueError:
            msg = "❌ كود اللون غير صحيح، استخدم صيغة hex زي `#5865F2`." if lang == "ar" else "❌ Invalid color code, use hex format like `#5865F2`."
            return await ctx.send(msg)

    try:
        new_role = await ctx.guild.create_role(name=name, color=role_color)
        msg = f"✅ تم إنشاء الرتبة {new_role.mention}." if lang == "ar" else f"✅ Created role {new_role.mention}."
        await ctx.send(msg)
    except discord.Forbidden:
        msg = "❌ لا أملك صلاحية إنشاء رتب." if lang == "ar" else "❌ I don't have permission to create roles."
        await ctx.send(msg)


@bot.command(aliases=["حذف_رتبة"])
@commands.has_permissions(manage_roles=True)
async def deleterole(ctx, role: discord.Role = None):
    lang = get_lang(ctx.guild)
    if role is None:
        msg = "❌ الاستخدام: `!deleterole @رتبة`" if lang == "ar" else "❌ Usage: `!deleterole @role`"
        return await ctx.send(msg)
    try:
        role_name = role.name
        await role.delete()
        msg = f"✅ تم حذف رتبة **{role_name}**." if lang == "ar" else f"✅ Deleted role **{role_name}**."
        await ctx.send(msg)
    except discord.Forbidden:
        msg = "❌ لا أملك صلاحية حذف هذه الرتبة." if lang == "ar" else "❌ I don't have permission to delete this role."
        await ctx.send(msg)


@bot.command(aliases=["اعطاء_رتبة"])
@commands.has_permissions(manage_roles=True)
async def addrole(ctx, member: discord.Member = None, role: discord.Role = None):
    lang = get_lang(ctx.guild)
    if member is None or role is None:
        msg = "❌ الاستخدام: `!addrole @user @رتبة`" if lang == "ar" else "❌ Usage: `!addrole @user @role`"
        return await ctx.send(msg)
    try:
        await member.add_roles(role)
        msg = f"✅ تم إعطاء رتبة {role.mention} لـ {member.mention}." if lang == "ar" else f"✅ Gave {role.mention} to {member.mention}."
        await ctx.send(msg)
    except discord.Forbidden:
        msg = "❌ لا أملك صلاحية كافية (رتبتي لازم تكون أعلى من الرتبة دي)." if lang == "ar" else "❌ Missing permissions (my role must be higher than this role)."
        await ctx.send(msg)


@bot.command(aliases=["سحب_رتبة"])
@commands.has_permissions(manage_roles=True)
async def removerole(ctx, member: discord.Member = None, role: discord.Role = None):
    lang = get_lang(ctx.guild)
    if member is None or role is None:
        msg = "❌ الاستخدام: `!removerole @user @رتبة`" if lang == "ar" else "❌ Usage: `!removerole @user @role`"
        return await ctx.send(msg)
    try:
        await member.remove_roles(role)
        msg = f"✅ تم سحب رتبة {role.mention} من {member.mention}." if lang == "ar" else f"✅ Removed {role.mention} from {member.mention}."
        await ctx.send(msg)
    except discord.Forbidden:
        msg = "❌ لا أملك صلاحية كافية." if lang == "ar" else "❌ Missing permissions."
        await ctx.send(msg)


@bot.command(aliases=["إنشاء_روم"])
@commands.has_permissions(manage_channels=True)
async def createchannel(ctx, name: str = None, channel_type: str = "text"):
    lang = get_lang(ctx.guild)
    if not name:
        msg = "❌ الاستخدام: `!createchannel <اسم> [text/voice]`" if lang == "ar" else "❌ Usage: `!createchannel <name> [text/voice]`"
        return await ctx.send(msg)
    try:
        if channel_type.lower() in ["voice", "صوتي"]:
            new_channel = await ctx.guild.create_voice_channel(name)
        else:
            new_channel = await ctx.guild.create_text_channel(name)
        msg = f"✅ تم إنشاء الروم {new_channel.mention if hasattr(new_channel, 'mention') else new_channel.name}." if lang == "ar" else f"✅ Created channel {new_channel.mention if hasattr(new_channel, 'mention') else new_channel.name}."
        await ctx.send(msg)
    except discord.Forbidden:
        msg = "❌ لا أملك صلاحية إنشاء رومات." if lang == "ar" else "❌ I don't have permission to create channels."
        await ctx.send(msg)


@bot.command(aliases=["حذف_روم"])
@commands.has_permissions(manage_channels=True)
async def deletechannel(ctx, channel: discord.abc.GuildChannel = None):
    lang = get_lang(ctx.guild)
    if channel is None:
        msg = "❌ الاستخدام: `!deletechannel #روم`" if lang == "ar" else "❌ Usage: `!deletechannel #channel`"
        return await ctx.send(msg)
    try:
        name = channel.name
        await channel.delete()
        if channel.id != ctx.channel.id:
            msg = f"✅ تم حذف روم **{name}**." if lang == "ar" else f"✅ Deleted channel **{name}**."
            await ctx.send(msg)
    except discord.Forbidden:
        msg = "❌ لا أملك صلاحية حذف هذا الروم." if lang == "ar" else "❌ I don't have permission to delete this channel."
        await ctx.send(msg)


@bot.command(aliases=["تسمية_روم"])
@commands.has_permissions(manage_channels=True)
async def renamechannel(ctx, channel: discord.abc.GuildChannel = None, *, new_name: str = None):
    lang = get_lang(ctx.guild)
    if channel is None or not new_name:
        msg = "❌ الاستخدام: `!renamechannel #روم <اسم جديد>`" if lang == "ar" else "❌ Usage: `!renamechannel #channel <new name>`"
        return await ctx.send(msg)
    try:
        await channel.edit(name=new_name)
        msg = f"✅ تم تغيير اسم الروم إلى **{new_name}**." if lang == "ar" else f"✅ Renamed channel to **{new_name}**."
        await ctx.send(msg)
    except discord.Forbidden:
        msg = "❌ لا أملك صلاحية تعديل هذا الروم." if lang == "ar" else "❌ I don't have permission to edit this channel."
        await ctx.send(msg)


@bot.command(aliases=["مسح_رسائل_عضو"])
@commands.has_permissions(manage_messages=True)
async def purgeuser(ctx, member: discord.Member = None, amount: int = 50):
    lang = get_lang(ctx.guild)
    if member is None:
        msg = "❌ الاستخدام: `!purgeuser @user [عدد الرسائل للفحص]`" if lang == "ar" else "❌ Usage: `!purgeuser @user [messages to scan]`"
        return await ctx.send(msg)
    if amount < 1 or amount > 500:
        amount = 100

    def check(m):
        return m.author.id == member.id

    deleted = await ctx.channel.purge(limit=amount, check=check)
    msg = f"🧹 تم حذف **{len(deleted)}** رسالة من {member.mention}." if lang == "ar" else f"🧹 Deleted **{len(deleted)}** messages from {member.mention}."
    await ctx.send(msg, delete_after=4)


@bot.command(aliases=["اعلان", "say"])
@commands.has_permissions(administrator=True)
async def announce(ctx, channel: discord.TextChannel = None, *, message: str = None):
    lang = get_lang(ctx.guild)
    if channel is None or not message:
        msg = "❌ الاستخدام: `!announce #روم <الرسالة>`" if lang == "ar" else "❌ Usage: `!announce #channel <message>`"
        return await ctx.send(msg)
    embed = discord.Embed(description=message, color=discord.Color.gold())
    embed.set_footer(text=f"بواسطة {ctx.author.display_name}" if lang == "ar" else f"By {ctx.author.display_name}")
    try:
        await channel.send(embed=embed)
        confirm = f"✅ تم إرسال الإعلان في {channel.mention}." if lang == "ar" else f"✅ Announcement sent in {channel.mention}."
        await ctx.send(confirm)
    except discord.Forbidden:
        msg = "❌ لا أملك صلاحية الإرسال بهذا الروم." if lang == "ar" else "❌ I don't have permission to send messages there."
        await ctx.send(msg)


@bot.command(aliases=["معلومات_السيرفر", "si"])
async def serverinfo(ctx):
    lang = get_lang(ctx.guild)
    guild = ctx.guild
    owner = guild.owner if guild.owner else "N/A"

    title = f"📊 معلومات سيرفر {guild.name}" if lang == "ar" else f"📊 {guild.name} Server Info"
    embed = discord.Embed(title=title, color=discord.Color.purple())
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    if lang == "ar":
        embed.add_field(name="👑 المالك", value=str(owner), inline=True)
        embed.add_field(name="👥 الأعضاء", value=str(guild.member_count), inline=True)
        embed.add_field(name="🎭 الرتب", value=str(len(guild.roles)), inline=True)
        embed.add_field(name="💬 الرومات النصية", value=str(len(guild.text_channels)), inline=True)
        embed.add_field(name="🔊 الرومات الصوتية", value=str(len(guild.voice_channels)), inline=True)
        embed.add_field(name="🚀 مستوى البوست", value=str(guild.premium_tier), inline=True)
        embed.add_field(name="📅 تاريخ الإنشاء", value=f"<t:{int(guild.created_at.timestamp())}:R>", inline=False)
    else:
        embed.add_field(name="👑 Owner", value=str(owner), inline=True)
        embed.add_field(name="👥 Members", value=str(guild.member_count), inline=True)
        embed.add_field(name="🎭 Roles", value=str(len(guild.roles)), inline=True)
        embed.add_field(name="💬 Text Channels", value=str(len(guild.text_channels)), inline=True)
        embed.add_field(name="🔊 Voice Channels", value=str(len(guild.voice_channels)), inline=True)
        embed.add_field(name="🚀 Boost Level", value=str(guild.premium_tier), inline=True)
        embed.add_field(name="📅 Created", value=f"<t:{int(guild.created_at.timestamp())}:R>", inline=False)

    embed.set_footer(text=f"ID: {guild.id}")
    await ctx.send(embed=embed)


# ============================================================
#  5. أوامر إعداد السيرفر (لغة، ترحيب، وداع، رتبة تلقائية، تذاكر)
# ============================================================
@bot.command()
@commands.has_permissions(administrator=True)
async def setlang(ctx, lang: str = None):
    if not lang or lang.lower() not in ["ar", "en"]:
        return await ctx.send("❌ Usage: `!setlang ar` or `!setlang en`")
    server_langs[ctx.guild.id] = lang.lower()
    await save_langs()
    await ctx.send(f"✅ Language updated to **{lang.upper()}**")


@bot.command(aliases=["ترحيب"])
@commands.has_permissions(administrator=True)
async def setwelcome(ctx, channel: discord.TextChannel = None, *, message: str = None):
    lang = get_lang(ctx.guild)
    if channel is None:
        if ctx.guild.id in welcome_config:
            del welcome_config[ctx.guild.id]
            await save_welcome()
        msg = "✅ تم إيقاف رسائل الترحيب." if lang == "ar" else "✅ Welcome messages disabled."
        return await ctx.send(msg)

    if not message:
        message = "🎉 أهلاً {user} في {server}! أنت العضو رقم {count}." if lang == "ar" else "🎉 Welcome {user} to {server}! You're member #{count}."

    welcome_config[ctx.guild.id] = {"channel_id": channel.id, "message": message}
    await save_welcome()
    msg = f"✅ تم تفعيل الترحيب في {channel.mention}" if lang == "ar" else f"✅ Welcome messages enabled in {channel.mention}"
    await ctx.send(msg)


@bot.command(aliases=["وداع"])
@commands.has_permissions(administrator=True)
async def setleave(ctx, channel: discord.TextChannel = None, *, message: str = None):
    lang = get_lang(ctx.guild)
    if channel is None:
        if ctx.guild.id in leave_config:
            del leave_config[ctx.guild.id]
            await save_leave()
        msg = "✅ تم إيقاف رسائل الوداع." if lang == "ar" else "✅ Leave messages disabled."
        return await ctx.send(msg)

    if not message:
        message = "👋 {user} غادر {server}. عددنا الآن {count} عضو." if lang == "ar" else "👋 {user} left {server}. We're now {count} members."

    leave_config[ctx.guild.id] = {"channel_id": channel.id, "message": message}
    await save_leave()
    msg = f"✅ تم تفعيل الوداع في {channel.mention}" if lang == "ar" else f"✅ Leave messages enabled in {channel.mention}"
    await ctx.send(msg)


@bot.command(aliases=["رتبة_تلقائية"])
@commands.has_permissions(administrator=True)
async def setautorole(ctx, role: discord.Role = None):
    lang = get_lang(ctx.guild)
    if role is None:
        if ctx.guild.id in autorole_config:
            del autorole_config[ctx.guild.id]
            await save_autorole()
        msg = "✅ تم إيقاف الرتبة التلقائية." if lang == "ar" else "✅ Autorole disabled."
        return await ctx.send(msg)

    autorole_config[ctx.guild.id] = role.id
    await save_autorole()
    msg = f"✅ سيحصل كل عضو جديد على رتبة {role.mention} تلقائياً." if lang == "ar" else f"✅ New members will automatically get {role.mention}."
    await ctx.send(msg)


@bot.command(aliases=["إعداد_تذاكر"])
@commands.has_permissions(administrator=True)
async def ticketsetup(ctx, channel: discord.TextChannel = None, *staff_roles: discord.Role):
    lang = get_lang(ctx.guild)
    if channel is None:
        msg = "❌ الاستخدام: `!ticketsetup #قناة [@رتبة1] [@رتبة2] ...` — أي رتبة تحطها هنا، أو أي رتبة أعلى منها بترتيب السيرفر، هتقدر تشوف التذاكر." if lang == "ar" else "❌ Usage: `!ticketsetup #channel [@role1] [@role2] ...` — any role listed here, or any role ranked above it, will be able to see tickets."
        return await ctx.send(msg)

    category = discord.utils.get(ctx.guild.categories, name="Tickets")
    if category is None:
        category = await ctx.guild.create_category("Tickets")

    ticket_config[ctx.guild.id] = {
        "category_id": category.id,
        "staff_role_ids": [r.id for r in staff_roles],
        "panel_channel_id": channel.id,
    }
    await save_tickets()

    if lang == "ar":
        embed = discord.Embed(
            title="🎫 نظام التذاكر",
            description="اختر سبب فتح التذكرة من القائمة تحت، واملأ التفاصيل، وهيتفتح لك روم خاص بيك.",
            color=discord.Color.blurple(),
        )
    else:
        embed = discord.Embed(
            title="🎫 Support Tickets",
            description="Pick a reason from the menu below, fill in the details, and a private ticket channel will open for you.",
            color=discord.Color.blurple(),
        )

    await channel.send(embed=embed, view=TicketPanelView(is_home_guild=(ctx.guild.id == HOME_GUILD_ID)))
    msg = f"✅ تم إعداد نظام التذاكر في {channel.mention}" if lang == "ar" else f"✅ Ticket system set up in {channel.mention}"
    await ctx.send(msg)


# ============================================================
#  5.4.5 نظام حالة البوت التلقائي (Status Channel)
#  البوت بيغيّر اسم الروم لوحده لما يشتغل أو يدخل صيانة.
#  ملاحظة: مستحيل يغيّره لـ "قافل" وقت الكراش المفاجئ لأنه
#  وقتها مش شغال أصلاً وميقدرش ينفذ أي أمر - ده قيد منطقي.
# ============================================================
status_channel_config = {}
bot_start_time = time.time()
maintenance_state = {}  # guild_id -> {"on": bool, "reason": str}


def save_status_channel():
    return storage_save("status_channel", {str(k): v for k, v in status_channel_config.items()})


def save_maintenance_state():
    return storage_save("maintenance_state", {str(k): v for k, v in maintenance_state.items()})


async def update_status_channel(guild: discord.Guild, state: str):
    """state: 'online' | 'maintenance' | 'restarting'"""
    channel_id = status_channel_config.get(guild.id)
    if not channel_id:
        return
    channel = guild.get_channel(channel_id)
    if not channel:
        return

    labels = {
        "online": "🟢│status",
        "maintenance": "🟡│status",
        "restarting": "🟠│status",
    }
    new_name = labels.get(state, "🟢│status")
    try:
        if channel.name != new_name:
            await channel.edit(name=new_name)
    except discord.Forbidden:
        pass
    except discord.HTTPException:
        pass  # ديسكورد بيحدد عدد مرات تغيير اسم الروم (حد أقصى مرتين كل 10 دقايق تقريباً)


@bot.command(aliases=["روم_الحالة"])
@commands.is_owner()
@home_guild_only()
async def setstatuschannel(ctx, channel: discord.TextChannel = None):
    lang = get_lang(ctx.guild)
    if channel is None:
        if ctx.guild.id in status_channel_config:
            del status_channel_config[ctx.guild.id]
            await save_status_channel()
        msg = "✅ تم إيقاف تحديث روم الحالة التلقائي." if lang == "ar" else "✅ Auto status channel disabled."
        return await ctx.send(msg)

    status_channel_config[ctx.guild.id] = channel.id
    await save_status_channel()
    await update_status_channel(ctx.guild, "maintenance" if maintenance_state.get(ctx.guild.id, {}).get("on") else "online")
    msg = f"✅ هيتم تحديث حالة البوت تلقائياً في {channel.mention} (🟢 شغال / 🟡 صيانة)." if lang == "ar" else f"✅ Bot status will now auto-update in {channel.mention} (🟢 online / 🟡 maintenance)."
    await ctx.send(msg)


@bot.command(aliases=["صيانة"])
@commands.is_owner()
@home_guild_only()
async def maintenance(ctx, action: str = None, *, reason: str = "بدون سبب"):
    lang = get_lang(ctx.guild)
    if action is None or action.lower() not in ["on", "off"]:
        msg = "❌ الاستخدام: `!maintenance on [سبب]` أو `!maintenance off`" if lang == "ar" else "❌ Usage: `!maintenance on [reason]` or `!maintenance off`"
        return await ctx.send(msg)

    is_on = action.lower() == "on"
    maintenance_state[ctx.guild.id] = {"on": is_on, "reason": reason}
    await save_maintenance_state()
    await update_status_channel(ctx.guild, "maintenance" if is_on else "online")

    channel_id = status_channel_config.get(ctx.guild.id)
    channel = ctx.guild.get_channel(channel_id) if channel_id else None

    if is_on:
        title = "🟡 البوت دخل وضع الصيانة" if lang == "ar" else "🟡 Bot entered maintenance mode"
        desc = f"**السبب:** {reason}" if lang == "ar" else f"**Reason:** {reason}"
        color = discord.Color.gold()
    else:
        title = "🟢 البوت رجع يشتغل بكامل قدراته" if lang == "ar" else "🟢 Bot is back online"
        desc = "شكراً لصبركم! 🌌" if lang == "ar" else "Thanks for your patience! 🌌"
        color = discord.Color.green()

    embed = discord.Embed(title=title, description=desc, color=color)
    sent_to_status_channel = False
    if channel:
        try:
            await channel.send(embed=embed)
            sent_to_status_channel = True
        except discord.Forbidden:
            pass

    if not sent_to_status_channel or ctx.channel.id != channel.id:
        await ctx.send(embed=embed)


@bot.command(aliases=["مدة_التشغيل"])
async def uptime(ctx):
    lang = get_lang(ctx.guild)
    elapsed = int(time.time() - bot_start_time)
    days, rem = divmod(elapsed, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)

    if lang == "ar":
        parts = []
        if days: parts.append(f"{days} يوم")
        if hours: parts.append(f"{hours} ساعة")
        parts.append(f"{minutes} دقيقة")
        msg = f"🟢 البوت شغال من: **{' و '.join(parts)}**"
    else:
        parts = []
        if days: parts.append(f"{days}d")
        if hours: parts.append(f"{hours}h")
        parts.append(f"{minutes}m")
        msg = f"🟢 Bot has been online for: **{' '.join(parts)}**"
    await ctx.send(msg)


# ============================================================
#  📝 صندوق الحفظ الشخصي (Personal Notes / Vault)
#  متاح لأي عضو، بيانات خاصة بيه بس، عالمية عبر كل السيرفرات
# ============================================================
user_notes = {}  # user_id -> [note1, note2, ...]


def save_user_notes():
    return storage_save("user_notes", {str(k): v for k, v in user_notes.items()})


@bot.group(name="note", aliases=["ملاحظة", "n"], invoke_without_command=True)
async def note(ctx):
    lang = get_lang(ctx.guild)
    msg = (
        "❌ الاستخدام: `!note save <النص>` أو `!note list` أو `!note delete <رقم>`"
        if lang == "ar" else
        "❌ Usage: `!note save <text>` / `!note list` / `!note delete <number>`"
    )
    await ctx.send(msg)


@note.command(name="save", aliases=["حفظ"])
async def note_save(ctx, *, text: str = None):
    lang = get_lang(ctx.guild)
    if not text:
        msg = "❌ اكتب نص الملاحظة بعد الأمر." if lang == "ar" else "❌ Write the note's text after the command."
        return await ctx.send(msg)

    notes = user_notes.setdefault(ctx.author.id, [])
    if len(notes) >= 20:
        msg = "❌ وصلت للحد الأقصى (20 ملاحظة). امسح واحدة قبل ما تضيف جديدة." if lang == "ar" else "❌ You've hit the limit (20 notes). Delete one before adding a new one."
        return await ctx.send(msg)

    if len(text) > 500:
        text = text[:500]

    notes.append(text)
    await save_user_notes()

    msg = f"✅ تم الحفظ! (رقمها {len(notes)}). شوف كل ملاحظاتك بـ `!note list`" if lang == "ar" else f"✅ Saved! (item #{len(notes)}). View all your notes with `!note list`"
    await ctx.send(msg)


@note.command(name="list", aliases=["عرض"])
async def note_list(ctx):
    lang = get_lang(ctx.guild)
    notes = user_notes.get(ctx.author.id, [])

    if not notes:
        msg = "📭 مفيش ملاحظات محفوظة عندك لسه. جرب `!note save <النص>`" if lang == "ar" else "📭 You don't have any saved notes yet. Try `!note save <text>`"
        return await ctx.send(msg)

    title = f"📝 ملاحظاتك ({len(notes)})" if lang == "ar" else f"📝 Your Notes ({len(notes)})"
    embed = discord.Embed(title=title, color=discord.Color.blurple())
    lines = [f"**#{i+1}** — {t}" for i, t in enumerate(notes)]
    embed.description = "\n".join(lines)[:4000]
    await ctx.send(embed=embed)


@note.command(name="delete", aliases=["مسح", "del"])
async def note_delete(ctx, number: int = None):
    lang = get_lang(ctx.guild)
    notes = user_notes.get(ctx.author.id, [])

    if number is None or number < 1 or number > len(notes):
        msg = "❌ حدد رقم صحيح من `!note list`." if lang == "ar" else "❌ Specify a valid number from `!note list`."
        return await ctx.send(msg)

    removed = notes.pop(number - 1)
    await save_user_notes()
    msg = f"🗑️ اتمسحت: \"{removed[:50]}\"" if lang == "ar" else f"🗑️ Deleted: \"{removed[:50]}\""
    await ctx.send(msg)


# ============================================================
#  5.5 نظام السجلات الإدارية (Mod-Log)
# ============================================================
modlog_config = {}


def save_modlog():
    return storage_save("modlog", {str(k): v for k, v in modlog_config.items()})


async def send_modlog(guild: discord.Guild, title: str, description: str, color=discord.Color.dark_red()):
    channel_id = modlog_config.get(guild.id)
    if not channel_id:
        return
    channel = guild.get_channel(channel_id)
    if not channel:
        return
    embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.datetime.now())
    try:
        await channel.send(embed=embed)
    except discord.Forbidden:
        pass


@bot.command(aliases=["سجل_الإدارة"])
@commands.has_permissions(administrator=True)
async def setmodlog(ctx, channel: discord.TextChannel = None):
    lang = get_lang(ctx.guild)
    if channel is None:
        if ctx.guild.id in modlog_config:
            del modlog_config[ctx.guild.id]
            await save_modlog()
        msg = "✅ تم إيقاف سجل الإدارة." if lang == "ar" else "✅ Mod-log disabled."
        return await ctx.send(msg)
    modlog_config[ctx.guild.id] = channel.id
    await save_modlog()
    msg = f"✅ سجل الإدارة هيتسجل في {channel.mention} (كيك، بان، تحذيرات).​" if lang == "ar" else f"✅ Moderation actions (kicks, bans, warnings) will now be logged in {channel.mention}."
    await ctx.send(msg)


# ============================================================
#  5.6 نظام الجيف أواي (Giveaways) - ميزة "برو"
# ============================================================
active_giveaways = {}  # message_id -> data


def save_giveaways():
    return storage_save("giveaways", {str(k): v for k, v in active_giveaways.items()})


# (نظام الملاحظات الشخصية موجود فوق بالفعل كـ !note group - مبني بـ bot.group)


# ============================================================
#  5.7 نظام البريميوم (Personal & Server Premium)
#  التفعيل يدوي من المالك دلوقتي (مفيش بوابة دفع لسه) -
#  لما توصل وسيلة دفع، ممكن نأتمت !grantpremium نفسه بس
#  باقي النظام (البادچ، المضاعفة، الهدية، التذكير) هيفضل زي ما هو
#  (premium_users و premium_servers و get_dynamic_prefix متعرّفين فوق
#  الملف عشان بريفكس البوت محتاجهم وقت الإنشاء)
# ============================================================
premium_reminder_sent = set()  # user_ids اتبعتلهم تذكير الانتهاء عشان ما نكررش


def save_premium_users():
    return storage_save("premium_users", {str(k): v for k, v in premium_users.items()})


def save_premium_servers():
    return storage_save("premium_servers", {str(k): v for k, v in premium_servers.items()})


def is_premium_active(user_id: int) -> bool:
    data = premium_users.get(user_id)
    return bool(data and data.get("expires", 0) > time.time())


def is_server_premium_active(guild_id: int) -> bool:
    data = premium_servers.get(guild_id)
    return bool(data and data.get("expires", 0) > time.time())


@tasks.loop(hours=6)
async def check_premium_expiry():
    now = time.time()
    for user_id, data in list(premium_users.items()):
        expires = data.get("expires", 0)
        if expires <= now:
            continue
        remaining = expires - now
        if remaining <= 3 * 86400 and user_id not in premium_reminder_sent:
            user = bot.get_user(user_id)
            if user:
                try:
                    days_left = max(1, int(remaining // 86400))
                    msg = f"⏳ اشتراكك في Cosmic Galaxy Premium 💎 هينتهي بعد **{days_left} يوم**. جدد عشان تفضل مستفيد من كل المميزات!"
                    await user.send(msg)
                except discord.Forbidden:
                    pass
            premium_reminder_sent.add(user_id)


def _grant_premium(user_id: int, days: int, is_gift: bool = False):
    now = time.time()
    existing = premium_users.get(user_id, {})
    base = max(existing.get("expires", 0), now)
    new_expiry = base + days * 86400
    # الهدية ما تسجلش "كان مشترك قبل كده" - البادچ الباهت للمشتركين الحقيقيين بس
    was_ever = existing.get("was_premium_ever", False) or (not is_gift)
    premium_users[user_id] = {
        "expires": new_expiry,
        "is_gift": is_gift,
        "was_premium_ever": was_ever,
        "first_subscribed": existing.get("first_subscribed", now) if was_ever else existing.get("first_subscribed"),
        "embed_color": existing.get("embed_color"),
        "custom_title": existing.get("custom_title"),
    }
    premium_reminder_sent.discard(user_id)
    return new_expiry


@bot.command(aliases=["منح_بريميوم"])
@commands.is_owner()
async def grantpremium(ctx, member: discord.User = None, days: int = None):
    lang = get_lang(ctx.guild)
    if member is None or days is None or days <= 0:
        msg = "❌ الاستخدام: `!grantpremium @user <عدد_الأيام>`" if lang == "ar" else "❌ Usage: `!grantpremium @user <days>`"
        return await ctx.send(msg)
    new_expiry = _grant_premium(member.id, days, is_gift=False)
    await save_premium_users()
    date_str = datetime.datetime.fromtimestamp(new_expiry).strftime("%Y-%m-%d")
    msg = f"✅ تم تفعيل بريميوم لـ **{member}** لحد **{date_str}**." if lang == "ar" else f"✅ Premium activated for **{member}** until **{date_str}**."
    await ctx.send(msg)
    try:
        dm = f"🎉 مبروك! تم تفعيل اشتراكك في Cosmic Galaxy Premium 💎 لحد **{date_str}**. اكتب `!premiumcheck` عشان تشوف كل مميزاتك!"
        await member.send(dm)
    except discord.Forbidden:
        pass


@bot.command(aliases=["سحب_بريميوم"])
@commands.is_owner()
async def revokepremium(ctx, member: discord.User = None):
    lang = get_lang(ctx.guild)
    if member is None:
        msg = "❌ الاستخدام: `!revokepremium @user`" if lang == "ar" else "❌ Usage: `!revokepremium @user`"
        return await ctx.send(msg)
    if member.id in premium_users:
        premium_users[member.id]["expires"] = 0
        await save_premium_users()
    msg = f"✅ تم إلغاء بريميوم **{member}**." if lang == "ar" else f"✅ Revoked premium for **{member}**."
    await ctx.send(msg)


@bot.command(aliases=["بريميوم_سيرفر"])
@commands.is_owner()
async def serverpremium(ctx, guild_id: int = None, days: int = None):
    lang = get_lang(ctx.guild)
    if guild_id is None or days is None or days <= 0:
        msg = "❌ الاستخدام: `!serverpremium <آيدي_السيرفر> <عدد_الأيام>`" if lang == "ar" else "❌ Usage: `!serverpremium <guild_id> <days>`"
        return await ctx.send(msg)
    now = time.time()
    existing = premium_servers.get(guild_id, {})
    base = max(existing.get("expires", 0), now)
    new_expiry = base + days * 86400
    premium_servers[guild_id] = {"expires": new_expiry, "prefix": existing.get("prefix")}
    await save_premium_servers()
    date_str = datetime.datetime.fromtimestamp(new_expiry).strftime("%Y-%m-%d")
    msg = f"✅ تم تفعيل بريميوم السيرفر (`{guild_id}`) لحد **{date_str}**." if lang == "ar" else f"✅ Server premium activated (`{guild_id}`) until **{date_str}**."
    await ctx.send(msg)


@bot.command(aliases=["سحب_بريميوم_سيرفر"])
@commands.is_owner()
async def revokeserverpremium(ctx, guild_id: int = None):
    lang = get_lang(ctx.guild)
    if guild_id is None:
        msg = "❌ الاستخدام: `!revokeserverpremium <آيدي_السيرفر>`" if lang == "ar" else "❌ Usage: `!revokeserverpremium <guild_id>`"
        return await ctx.send(msg)
    if guild_id in premium_servers:
        premium_servers[guild_id]["expires"] = 0
        await save_premium_servers()
    msg = "✅ تم إلغاء بريميوم السيرفر." if lang == "ar" else "✅ Server premium revoked."
    await ctx.send(msg)


class PremiumSubscribeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.button(label="💎 اشترك دلوقتي / Subscribe Now", style=discord.ButtonStyle.green)
    async def subscribe(self, interaction: discord.Interaction, button: discord.ui.Button):
        lang = get_lang(interaction.guild)
        if interaction.guild is None or interaction.guild.id != HOME_GUILD_ID:
            msg = "❌ الاشتراك متاح بس من سيرفر الدعم الرسمي." if lang == "ar" else "❌ Subscribing is only available on the official support server."
            return await interaction.response.send_message(msg, ephemeral=True)
        modal = TicketReasonModal("premium_personal", lang)
        await interaction.response.send_modal(modal)


@bot.command(aliases=["فحص_بريميوم"])
async def premiumcheck(ctx, member: discord.Member = None):
    target = member or ctx.author
    lang = get_lang(ctx.guild)

    if is_premium_active(target.id):
        data = premium_users[target.id]
        remaining = data["expires"] - time.time()
        days = int(remaining // 86400)
        hours = int((remaining % 86400) // 3600)
        if lang == "ar":
            msg = f"💎 **{target.display_name}** مشترك في Premium ✅\n⏳ باقي: **{days} يوم و {hours} ساعة** على انتهاء الاشتراك."
        else:
            msg = f"💎 **{target.display_name}** is Premium ✅\n⏳ Time left: **{days}d {hours}h** until expiry."
        return await ctx.send(msg)

    if lang == "ar":
        desc = f"❌ **{target.display_name}** مش مشترك في Cosmic Galaxy Premium حالياً.\n\n💎 اشترك واستمتع بـ: بادچ مميز، daily مضاعف، رومر حصري، ومميزات تانية!"
    else:
        desc = f"❌ **{target.display_name}** isn't subscribed to Cosmic Galaxy Premium.\n\n💎 Subscribe and get: a premium badge, doubled daily rewards, an exclusive channel, and more!"

    if target.id == ctx.author.id:
        await ctx.send(desc, view=PremiumSubscribeView())
    else:
        await ctx.send(desc)


@bot.command(name="premium", aliases=["بريميوم"])
async def premium_info(ctx):
    lang = get_lang(ctx.guild)

    if lang == "ar":
        summary = "💎 **Cosmic Galaxy Premium** — بعتلك التفاصيل كاملة في الخاص!"
        dm_embed = discord.Embed(title="💎 Cosmic Galaxy Premium", color=discord.Color.gold())
        dm_embed.add_field(
            name="👤 الاشتراك الشخصي",
            value=(
                "💎 بادچ مميز في كل مكان (البروفايل، لوحة المتصدرين، الترحيب)\n"
                "⚡ مضاعفة مكافأة الـ`daily` (×2)\n"
                "🎨 لون مخصص لرسايلك\n"
                "🏷️ لقب مخصص جنب اسمك\n"
                "🚀 وصول مبكر لأي ميزة جديدة\n"
                "📣 منشن فوري لما تفتح تذكرة\n"
                "🎁 هدية شهرية تقدر تديها لصديق (أسبوع تجربة)\n"
                "🏆 عداد ولاء يوضح من إمتى إنت مشترك"
            ),
            inline=False,
        )
        dm_embed.add_field(
            name="🏛️ اشتراك السيرفر (أغلى، لفايدة كل الأعضاء)",
            value="بريفكس مخصص لسيرفرك، ومميزات إدارية إضافية بتتوسع مع الوقت.",
            inline=False,
        )
        dm_embed.set_footer(text="اضغط الزرار المناسب تحت عشان تفتح تذكرة اشتراك")
    else:
        summary = "💎 **Cosmic Galaxy Premium** — Sent you the full details in DMs!"
        dm_embed = discord.Embed(title="💎 Cosmic Galaxy Premium", color=discord.Color.gold())
        dm_embed.add_field(
            name="👤 Personal Subscription",
            value=(
                "💎 A premium badge everywhere (profile, leaderboard, welcome)\n"
                "⚡ Doubled `daily` reward (×2)\n"
                "🎨 A custom color for your messages\n"
                "🏷️ A custom title next to your name\n"
                "🚀 Early access to new features\n"
                "📣 Instant mention when you open a ticket\n"
                "🎁 A monthly gift you can give a friend (1-week trial)\n"
                "🏆 A loyalty counter showing how long you've been subscribed"
            ),
            inline=False,
        )
        dm_embed.add_field(
            name="🏛️ Server Subscription (pricier, benefits the whole server)",
            value="A custom prefix for your server, plus admin features that keep expanding.",
            inline=False,
        )
        dm_embed.set_footer(text="Press the matching button below to open a subscription ticket")

    class PremiumInfoView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=180)

        @discord.ui.button(label="💎 اشتراك شخصي / Personal", style=discord.ButtonStyle.green)
        async def personal(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.guild is None or interaction.guild.id != HOME_GUILD_ID:
                msg = "❌ متاح بس من سيرفر الدعم الرسمي." if lang == "ar" else "❌ Only available on the official support server."
                return await interaction.response.send_message(msg, ephemeral=True)
            await interaction.response.send_modal(TicketReasonModal("premium_personal", lang))

        @discord.ui.button(label="🏛️ اشتراك سيرفر / Server", style=discord.ButtonStyle.blurple)
        async def server(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.guild is None or interaction.guild.id != HOME_GUILD_ID:
                msg = "❌ متاح بس من سيرفر الدعم الرسمي." if lang == "ar" else "❌ Only available on the official support server."
                return await interaction.response.send_message(msg, ephemeral=True)
            await interaction.response.send_modal(TicketReasonModal("premium_server", lang))

    await ctx.send(summary)
    try:
        await ctx.author.send(embed=dm_embed, view=PremiumInfoView())
    except discord.Forbidden:
        await ctx.send(embed=dm_embed, view=PremiumInfoView())


@bot.command(aliases=["اعدادات_بريميوم"])
async def premiumsettings(ctx, setting: str = None, *, value: str = None):
    lang = get_lang(ctx.guild)
    if not is_premium_active(ctx.author.id):
        msg = "❌ الميزة دي لمشتركي Premium بس. اكتب `!premium` عشان تعرف أكتر." if lang == "ar" else "❌ This is a Premium-only feature. Type `!premium` to learn more."
        return await ctx.send(msg)

    if setting is None or setting.lower() not in ["color", "title", "لون", "لقب"]:
        msg = "❌ الاستخدام: `!premiumsettings color <#hex>` أو `!premiumsettings title <النص>`" if lang == "ar" else "❌ Usage: `!premiumsettings color <#hex>` or `!premiumsettings title <text>`"
        return await ctx.send(msg)

    setting = {"لون": "color", "لقب": "title"}.get(setting.lower(), setting.lower())
    data = premium_users[ctx.author.id]

    if setting == "color":
        if not value or not value.strip().lstrip("#"):
            msg = "❌ اكتب كود لون hex زي `#8B6EF2`." if lang == "ar" else "❌ Provide a hex color code like `#8B6EF2`."
            return await ctx.send(msg)
        try:
            int(value.strip().lstrip("#"), 16)
        except ValueError:
            msg = "❌ كود اللون غير صحيح." if lang == "ar" else "❌ Invalid color code."
            return await ctx.send(msg)
        data["embed_color"] = value.strip().lstrip("#")
        await save_premium_users()
        msg = "✅ اتغير لون رسايلك الشخصية." if lang == "ar" else "✅ Your personal message color was updated."
        return await ctx.send(msg)

    if setting == "title":
        if not value:
            data["custom_title"] = None
            await save_premium_users()
            msg = "✅ تم إلغاء اللقب." if lang == "ar" else "✅ Title removed."
            return await ctx.send(msg)
        if len(value) > 30:
            msg = "❌ اللقب طويل أوي (حد أقصى 30 حرف)." if lang == "ar" else "❌ Title is too long (30 characters max)."
            return await ctx.send(msg)
        data["custom_title"] = value
        await save_premium_users()
        msg = f"✅ لقبك الجديد: **{value}**" if lang == "ar" else f"✅ Your new title: **{value}**"
        return await ctx.send(msg)


@bot.command(aliases=["هدية_بريميوم"])
async def premiumgift(ctx, member: discord.Member = None):
    lang = get_lang(ctx.guild)
    if not is_premium_active(ctx.author.id) or premium_users[ctx.author.id].get("is_gift"):
        msg = "❌ الميزة دي لمشتركي Premium الأساسيين بس (مش الهدايا)." if lang == "ar" else "❌ Only original Premium subscribers can gift (not gifted accounts)."
        return await ctx.send(msg)

    if member is None:
        msg = "❌ الاستخدام: `!premiumgift @user`" if lang == "ar" else "❌ Usage: `!premiumgift @user`"
        return await ctx.send(msg)

    if member.id == ctx.author.id:
        msg = "❌ مينفعش تهدي نفسك." if lang == "ar" else "❌ You can't gift yourself."
        return await ctx.send(msg)

    if member.bot:
        msg = "❌ مينفعش تهدي بوت." if lang == "ar" else "❌ You can't gift a bot."
        return await ctx.send(msg)

    if is_premium_active(member.id):
        msg = "❌ العضو ده مشترك بالفعل." if lang == "ar" else "❌ That member is already premium."
        return await ctx.send(msg)

    if getattr(member, "joined_at", None):
        member_age = time.time() - member.joined_at.timestamp()
        if member_age < 86400:
            msg = "❌ العضو ده جديد جداً في السيرفر، جرب بعد شوية." if lang == "ar" else "❌ That member is too new to this server, try again later."
            return await ctx.send(msg)

    _grant_premium(member.id, 7, is_gift=True)
    await save_premium_users()

    msg = f"🎁 تم إهداء أسبوع Premium لـ {member.mention}!" if lang == "ar" else f"🎁 Gifted a week of Premium to {member.mention}!"
    await ctx.send(msg)
    try:
        dm = f"🎁 {ctx.author} أهداك أسبوع من Cosmic Galaxy Premium 💎! جرب المميزات واشترك بنفسك لو عجبتك بـ `!premium`." if lang == "ar" else f"🎁 {ctx.author} gifted you a week of Cosmic Galaxy Premium 💎! Try the features and subscribe yourself with `!premium` if you like them."
        await member.send(dm)
    except discord.Forbidden:
        pass


@bot.command(aliases=["بريفكس_مخصص"])
@commands.has_permissions(administrator=True)
async def setprefix(ctx, new_prefix: str = None):
    lang = get_lang(ctx.guild)
    if not is_server_premium_active(ctx.guild.id):
        msg = "❌ البريفكس المخصص ميزة بريميوم السيرفر. اكتب `!premium` عشان تعرف أكتر." if lang == "ar" else "❌ Custom prefix is a Server Premium feature. Type `!premium` to learn more."
        return await ctx.send(msg)
    if not new_prefix or len(new_prefix) > 3:
        msg = "❌ اختر بريفكس قصير (حرف لـ 3 حروف كحد أقصى)." if lang == "ar" else "❌ Choose a short prefix (1-3 characters)."
        return await ctx.send(msg)
    premium_servers[ctx.guild.id]["prefix"] = new_prefix
    await save_premium_servers()
    msg = f"✅ بريفكس السيرفر بقى `{new_prefix}`." if lang == "ar" else f"✅ Server prefix is now `{new_prefix}`."
    await ctx.send(msg)


async def load_all_data():
    """يحمّل كل بيانات البوت من MongoDB (أو JSON محلي لو مفيش MONGO_URI) لحظة التشغيل."""
    global server_langs, user_galaxies, user_last_daily, user_warns, ticket_config
    global welcome_config, leave_config, autorole_config, user_stardust, blacklist_data, known_users
    global ticket_counters, active_tickets, modlog_config, active_giveaways, user_notes
    global status_channel_config, maintenance_state, shop_items
    global premium_users, premium_servers

    server_langs = {int(k): v for k, v in (await storage_load("langs", {})).items()}
    user_galaxies = {int(k): v for k, v in (await storage_load("galaxies", {})).items()}
    user_last_daily = {int(k): v for k, v in (await storage_load("daily", {})).items()}
    user_warns = {int(k): v for k, v in (await storage_load("warns", {})).items()}
    ticket_config = {int(k): v for k, v in (await storage_load("tickets", {})).items()}
    welcome_config = {int(k): v for k, v in (await storage_load("welcome", {})).items()}
    leave_config = {int(k): v for k, v in (await storage_load("leave", {})).items()}
    autorole_config = {int(k): v for k, v in (await storage_load("autorole", {})).items()}

    raw_stardust = await storage_load("stardust", {})
    user_stardust = {int(gk): {int(uk): v for uk, v in uv.items()} for gk, uv in raw_stardust.items()}

    blacklist_data = {int(k): v for k, v in (await storage_load("blacklist", {})).items()}
    known_users = {int(k): v for k, v in (await storage_load("known_users", {})).items()}
    ticket_counters = {int(k): v for k, v in (await storage_load("ticket_counter", {})).items()}
    active_tickets = {int(k): v for k, v in (await storage_load("active_tickets", {})).items()}
    modlog_config = {int(k): v for k, v in (await storage_load("modlog", {})).items()}
    active_giveaways = {int(k): v for k, v in (await storage_load("giveaways", {})).items()}
    user_notes = {int(k): v for k, v in (await storage_load("user_notes", {})).items()}
    status_channel_config = {int(k): v for k, v in (await storage_load("status_channel", {})).items()}
    maintenance_state = {int(k): v for k, v in (await storage_load("maintenance_state", {})).items()}

    raw_shop = await storage_load("shop", {})
    shop_items = {int(gk): iv for gk, iv in raw_shop.items()}

    premium_users = {int(k): v for k, v in (await storage_load("premium_users", {})).items()}
    premium_servers = {int(k): v for k, v in (await storage_load("premium_servers", {})).items()}

    backend = "MongoDB" if USE_MONGO else "local JSON files"
    print(f"✅ Data loaded from {backend} ({len(known_users)} known users, {len(user_galaxies)} galaxy wallets).")


def parse_duration(text: str):
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    try:
        unit = text[-1].lower()
        if unit not in units:
            return None
        value = int(text[:-1])
        if value <= 0:
            return None
        return value * units[unit]
    except (ValueError, IndexError):
        return None


class GiveawayJoinView(discord.ui.View):
    def __init__(self, message_id: int):
        super().__init__(timeout=None)
        self.message_id = message_id
        self.join_button.custom_id = f"giveaway_join_{message_id}"

    @discord.ui.button(label="🎉 Join / اشترك", style=discord.ButtonStyle.green)
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        lang = get_lang(interaction.guild)
        data = active_giveaways.get(self.message_id)
        if not data or data.get("ended"):
            msg = "❌ الجيف أواي ده خلص." if lang == "ar" else "❌ This giveaway has ended."
            return await interaction.response.send_message(msg, ephemeral=True)

        if interaction.user.id in data["participants"]:
            data["participants"].remove(interaction.user.id)
            await save_giveaways()
            msg = "❎ تم إلغاء اشتراكك." if lang == "ar" else "❎ You left the giveaway."
        else:
            data["participants"].append(interaction.user.id)
            await save_giveaways()
            msg = "✅ تم تسجيل اشتراكك! بالتوفيق 🍀" if lang == "ar" else "✅ You're in! Good luck 🍀"
        await interaction.response.send_message(msg, ephemeral=True)


@tasks.loop(seconds=30)
async def check_giveaways():
    now = time.time()
    for message_id, data in list(active_giveaways.items()):
        if data.get("ended") or data["end_time"] > now:
            continue
        await end_giveaway(message_id)


async def end_giveaway(message_id: int):
    data = active_giveaways.get(message_id)
    if not data or data.get("ended"):
        return
    data["ended"] = True
    await save_giveaways()

    guild = bot.get_guild(data["guild_id"])
    if not guild:
        return
    channel = guild.get_channel(data["channel_id"])
    if not channel:
        return
    try:
        message = await channel.fetch_message(message_id)
    except discord.NotFound:
        return

    participants = data["participants"]
    winners_count = min(data["winners_count"], len(participants))

    if winners_count == 0:
        result_text = "😢 محدش اشترك، مافيش فايزين." if get_lang(guild) == "ar" else "😢 No one joined, no winners."
    else:
        winner_ids = random.sample(participants, winners_count)
        mentions = ", ".join(f"<@{uid}>" for uid in winner_ids)
        result_text = f"🎉 مبروك {mentions}! فزتوا بـ **{data['prize']}**" if get_lang(guild) == "ar" else f"🎉 Congrats {mentions}! You won **{data['prize']}**"

    embed = discord.Embed(title=f"🎉 الجيف أواي خلص! / Giveaway Ended!", description=f"**{data['prize']}**\n\n{result_text}", color=discord.Color.gold())
    try:
        await message.edit(embed=embed, view=None)
        await channel.send(result_text)
    except discord.Forbidden:
        pass


@bot.command(aliases=["جيف", "gstart"])
@commands.has_permissions(administrator=True)
async def giveaway(ctx, duration: str = None, winners_count: int = None, *, prize: str = None):
    lang = get_lang(ctx.guild)
    if not duration or not winners_count or not prize:
        msg = "❌ الاستخدام: `!giveaway <مدة مثل 10m/1h/1d> <عدد_الفايزين> <الجائزة>`" if lang == "ar" else "❌ Usage: `!giveaway <duration e.g. 10m/1h/1d> <winners_count> <prize>`"
        return await ctx.send(msg)

    seconds = parse_duration(duration)
    if seconds is None:
        msg = "❌ صيغة المدة غلط. استخدم s/m/h/d زي `30m` أو `2h`." if lang == "ar" else "❌ Invalid duration format. Use s/m/h/d like `30m` or `2h`."
        return await ctx.send(msg)

    if winners_count < 1 or winners_count > 20:
        msg = "❌ عدد الفايزين لازم يكون بين 1 و 20." if lang == "ar" else "❌ Winners count must be between 1 and 20."
        return await ctx.send(msg)

    end_time = time.time() + seconds
    title = "🎉 جيف أواي جديد!" if lang == "ar" else "🎉 New Giveaway!"
    desc = (
        f"**الجائزة:** {prize}\n**عدد الفايزين:** {winners_count}\n"
        f"**بينتهي:** <t:{int(end_time)}:R>\n\nاضغط الزر تحت عشان تشترك!"
        if lang == "ar" else
        f"**Prize:** {prize}\n**Winners:** {winners_count}\n"
        f"**Ends:** <t:{int(end_time)}:R>\n\nClick the button below to join!"
    )
    embed = discord.Embed(title=title, description=desc, color=discord.Color.magenta())
    embed.set_footer(text=f"Hosted by {ctx.author.display_name}")

    temp_view = discord.ui.View(timeout=None)
    message = await ctx.send(embed=embed, view=temp_view)

    active_giveaways[message.id] = {
        "guild_id": ctx.guild.id,
        "channel_id": ctx.channel.id,
        "prize": prize,
        "winners_count": winners_count,
        "end_time": end_time,
        "participants": [],
        "ended": False,
    }
    await save_giveaways()

    real_view = GiveawayJoinView(message.id)
    bot.add_view(real_view, message_id=message.id)
    await message.edit(view=real_view)


@bot.command(aliases=["جيف_انهاء", "gend"])
@commands.has_permissions(administrator=True)
async def gawend(ctx, message_id: int = None):
    lang = get_lang(ctx.guild)
    if message_id is None or message_id not in active_giveaways:
        msg = "❌ حدد آيدي رسالة جيف أواي شغال." if lang == "ar" else "❌ Specify a valid running giveaway's message ID."
        return await ctx.send(msg)
    await end_giveaway(message_id)
    msg = "✅ تم إنهاء الجيف أواي." if lang == "ar" else "✅ Giveaway ended."
    await ctx.send(msg)


# ============================================================
#  5.7 نظام الغياب (AFK)
# ============================================================
afk_data = {}  # user_id -> {"reason":, "since":} - في الذاكرة، حالة مؤقتة بطبيعتها


@bot.command(aliases=["غياب"])
async def afk(ctx, *, reason: str = "بدون سبب"):
    lang = get_lang(ctx.guild)
    afk_data[ctx.author.id] = {"reason": reason, "since": time.time()}
    msg = f"😴 تم تفعيل وضع الغياب. السبب: {reason}" if lang == "ar" else f"😴 You're now AFK. Reason: {reason}"
    await ctx.send(msg)


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        await bot.process_commands(message)
        return

    lang = get_lang(message.guild)

    if message.author.id in afk_data:
        del afk_data[message.author.id]
        try:
            welcome_back = "🌟 أهلاً بعودتك! تم إلغاء وضع الغياب." if lang == "ar" else "🌟 Welcome back! Your AFK status was removed."
            await message.channel.send(f"{message.author.mention} {welcome_back}", delete_after=6)
        except discord.Forbidden:
            pass

    if message.mentions:
        afk_mentions = [m for m in message.mentions if m.id in afk_data]
        for m in afk_mentions:
            info = afk_data[m.id]
            elapsed = int(time.time() - info["since"])
            minutes = elapsed // 60
            note = f"⏳ {m.display_name} غايب دلوقتي ({minutes} دقيقة). السبب: {info['reason']}" if lang == "ar" else f"⏳ {m.display_name} is AFK right now ({minutes}m). Reason: {info['reason']}"
            try:
                await message.channel.send(note, delete_after=8)
            except discord.Forbidden:
                pass

    await bot.process_commands(message)


# ============================================================
#  6. أوامر المالك (Owner)
# ============================================================
@bot.command()
@commands.is_owner()
async def setname(ctx, *, new_name: str):
    await bot.user.edit(username=new_name)
    await ctx.send(f"✅ تم تغيير اسم البوت إلى: **{new_name}**")


@bot.command()
@commands.is_owner()
async def setavatar(ctx, url: str = None):
    if ctx.message.attachments:
        url = ctx.message.attachments[0].url
    if not url:
        return await ctx.send("❌ يرجى إرفاق صورة أو وضع رابط الصورة.")
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.read()
                await bot.user.edit(avatar=data)
                await ctx.send("✅ تم تغيير صورة البوت بنجاح!")
            else:
                await ctx.send("❌ لم أستطع تحميل الصورة من الرابط.")


@bot.command()
@commands.is_owner()
async def setstatus(ctx, *, status_text: str):
    await bot.change_presence(activity=discord.Game(name=status_text))
    await ctx.send(f"✅ تم تغيير حالة البوت إلى: **{status_text}**")


# ============================================================
#  7. أوامر التحكم العالمي (مالك البوت فقط) - المستخدمين، الحظر، السيرفرات
# ============================================================
@bot.command(aliases=["حظر_بوت"])
@commands.is_owner()
async def blacklist(ctx, action: str = None, member: discord.User = None, *, reason: str = "بدون سبب"):
    lang = get_lang(ctx.guild)
    if action is None:
        msg = "❌ الاستخدام: `!blacklist add @user [سبب]` أو `!blacklist remove @user` أو `!blacklist list`" if lang == "ar" else "❌ Usage: `!blacklist add @user [reason]` / `!blacklist remove @user` / `!blacklist list`"
        return await ctx.send(msg)

    action = action.lower()

    if action == "list":
        if not blacklist_data:
            msg = "✅ لا يوجد أي عضو محظور من البوت." if lang == "ar" else "✅ No one is blacklisted."
            return await ctx.send(msg)
        title = "🚫 المحظورين من استخدام البوت" if lang == "ar" else "🚫 Blacklisted Users"
        embed = discord.Embed(title=title, color=discord.Color.dark_red())
        lines = [f"`{uid}` — {r}" for uid, r in list(blacklist_data.items())[:40]]
        embed.description = "\n".join(lines)
        return await ctx.send(embed=embed)

    if member is None:
        msg = "❌ حدد العضو (منشن أو آيدي)." if lang == "ar" else "❌ Specify a member (mention or ID)."
        return await ctx.send(msg)

    if action == "add":
        if await bot.is_owner(member):
            msg = "❌ ما تقدر تحظر مالك البوت." if lang == "ar" else "❌ You can't blacklist the bot owner."
            return await ctx.send(msg)
        blacklist_data[member.id] = reason
        await save_blacklist()
        msg = f"🚫 تم حظر **{member}** من استخدام البوت في كل السيرفرات. السبب: {reason}" if lang == "ar" else f"🚫 **{member}** is now blacklisted from the bot everywhere. Reason: {reason}"
        return await ctx.send(msg)

    if action == "remove":
        if member.id in blacklist_data:
            del blacklist_data[member.id]
            await save_blacklist()
            msg = f"✅ تم رفع الحظر عن **{member}**." if lang == "ar" else f"✅ **{member}** was removed from the blacklist."
            return await ctx.send(msg)
        msg = "❌ هذا العضو غير محظور أصلاً." if lang == "ar" else "❌ This user isn't blacklisted."
        return await ctx.send(msg)

    msg = "❌ استخدم `add` أو `remove` أو `list`." if lang == "ar" else "❌ Use `add`, `remove`, or `list`."
    await ctx.send(msg)


@bot.command(aliases=["مستخدمين_البوت", "allusers"])
@commands.is_owner()
async def botusers(ctx):
    lang = get_lang(ctx.guild)
    if not known_users:
        msg = "لا يوجد بيانات مستخدمين مسجلة بعد." if lang == "ar" else "No user data recorded yet."
        return await ctx.send(msg)

    sorted_users = sorted(known_users.items(), key=lambda x: x[1]["last_seen"], reverse=True)
    chunk_size = 15
    pages = []
    for i in range(0, len(sorted_users), chunk_size):
        chunk = sorted_users[i:i + chunk_size]
        title = f"👥 مستخدمي البوت ({len(known_users)} إجمالي)" if lang == "ar" else f"👥 Bot Users ({len(known_users)} total)"
        embed = discord.Embed(title=title, color=discord.Color.blue())
        lines = []
        for uid, info in chunk:
            tag = " 🚫" if uid in blacklist_data else ""
            lines.append(f"`{uid}` — {info['name']}{tag}")
        embed.description = "\n".join(lines)
        pages.append(embed)

    view = HelpPaginator(ctx, pages, lang)
    await ctx.send(embed=pages[0], view=view)


@bot.command(aliases=["السيرفرات", "guilds"])
@commands.is_owner()
async def servers(ctx):
    lang = get_lang(ctx.guild)
    guild_list = bot.guilds
    if not guild_list:
        msg = "البوت مو موجود بأي سيرفر." if lang == "ar" else "The bot isn't in any server."
        return await ctx.send(msg)

    chunk_size = 8
    pages = []
    for i in range(0, len(guild_list), chunk_size):
        chunk = guild_list[i:i + chunk_size]
        title = f"🌐 سيرفرات البوت ({len(guild_list)} إجمالي)" if lang == "ar" else f"🌐 Bot Servers ({len(guild_list)} total)"
        embed = discord.Embed(title=title, color=discord.Color.blurple())
        for g in chunk:
            owner_name = g.owner if g.owner else "غير معروف"
            if lang == "ar":
                embed.add_field(name=g.name, value=f"آيدي: `{g.id}`\nالأعضاء: {g.member_count}\nالمالك: {owner_name}", inline=False)
            else:
                embed.add_field(name=g.name, value=f"ID: `{g.id}`\nMembers: {g.member_count}\nOwner: {owner_name}", inline=False)
        pages.append(embed)

    view = HelpPaginator(ctx, pages, lang)
    await ctx.send(embed=pages[0], view=view)


@bot.command(aliases=["مغادرة_سيرفر"])
@commands.is_owner()
async def leaveserver(ctx, guild_id: int = None):
    lang = get_lang(ctx.guild)
    if guild_id is None:
        msg = "❌ الاستخدام: `!leaveserver <آيدي السيرفر>` (استخدم `!servers` عشان تجيب الآيدي)" if lang == "ar" else "❌ Usage: `!leaveserver <guild ID>` (use `!servers` to get the ID)"
        return await ctx.send(msg)

    target_guild = bot.get_guild(guild_id)
    if target_guild is None:
        msg = "❌ البوت مو موجود بهذا السيرفر." if lang == "ar" else "❌ The bot isn't in that server."
        return await ctx.send(msg)

    name = target_guild.name
    await target_guild.leave()
    msg = f"✅ تم مغادرة سيرفر **{name}**." if lang == "ar" else f"✅ Left server **{name}**."
    await ctx.send(msg)


# ============================================================
#  معالج الأخطاء العام
# ============================================================
@bot.event
async def on_command_error(ctx, error):
    lang = get_lang(ctx.guild)

    if isinstance(error, commands.CommandNotFound):
        return

    if isinstance(error, Blacklisted):
        msg = f"🚫 أنت محظور من استخدام هذا البوت. السبب: {error.reason}" if lang == "ar" else f"🚫 You are blacklisted from using this bot. Reason: {error.reason}"
        try:
            await ctx.send(msg)
        except discord.Forbidden:
            pass
        return

    if isinstance(error, commands.MissingPermissions):
        msg = "❌ لا تملك الصلاحية الكافية لاستخدام هذا الأمر." if lang == "ar" else "❌ You don't have permission to use this command."
        return await ctx.send(msg)

    if isinstance(error, commands.MissingRequiredArgument):
        msg = "❌ ناقص بيانات في الأمر. استخدم `!help` للتأكد من الصيغة الصحيحة." if lang == "ar" else "❌ Missing arguments. Use `!help` to check the correct usage."
        return await ctx.send(msg)

    if isinstance(error, (commands.BadArgument, commands.MemberNotFound)):
        msg = "❌ لم أستطع إيجاد العضو أو القيمة غير صحيحة." if lang == "ar" else "❌ Couldn't find that member or the value is invalid."
        return await ctx.send(msg)

    if isinstance(error, commands.CommandOnCooldown):
        msg = f"⏳ الرجاء الانتظار {error.retry_after:.1f} ثانية." if lang == "ar" else f"⏳ Please wait {error.retry_after:.1f}s."
        return await ctx.send(msg)

    if isinstance(error, commands.NotOwner):
        msg = "❌ هذا الأمر لمالك البوت فقط." if lang == "ar" else "❌ This command is owner-only."
        return await ctx.send(msg)

    if isinstance(error, commands.CheckFailure):
        msg = "❌ لا تملك الصلاحية لاستخدام هذا الأمر." if lang == "ar" else "❌ You don't have permission for this."
        return await ctx.send(msg)

    print(f"⚠️ Unhandled error in command '{ctx.command}': {error}")
    msg = "❌ صار خطأ غير متوقع أثناء تنفيذ الأمر." if lang == "ar" else "❌ An unexpected error occurred."
    await ctx.send(msg)


bot.run(os.getenv("TOKEN"))
