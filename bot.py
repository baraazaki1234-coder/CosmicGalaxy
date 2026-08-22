import discord
from discord.ext import commands
import datetime
import aiohttp

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# بيانات التخزين
server_langs = {}   # {guild_id: 'ar' or 'en'}
user_galaxies = {}  # {user_id: amount}

# --- نظام أزرار التنقل لقائمة Help ---
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
            msg = "عذراً، هذا زر التفاعل لا يخصك." if self.lang == "ar" else "Sorry, these buttons are not for you."
            return await interaction.response.send_message(msg, ephemeral=True)
        
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(label="التالي ▶️", style=discord.ButtonStyle.blurple, custom_id="next_btn")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            msg = "عذراً، هذا زر التفاعل لا يخصك." if self.lang == "ar" else "Sorry, these buttons are not for you."
            return await interaction.response.send_message(msg, ephemeral=True)
            
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

def get_lang(guild):
    return server_langs.get(guild.id, "ar") if guild else "ar"

@bot.event
async def on_ready():
    print(f'✅ Bot active: {bot.user.name}')

# --- 1. أمر قائمة المساعدة المطور (Help) ---
@bot.command(aliases=["هيلب", "الأوامر"])
async def help(ctx):
    lang = get_lang(ctx.guild)
    
    if lang == "ar":
        # صفحة 1: الأعضاء
        p1 = discord.Embed(title="🌌 قائمة الأوامر - (1/3) أوامر الأعضاء", color=discord.Color.purple())
        p1.add_field(name="`!galaxies`", value="عرض رصيدك من المجرات.", inline=False)
        p1.add_field(name="`!daily`", value="استلام المكافأة اليومية من المجرات.", inline=False)
        p1.add_field(name="`!transfer @user <عدد>`", value="تحويل مجرات لعضو آخر.", inline=False)
        p1.add_field(name="`!profile [@user]`", value="عرض البروفايل وصورة الشخص ومجراته.", inline=False)
        p1.add_field(name="`!ping`", value="عرض سرعة استجابة البوت.", inline=False)
        

        # صفحة 2: الإدارة
        p2 = discord.Embed(title="🛡️ قائمة الأوامر - (2/3) أوامر الإدارة", color=discord.Color.dark_red())
        p2.add_field(name="`!clear <عدد>`", value="مسح عدد محدد من الرسائل.", inline=False)
        p2.add_field(name="`!kick @user [سبب]`", value="طرد عضو من السيرفر.", inline=False)
        p2.add_field(name="`!ban @user [سبب]`", value="حظر عضو من السيرفر.", inline=False)
        p2.add_field(name="`!timeout @user <دقائق>`", value="إعطاء تايم أوت (ميوت مؤقت) لعضو.", inline=False)
        p2.add_field(name="`!addgalaxies @user <عدد>`", value="إضافة مجرات لعضو معين.", inline=False)
        p2.add_field(name="`!setlang <ar/en>`", value="تغيير لغة البوت داخل السيرفر.", inline=False)
        # صفحة 3: المالك
        p3 = discord.Embed(title="👑 قائمة الأوامر - (3/3) أوامر المالك", color=discord.Color.gold())
        p3.add_field(name="`!setname <الاسم الجديد>`", value="تغيير اسم البوت.", inline=False)
        p3.add_field(name="`!setavatar <رابط/صورة>`", value="تغيير صورة البوت الشخصية.", inline=False)
        p3.add_field(name="`!setstatus <النص>`", value="تغيير الحالة (Activity) الخاصة بالبوت.", inline=False)
    else:
        # English Pages
        p1 = discord.Embed(title="🌌 Help Menu - (1/3) Member Commands", color=discord.Color.purple())
        p1.add_field(name="`!galaxies`", value="Check your Galaxies balance.", inline=False)
        p1.add_field(name="`!daily`", value="Claim your daily reward.", inline=False)
        p1.add_field(name="`!transfer @user <amount>`", value="Transfer Galaxies to another member.", inline=False)
        p1.add_field(name="`!profile [@user]`", value="View member profile & Galaxies.", inline=False)
        p1.add_field(name="`!ping`", value="Check bot latency.", inline=False)
        p1.add_field(name="`!setlang <ar/en>`", value="Change server language.", inline=False)

        p2 = discord.Embed(title="🛡️ Help Menu - (2/3) Admin Commands", color=discord.Color.dark_red())
        p2.add_field(name="`!clear <amount>`", value="Clear chat messages.", inline=False)
        p2.add_field(name="`!kick @user [reason]`", value="Kick a member.", inline=False)
        p2.add_field(name="`!ban @user [reason]`", value="Ban a member.", inline=False)
        p2.add_field(name="`!timeout @user <minutes>`", value="Mute member temporarily.", inline=False)
        p2.add_field(name="`!addgalaxies @user <amount>`", value="Add Galaxies to a user.", inline=False)

        p3 = discord.Embed(title="👑 Help Menu - (3/3) Owner Commands", color=discord.Color.gold())
        p3.add_field(name="`!setname <name>`", value="Change bot username.", inline=False)
        p3.add_field(name="`!setavatar <url/file>`", value="Change bot avatar.", inline=False)
        p3.add_field(name="`!setstatus <text>`", value="Change bot activity status.", inline=False)

    pages = [p1, p2, p3]
    view = HelpPaginator(ctx, pages, lang)
    await ctx.send(embed=pages[0], view=view)

