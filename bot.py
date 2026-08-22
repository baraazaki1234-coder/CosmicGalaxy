import os
import datetime
import threading
import requests
from flask import Flask, redirect, request, session, render_template_string
import discord
from discord.ext import commands
import motor.motor_asyncio
import asyncio

# --- إعدادات ديسكورد ومونجو ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

MONGO_URL = os.getenv("MONGO_URL")
cluster = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
db = cluster["CosmicGalaxyDB"]
users_col = db["users"]
commands_col = db["custom_commands"]

CLIENT_ID = "1540670666892644392"
CLIENT_SECRET = "KKxIth2xhukD7zvKWIsc2e4CJrtgVS1z"
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:5000/callback")
DISCORD_API_URL = "https://discord.com/api/v10"

# --- سيرفر الويب (Flask Dashboard) ---
app = Flask(__name__)
app.secret_key = "cosmic_secret_key_123"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>Cosmic Galaxy - Dashboard</title>
    <style>
        body { font-family: sans-serif; background: #0f111a; color: white; text-align: center; padding: 40px; }
        .card { background: #1a1d2e; padding: 20px; border-radius: 12px; max-width: 500px; margin: auto; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
        input, button { padding: 10px; margin: 8px 0; border-radius: 6px; border: none; width: 90%; }
        input { background: #282c42; color: white; }
        button { background: #5865f2; color: white; font-weight: bold; cursor: pointer; }
        button:hover { background: #4752c4; }
        .cmd-item { background: #25283c; padding: 10px; border-radius: 6px; margin: 5px 0; text-align: right; }
    </style>
</head>
<body>
    <div class="card">
        <h2>🚀 لوحة تحكم Cosmic Galaxy</h2>
        {% if user %}
            <p>أهلاً بك، <b>{{ user['username'] }}</b>!</p>
            <hr>
            <h3>إضافة أمر مخصص جديد</h3>
            <form action="/add-command" method="POST">
                <input type="text" name="name" placeholder="اسم الأمر (مثال: قوانين)" required><br>
                <input type="text" name="response" placeholder="رد البوت على الأمر" required><br>
                <button type="submit">إضافة الأمر</button>
            </form>
            <hr>
            <h3>الأوامر المخصصة الحالية</h3>
            {% for cmd in custom_cmds %}
                <div class="cmd-item">
                    <b>!{{ cmd['name'] }}</b> ➔ {{ cmd['response'] }}
                </div>
            {% else %}
                <p>لا توجد أوامر مخصصة بعد.</p>
            {% endfor %}
            <br>
            <a href="/logout" style="color: #ff4757;">تسجيل الخروج</a>
        {% else %}
            <p>سجل دخول بحسابك في ديسكورد للتحكم في الأوامر.</p>
            <a href="/login"><button>تسجيل الدخول عبر Discord</button></a>
        {% endif %}
    </div>
</body>
</html>
"""

@app.route("/")
def home():
    user = session.get("user")
    custom_cmds = []
    if user:
        # جلب الأوامر المخصصة من قاعدة البيانات synchronous عبر asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        custom_cmds = loop.run_until_complete(commands_col.find().to_list(100))
    return render_template_string(HTML_TEMPLATE, user=user, custom_cmds=custom_cmds)

@app.route("/login")
def login():
    login_url = f"https://discord.com/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify"
    return redirect(login_url)

@app.route("/callback")
def callback():
    code = request.args.get("code")
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    r = requests.post(f"{DISCORD_API_URL}/oauth2/token", data=data, headers=headers)
    token_json = r.json()
    
    access_token = token_json.get("access_token")
    if access_token:
        user_r = requests.get(f"{DISCORD_API_URL}/users/@me", headers={"Authorization": f"Bearer {access_token}"})
        session["user"] = user_r.json()
    return redirect("/")

@app.route("/add-command", methods=["POST"])
def add_command():
    if "user" not in session:
        return redirect("/")
    name = request.form.get("name").strip().replace("!", "")
    response = request.form.get("response").strip()
    
    if name and response:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(commands_col.update_one({"name": name}, {"$set": {"response": response}}, upsert=True))
    return redirect("/")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

def run_flask():
    app.run(host="0.0.0.0", port=5000)

# --- أحداث وأوامر ديسكورد ---
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} with Web Dashboard active!")
    await bot.change_presence(activity=discord.Game(name="Cosmic Galaxy | !help"))

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # فحص إذا كان الكلام المكتوب عبارة عن أمر مخصص من MongoDB
    if message.content.startswith("!"):
        cmd_name = message.content[1:].strip()
        custom_cmd = await commands_col.find_one({"name": cmd_name})
        if custom_cmd:
            await message.channel.send(custom_cmd["response"])
            return

    await bot.process_commands(message)

@bot.command()
async def ping(ctx):
    await ctx.send(f"🏓 Pong! {round(bot.latency * 1000)}ms")

@bot.command()
async def daily(ctx):
    user_id = ctx.author.id
    now = datetime.datetime.utcnow().timestamp()
    cooldown = 86400

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

# تشغيل سيرفر الويب في خلفية مستقلة
threading.Thread(target=run_flask, daemon=True).start()

token = os.getenv("DISCORD_TOKEN")
if token:
    bot.run(token)
else:
    print("Error: DISCORD_TOKEN missing!")
    
