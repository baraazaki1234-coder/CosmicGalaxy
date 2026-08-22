import discord
from discord.ext import commands

# إعداد البوت
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# تخزين لغة السيرفرات ورصيد المجرات
server_langs = {}   # {guild_id: 'ar' or 'en'}
user_Galaxies = {}   # {user_id: amount}

# نصوص الترجمة للغتين
TRANSLATIONS = {
    "ar": {
        "help_title": "🌌 قائمة أوامر Cosmic Galaxy",
        "help_desc": "أهلاً بك! إليك قائمة الأوامر المتاحة:",
        "cmd_Galaxies_title": "🌌 نظام المجرات (Galaxies)",
        "cmd_Galaxies_val": "`!Galaxies` - عرض رصيدك من المجرات\n`!daily` - استلام المكافأة اليومية من المجرات\n`!addcredits @user <عدد>` - إضافة مجرات لمستخدم (للأدمن)",
        "cmd_admin_title": "🛡️ أوامر الإدارة",
        "cmd_admin_val": "`!clear <عدد>` - مسح عدد محدد من الرسائل\n`!kick @user` - طرد عضو من السيرفر",
        "cmd_gen_title": "⚙️ الأوامر العامة واللغة",
        "cmd_gen_val": "`!ping` - فحص سرعة استجابة البوت\n`!setlang <ar/en>` - تغيير لغة البوت في السيرفر",
        "help_footer": "تغيير اللغة: !setlang ar أو !setlang en",
        "Galaxies_msg": "🌌 رصيد **{user}** هو: **{amount}** مجرة.",
        "daily_success": "🎉 حصلت على **{amount}** مجرة هداية اليوم!",
        "lang_set": "✅ تم تغيير لغة البوت في هذا السيرفر إلى **العربية**.",
        "lang_usage": "❌ الاستخدام الصحيح: `!setlang ar` أو `!setlang en`",
        "ping_msg": "🏓 سرعة الاستجابة: **{ms}ms**",
        "clear_msg": "🧹 تم مسح **{count}** رسالة بنجاح.",
    },
    "en": {
        "help_title": "🌌 Cosmic Galaxy Commands",
        "help_desc": "Welcome! Here is the list of available commands:",
        "cmd_Galaxies_title": "🌌 Galaxies System",
        "cmd_Galaxies_val": "`!Galaxies` - Check your galaxy balance\n`!daily` - Claim your daily galaxy reward\n`!addcredits @user <amount>` - Add galaxies to a user (Admin)",
        "cmd_admin_title": "🛡️ Moderation Commands",
        "cmd_admin_val": "`!clear <amount>` - Delete specified amount of messages\n`!kick @user` - Kick a member",
        "cmd_gen_title": "⚙️ General & Language Commands",
        "cmd_gen_val": "`!ping` - Check bot latency\n`!setlang <ar/en>` - Change server language",
        "help_footer": "Change language: !setlang ar or !setlang en",
        "Galaxies_msg": "🌌 **{user}**'s balance is: **{amount}** Galaxies.",
        "daily_success": "🎉 You claimed your daily reward of **{amount}** Galaxies!",
        "lang_set": "✅ Bot language in this server has been set to **English**.",
        "lang_usage": "❌ Usage: `!setlang ar` or `!setlang en`",
        "ping_msg": "🏓 Latency: **{ms}ms**",
        "clear_msg": "🧹 Cleared **{count}** messages successfully.",
    }
}

def get_lang(guild):
    if not guild:
        return "ar"
    return server_langs.get(guild.id, "ar") # اللغة الافتراضية هي العربية

@bot.event
async def on_ready():
    print(f'Bot is ready! Logged in as {bot.user.name}')

# 1. أمر تغيير اللغة
@bot.command()
@commands.has_permissions(administrator=True)
async def setlang(ctx, lang: str = None):
    if not lang or lang.lower() not in ["ar", "en"]:
        current_l = get_lang(ctx.guild)
        await ctx.send(TRANSLATIONS[current_l]["lang_usage"])
        return
    
    lang = lang.lower()
    server_langs[ctx.guild.id] = lang
    await ctx.send(TRANSLATIONS[lang]["lang_set"])

# 2. أمر المساعدة (Help)
@bot.command()
async def help(ctx):
    lang = get_lang(ctx.guild)
    t = TRANSLATIONS[lang]
    
    embed = discord.Embed(
        title=t["help_title"],
        description=t["help_desc"],
        color=discord.Color.purple()
    )
    embed.add_field(name=t["cmd_credits_title"], value=t["cmd_credits_val"], inline=False)
    embed.add_field(name=t["cmd_admin_title"], value=t["cmd_admin_val"], inline=False)
    embed.add_field(name=t["cmd_gen_title"], value=t["cmd_gen_val"], inline=False)
    embed.set_footer(text=t["help_footer"])
    
    await ctx.send(embed=embed)

# 3. أمر عرض المجرات (Galaxies)
@bot.command(aliases=["Galaxies", "مجرات", "مجرة"])
async def credits(ctx, member: discord.Member = None):
    lang = get_lang(ctx.guild)
    t = TRANSLATIONS[lang]
    target = member or ctx.author
    amount = user_credits.get(target.id, 0)
    
    await ctx.send(t["credits_msg"].format(user=target.mention, amount=amount))

# 4. أمر المكافأة اليومية (daily)
@bot.command()
async def daily(ctx):
    lang = get_lang(ctx.guild)
    t = TRANSLATIONS[lang]
    reward = 100
    user_Galaxies[ctx.author.id] = user_Galaxies.get(ctx.author.id, 0) + reward
    
    await ctx.send(t["daily_success"].format(amount=reward))

# 5. أمر إضافة مجرات (addcredits)
@bot.command()
@commands.has_permissions(administrator=True)
async def addcredits(ctx, member: discord.Member, amount: int):
    user_Galaxies[member.id] = user_Galaxies.get(member.id, 0) + amount
    await ctx.send(f"✅ تم إضافة **{amount}** مجرة لـ {member.mention}.")

# 6. أمر البينج (ping)
@bot.command()
async def ping(ctx):
    lang = get_lang(ctx.guild)
    t = TRANSLATIONS[lang]
    ms = round(bot.latency * 1000)
    await ctx.send(t["ping_msg"].format(ms=ms))

# 7. أمر مسح الشات (clear)
@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int = 5):
    lang = get_lang(ctx.guild)
    t = TRANSLATIONS[lang]
    await ctx.channel.purge(limit=amount + 1)
    await ctx.send(t["clear_msg"].format(count=amount), delete_after=3)

# 8. أمر الطرد (kick)
@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason=None):
    await member.kick(reason=reason)
    await ctx.send(f"👢 تم طرد {member.mention}.")

# ضع التوكن الخاص ببوتك هنا
bot.run("YOUR_BOT_TOKEN")
    