# --- 2. أوامر الأعضاء (Members) ---

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
    reward = 100
    user_galaxies[ctx.author.id] = user_galaxies.get(ctx.author.id, 0) + reward
    lang = get_lang(ctx.guild)
    
    if lang == "ar":
        await ctx.send(f"🎉 حصلت على **{reward}** مجرة هدية اليوم!")
    else:
        await ctx.send(f"🎉 You claimed your daily **{reward}** Galaxies!")

@bot.command(aliases=["تحويل", "pay"])
async def transfer(ctx, member: discord.Member, amount: int):
    if amount <= 0:
        return await ctx.send("❌ المبلغ يجب أن يكون أكبر من 0.")
    
    sender_bal = user_galaxies.get(ctx.author.id, 0)
    if sender_bal < amount:
        return await ctx.send("❌ لا تملك مجرات كافية للتحويل!")
    
    user_galaxies[ctx.author.id] -= amount
    user_galaxies[member.id] = user_galaxies.get(member.id, 0) + amount
    
    await ctx.send(f"🌌 تم تحويل **{amount}** مجرة بنجاح إلى {member.mention}!")

@bot.command(aliases=["بروفايل", "p"])
async def profile(ctx, member: discord.Member = None):
    target = member or ctx.author
    amount = user_galaxies.get(target.id, 0)
    
    embed = discord.Embed(title=f"👤 بروفايل {target.display_name}", color=discord.Color.purple())
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="🌌 المجرات (Galaxies):", value=f"`{amount}`", inline=True)
    embed.add_field(name="📅 تاريخ إنشاء الحساب:", value=f"<t:{int(target.created_at.timestamp())}:R>", inline=True)
    embed.add_field(name="📥 انضمامه للسيرفر:", value=f"<t:{int(target.joined_at.timestamp())}:R>", inline=True)
    embed.set_footer(text=f"User ID: {target.id}")
    
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
    await ctx.send(f"✅ Language updated to **{lang.upper()}**")

# --- 3. أوامر الإدارة (Admin) ---

@bot.command()
@commands.has_permissions(administrator=True)
async def addgalaxies(ctx, member: discord.Member, amount: int):
    user_galaxies[member.id] = user_galaxies.get(member.id, 0) + amount
    await ctx.send(f"✅ تم إضافة **{amount}** مجرة إلى {member.mention}.")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int = 5):
    await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🧹 تم مسح **{amount}** رسالة.", delete_after=3)

@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason=None):
    await member.kick(reason=reason)
    await ctx.send(f"👢 تم طرد {member.mention}.")

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason=None):
    await member.ban(reason=reason)
    await ctx.send(f"🔨 تم حظر {member.mention}.")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def timeout(ctx, member: discord.Member, minutes: int):
    duration = datetime.timedelta(minutes=minutes)
    await member.timeout(duration)
    await ctx.send(f"⏳ تم تطبيق تايم أوت على {member.mention} لمدة {minutes} دقيقة.")

# --- 4. أوامر المالك (Owner) ---

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

@bot.command()
@commands.is_owner()
async def setstatus(ctx, *, status_text: str):
    await bot.change_presence(activity=discord.Game(name=status_text))
    await ctx.send(f"✅ تم تغيير حالة البوت إلى: **{status_text}**")

bot.run("YOUR_BOT_TOKEN")
        
