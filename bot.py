import os
import logging
import asyncio
import threading
import time
import re
import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BotCommand
from pymongo import MongoClient
from pyrogram.errors import InputUserDeactivated, UserNotParticipant, FloodWait, UserIsBlocked, PeerIdInvalid
from health_check import start_health_check
from pyrogram.enums import ParseMode

# 🔰 Logging Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 🔰 Environment Variables
API_ID = int(os.getenv("API_ID", "37371391"))
API_HASH = os.getenv("API_HASH", "37895f967d284f6781f99e9beef21ebf")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8400031917:AAHzU3VA16otnPkYHFxZihNTWRNN4zrNuvQ")
MONGO_URL = os.getenv("MONGO_URL", "mongodb+srv://tgpurpose640:JkxqDWtmLTPtqf43@cluster0.1nlgp9s.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1003789202882"))
OWNER_ID = int(os.getenv("OWNER_ID", "7232121375"))
WELCOME_IMAGE = os.getenv("WELCOME_IMAGE", "https://envs.sh/n9o.jpg")
AUTO_DELETE_TIME = int(os.getenv("AUTO_DELETE_TIME", "30"))
DEFAULT_POINTS = int(os.getenv("DEFAULT_POINTS", "10"))
DEFAULT_RESET_TIME = int(os.getenv("DEFAULT_RESET_TIME", "18000"))

# ✅ Force Subscribe Setup
id_pattern = re.compile(r'^.\d+$')
AUTH_CHANNEL = [int(ch) if id_pattern.search(ch) else ch for ch in os.getenv("AUTH_CHANNEL", "-1003402069466").split()]

# 🔰 Initialize Bot & Database
bot = Client("video_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
mongo = MongoClient(MONGO_URL)
db = mongo["VideoBot1"]
collection = db["videos1"]
users_collection = db["users1"]
settings_collection = db["settings1"]

# ✅ **Cache Optimization**
video_cache = []
last_cache_time = 0
CACHE_EXPIRY = 300  # Refresh cache every 5 minutes

async def refresh_video_cache():
    global video_cache, last_cache_time
    if time.time() - last_cache_time > CACHE_EXPIRY:
        video_cache = list(collection.aggregate([{"$sample": {"size": 500}}]))  
        last_cache_time = time.time()

# ✅ **Fetch Protection Setting**
def is_protection_enabled():
    setting = settings_collection.find_one({"_id": "content_protection"})
    return setting and setting.get("enabled", True)

# ✅️ Tiers
PREMIUM_TIERS = {
    "silver": 10,
    "gold": 20,
    "diamond": 30,
    "platinum": 40
}

REFERRAL_TIERS = {
    10: ("silver", 5),
    30: ("gold", 10),
    50: ("diamond", 20)
}

# ✅ **User Management adding **
async def add_user(user_id):
    return get_user(user_id)

# ✅️ ** user management**
def get_user(user_id):
    user = users_collection.find_one({"id": user_id})
    if not user:
        settings = settings_collection.find_one({"_id": "points_settings"}) or {}
        reset_time = settings.get("reset_time", DEFAULT_RESET_TIME)

        user = {
            "id": user_id,
            "joined": datetime.datetime.utcnow(),
            "points": DEFAULT_POINTS,               # daily free points
            "points_reset_time": time.time() + reset_time,
            "paid_credits": 0,                      # 🔥 NEW
            "referral_points": 0,
            "referrals": [],
            "premium_used": 0,
            "premium": None
        }
        users_collection.insert_one(user)
    return user

# ✅ **/users Command – Get Total Users**
@bot.on_message(filters.command("users") & filters.user(OWNER_ID))
async def get_users_count(client, message):
    total_users = users_collection.count_documents({})
    await message.reply_text(f"📊 **Total Users:** `{total_users}`")

# ✅ **Broadcast System**
async def broadcast_messages(user_id, message):
    try:
        await message.copy(chat_id=user_id)
        return True, "Success"
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await broadcast_messages(user_id, message)
    except (InputUserDeactivated, UserIsBlocked, PeerIdInvalid):
        users_collection.delete_one({"id": user_id})
        return False, "Removed"
    except Exception:
        return False, "Error"

@bot.on_message(filters.command("broadcast") & filters.user(OWNER_ID) & filters.reply)
async def broadcast(client, message):
    users = users_collection.find()
    b_msg = message.reply_to_message
    total_users = users_collection.count_documents({})
    done, blocked, deleted, failed, success = 0, 0, 0, 0, 0

    status_msg = await message.reply_text(f"📢 **Broadcasting...**\nTotal Users: `{total_users}`")
    start_time = time.time()

    for user in users:
        user_id = user.get("id")
        if not user_id:
            continue
            
        result, reason = await broadcast_messages(user_id, b_msg)
        if result:
            success += 1
        else:
            if reason == "Removed":
                deleted += 1
            failed += 1
        done += 1

        if done % 20 == 0:
            try:
                await status_msg.edit(f"📢 **Broadcasting...**\nTotal Users: `{total_users}`\nProcessed: `{done}`\n✅ Success: `{success}`\n❌ Failed: `{failed}`\n🚫 Deleted: `{deleted}`")
            except:
                pass

    time_taken = datetime.timedelta(seconds=int(time.time() - start_time))
    await status_msg.edit(f"✅ **Broadcast Completed in {time_taken}!**\nTotal Users: `{total_users}`\nProcessed: `{done}`\n✅ Success: `{success}`\n❌ Failed: `{failed}`\n🚫 Deleted: `{deleted}`")

# ✅ **Start Command**
@bot.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    args = message.text.split()
    await add_user(user_id)

    if len(args) > 1 and args[1].startswith("ref-"):
        ref_id = int(args[1].split("-")[1])
        if ref_id != user_id:
            user = get_user(user_id)
            if ref_id not in user.get("referrals", []):
                users_collection.update_one({"id": ref_id}, {"$addToSet": {"referrals": user_id}})

    if AUTH_CHANNEL:
        try:
            btn = []
            for id in AUTH_CHANNEL:
                chat = await client.get_chat(int(id))
                await client.get_chat_member(id, user_id)
        except UserNotParticipant:
            btn.append([InlineKeyboardButton(f'Join {chat.title}', url=chat.invite_link)])
            btn.append([InlineKeyboardButton("♻️ Try Again ♻️", url=f"https://t.me/{client.me.username}?start=true")])
            await message.reply_text(
                f"👋 **Hello {message.from_user.mention},**\n\nJoin the channel and click 'Try Again'.",
                reply_markup=InlineKeyboardMarkup(btn),
            )
            return

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🎥 Get Random Video", callback_data="get_random_video")]]
    )
    await message.reply_photo(
        WELCOME_IMAGE, caption="🎉 Welcome to the Video Bot!\n\n<b>𝖳𝗁𝗂𝗌 𝖡𝗈𝗍 𝖢𝗈𝗇𝗍𝖺𝗂𝗇𝗌 18+ 𝖢𝗈𝗇𝗍𝖾𝗇𝗍 𝖲𝗈 𝖪𝗂𝗇𝖽𝗅𝗒 𝖠𝖼𝖼𝖾𝗌𝗌 𝖨𝗍 𝖶𝗂𝗍𝗁 𝖸𝗈𝗎𝗋 𝖮𝗐𝗇 𝖱𝗂𝗌𝗄. 𝖳𝗁𝖾 𝖬𝖺𝗍𝖾𝗋𝗂𝖺𝗅 𝖬𝖺𝗒 𝖨𝗇𝖼𝗅𝗎𝖽𝖾 𝖤𝗑𝗉𝗅𝗂𝖼𝗂𝗍 𝖮𝗋 𝖦𝗋𝖺𝗉𝗁𝗂𝖼 𝖢𝗈𝗇𝗍𝖺𝖼𝗍 𝖳𝗁𝖺𝗍 𝖨𝗌 𝖴𝗇𝗌𝗎𝗂𝗍𝖺𝖻𝗅𝖾 𝖥𝗈𝗋 𝖬𝗂𝗇𝗈𝗋𝗌. 𝖲𝗈 𝖢𝗁𝗂𝗅𝖽𝗋𝖾𝗇𝗌 𝖯𝗅𝖾𝖺𝗌𝖾 𝖲𝗍𝖺𝗒 𝖠𝗐𝖺𝗒.</b>\n\n 𝖯𝗅𝖾𝖺𝗌𝖾 𝖢𝗁𝖾𝖼𝗄 Disclaimer and About 𝖡𝖾𝖿𝗈𝗋𝖾 𝖴𝗌𝗂𝗇𝗀 𝖳𝗁𝗂𝗌 𝖡𝗈𝗍..\n\n ", reply_markup=keyboard)


# ✅ **Get Random Video**
async def send_random_video(client, chat_id):
    await refresh_video_cache()

    if not video_cache:
        await client.send_message(chat_id, "⚠ No videos available.")
        return

    if chat_id != OWNER_ID:
        user = get_user(chat_id)
        user = await reset_points_if_needed(user)

        quota_used = False  # 🔐 critical flag

        # 1️⃣ Daily Free Points
        if user.get("points", 0) > 0:
            users_collection.update_one(
                {"id": chat_id},
                {"$inc": {"points": -1}}
            )
            quota_used = True

        # 2️⃣ Referral Points
        elif user.get("referral_points", 0) > 0:
            users_collection.update_one(
                {"id": chat_id},
                {"$inc": {"referral_points": -1}}
            )
            quota_used = True

        # 3️⃣ Premium Daily Bonus
        elif user.get("premium") and time.time() < user["premium"].get("expiry", 0):
            tier = user["premium"]["tier"]
            max_premium = PREMIUM_TIERS.get(tier, 0)

            if user.get("premium_used", 0) < max_premium:
                users_collection.update_one(
                    {"id": chat_id},
                    {"$inc": {"premium_used": 1}}
                )
                quota_used = True

        # 4️⃣ Paid Credits
        if not quota_used and user.get("paid_credits", 0) > 0:
            users_collection.update_one(
                {"id": chat_id},
                {"$inc": {"paid_credits": -1}}
            )
            quota_used = True

        # ❌ No quota available
        if not quota_used:
            reset_time = datetime.datetime.fromtimestamp(
                user["points_reset_time"]
            ).strftime("%Y-%m-%d %H:%M:%S")

            await client.send_message(
                chat_id,
                f"⚠️ You’ve used all your free videos.\n\n"
                f"⏳ Free points reset at: {reset_time}\n"
                f"💎 Buy credits or wait for reset."
            )
            return

    # ✅ SEND VIDEO ONLY IF QUOTA WAS USED
    video = video_cache.pop()
    try:
        msg = await client.get_messages(CHANNEL_ID, video["message_id"])
        if msg and msg.video:
            sent = await client.send_video(
                chat_id,
                msg.video.file_id,
                caption="Thanks 😊",
                protect_content=True
            )
            if AUTO_DELETE_TIME > 0:
                await asyncio.sleep(AUTO_DELETE_TIME)
                await sent.delete()
    except FloodWait as e:
        await asyncio.sleep(e.value)
        await send_random_video(client, chat_id)


@bot.on_callback_query(filters.regex("get_random_video"))
async def random_video_callback(client, callback_query: CallbackQuery):
    await callback_query.answer()
    asyncio.create_task(send_random_video(client, callback_query.message.chat.id))


# ✅ **Points  Status**
async def calculate_total_points(user):
    total = user.get("points", 0)
    referral_points = user.get("referral_points", 0)
    premium = user.get("premium")
    premium_points = 0
    if premium and time.time() < premium.get("expiry", 0):
        tier = premium.get("tier")
        max_premium = PREMIUM_TIERS.get(tier, 0)
        used = user.get("premium_used", 0)
        premium_points = max_premium - used if used < max_premium else 0
        total += premium_points
    total += referral_points
    return total, referral_points, premium_points


async def reset_points_if_needed(user):
    settings = settings_collection.find_one({"_id": "points_settings"}) or {}
    reset_interval = settings.get("reset_time", DEFAULT_RESET_TIME)
    if time.time() > user.get("points_reset_time", 0):
        referral_points = 0
        for r, (name, pts) in REFERRAL_TIERS.items():
            if len(user.get("referrals", [])) >= r:
                referral_points = pts
        update_fields = {
            "points": DEFAULT_POINTS,
            "points_reset_time": time.time() + reset_interval,
            "referral_points": referral_points
        }
        if user.get("premium") and time.time() < user["premium"].get("expiry", 0):
            update_fields["premium_used"] = 0
        users_collection.update_one({"id": user["id"]}, {"$set": update_fields})
        user = get_user(user["id"])
    return user

# ✅️ **points **
@bot.on_message(filters.command("points"))
async def check_points(client, message):
    user = get_user(message.from_user.id)
    user = await reset_points_if_needed(user)
    points, ref, prem = await calculate_total_points(user)
    reset_time = datetime.datetime.fromtimestamp(user["points_reset_time"]).strftime("%Y-%m-%d %H:%M:%S")
    time_left = int(user["points_reset_time"] - time.time())
    await message.reply_text(
    f"⭐ Daily Free Points: {user.get('points', 0)}\n"
    f"🤝 Referral Points: {ref}\n"
    f"💎 Premium Bonus Left: {prem}\n"
    f"💳 Paid Credits: {user.get('paid_credits', 0)}\n"
    f"⏳ Next Reset In: {str(datetime.timedelta(seconds=time_left))}\n"
    f"🕒 Reset At: {reset_time}"
    )


# ✅️ **reset time option **
@bot.on_message(filters.command("setpoints") & filters.user(OWNER_ID))
async def set_points_reset(client, message):
    try:
        _, duration = message.text.split()
        if duration.endswith("h"):
            hours = int(duration[:-1])
            reset_time = hours * 3600
        elif duration.endswith("m"):
            minutes = int(duration[:-1])
            reset_time = minutes * 60
        else:
            reset_time = int(duration)

        # Save in settings
        settings_collection.update_one({"_id": "points_settings"}, {"$set": {"reset_time": reset_time}}, upsert=True)

        # Optional: force update all users' next reset time immediately
        new_reset_time = time.time() + reset_time
        users_collection.update_many({}, {"$set": {"points_reset_time": new_reset_time}})

        await message.reply_text(f"✅ Points reset interval updated to {duration}!")
    except:
        await message.reply_text("⚠ Usage: /setpoints <duration> (e.g., /setpoints 6h or /setpoints 30m)")


@bot.on_message(filters.command("getpoints") & filters.user(OWNER_ID))
async def get_points_reset(client, message):
    settings = settings_collection.find_one({"_id": "points_settings"}) or {}
    reset_time = settings.get("reset_time", DEFAULT_RESET_TIME)
    duration_str = str(datetime.timedelta(seconds=reset_time))
    await message.reply_text(f"⏱ Current points reset duration: {duration_str}")


# ✅ ** my plans **
@bot.on_message(filters.command("myplans"))
async def my_plans(client, message):
    user = get_user(message.from_user.id)
    premium = user.get("premium")
    text = "✨ <b>Your Current Plan</b> ✨\n\n"

    # Premium Tier Info
    if premium and time.time() < premium.get("expiry", 0):
        expiry = datetime.datetime.fromtimestamp(premium["expiry"]).strftime("%d %b %Y")
        tier = premium["tier"].capitalize()
        text += f"💎 <b>Premium Tier:</b> {tier}\n"
        text += f"⏳ <b>Valid Until:</b> {expiry}\n"
        text += f"⭐ <b>Bonus Points:</b> {PREMIUM_TIERS.get(premium['tier'], 0)} / reset\n"
    else:
        text += "💎 <b>Premium Tier:</b> None\n"
        text += "➕ <i>Upgrade to enjoy extra points daily!</i>\n"

    # Referral Info
    referrals = user.get("referrals", [])
    referral_count = len(referrals)
    referral_tier = "None"
    referral_bonus = 0
    for count, (tier, bonus) in sorted(REFERRAL_TIERS.items()):
        if referral_count >= count:
            referral_tier = tier.capitalize()
            referral_bonus = bonus

    text += "\n👥 <b>Referral Info</b>\n"
    if referral_count > 0:
        text += f"🥇 <b>Referral Tier:</b> {referral_tier}\n"
        text += f"👤 <b>Referrals:</b> {referral_count}\n"
        text += f"🎁 <b>Bonus:</b> +{referral_bonus} / reset"
    else:
        text += (
            "📭 <i>You haven't referred anyone yet.</i>\n"
            "🎯 Invite friends to unlock bonus points!"
        )

    await message.reply_text(text, parse_mode=ParseMode.HTML)
        

# ✅ **Index Videos**
@bot.on_message(filters.command("index") & filters.user(OWNER_ID))
async def index_videos(client, message):
    await message.reply_text("🔄 Indexing videos...")

    last_indexed = collection.find_one(sort=[("message_id", -1)])
    last_message_id = last_indexed["message_id"] if last_indexed else 1
    indexed_count = 0

    while True:
        try:
            messages = await client.get_messages(CHANNEL_ID, list(range(last_message_id, last_message_id + 100)))
            video_entries = [
                {"message_id": msg.id} for msg in messages if msg and msg.video and not collection.find_one({"message_id": msg.id})
            ]

            if video_entries:
                collection.insert_many(video_entries)
                indexed_count += len(video_entries)

            last_message_id += 100
            if not video_entries:
                break
        except Exception:
            break

    await refresh_video_cache()
    await message.reply_text(f"✅ Indexed {indexed_count} new videos!" if indexed_count else "⚠ No new videos found!")

# ✅️ plans
@bot.on_message(filters.command("plans"))
async def show_plans(client, message):
    photo_url = "https://envs.sh/s4V.jpg"
    text = (
        "💎 **Premium Plans**\n\n"
        "• **Silver** – 10 daily points\n"
        "   └ Rs. 29 / $0.35\n\n"
        "• **Gold** – 20 daily points\n"
        "   └ Rs. 59 / $0.70\n\n"
        "• **Diamond** – 30 daily points\n"
        "   └ Rs. 89 / $1.05\n\n"
        "• **Platinum** – 40 daily points\n"
        "   └ Rs. 129 / $1.50\n\n"
        "⏳ Plans renew daily until expiry.\n"
        "🔥 Above plans are monthly.\n"
        "❤️ Acess to unlimited files 😮‍💨.\n"
        "✨️ Must check Disclaimer for more info.\n"
        "🧾 Custom duration available.\n\n"
        "📞 Contact us to buy a plan!"
    )

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Buy Plan", url="https://t.me/Xsupprt4bot")]
    ])
    await message.reply_text(text, reply_markup=buttons)

# ✅️ **PREMIUM SYSTEM**
@bot.on_message(filters.command("addpremium") & filters.user(OWNER_ID))
async def add_premium(client, message):
    try:
        _, uid, level, days = message.text.split()
        uid = int(uid)
        days = int(days)
        expiry = time.time() + (days * 86400)
        users_collection.update_one({"id": uid}, {"$set": {"premium": {"tier": level.lower(), "expiry": expiry}, "premium_used": 0}})
        await message.reply_text("✅ Premium added.")
    except:
        await message.reply_text("Usage: /addpremium <user_id> <tier> <days>")


@bot.on_message(filters.command("removepremium") & filters.user(OWNER_ID))
async def remove_premium(client, message):
    try:
        _, uid = message.text.split()
        uid = int(uid)
        users_collection.update_one({"id": uid}, {"$unset": {"premium": "", "premium_used": ""}})
        await message.reply_text("✅ Premium removed.")
    except:
        await message.reply_text("Usage: /removepremium <user_id>")

@bot.on_message(filters.command("premiumusers") & filters.user(OWNER_ID))
async def list_premium_users(client, message):
    users = users_collection.find({"premium": {"$ne": None}})
    lines = []

    for i, user in enumerate(users, start=1):
        uid = user["id"]
        username = user.get("username")
        username_display = f"@{username}" if username else "—"
        username_link = f"[{username_display}](https://t.me/{username})" if username else "`—`"

        tier = user["premium"].get("tier", "Unknown").capitalize()
        expiry_ts = user["premium"].get("expiry", 0)
        expiry = datetime.datetime.fromtimestamp(expiry_ts).strftime("%Y-%m-%d %H:%M:%S")

        lines.append(
            f"**{i}.** 👤 **User ID:** `{uid}`\n"
            f"   🔗 **Username:** {username_link}\n"
            f"   💎 **Tier:** `{tier}`\n"
            f"   ⏰ **Expiry:** `{expiry}`\n"
        )

    if not lines:
        await message.reply_text("❌ No premium users found.")
        return

    text_output = "\n".join(lines)

    # Send as text message if short enough
    if len(text_output) <= 4096:
        await message.reply_text(f"**📋 Premium Users List:**\n\n{text_output}", disable_web_page_preview=True)
    else:
        await message.reply_text("⚠️ Too many users to display in chat. Sending as file instead.")

    # Also send as file
    file_path = "/tmp/premium_users.txt"
    with open(file_path, "w") as f:
        f.write(text_output)

    await message.reply_document(file_path, caption="📄 Premium Users List")


# ✅️ ** credit system **
@bot.on_message(filters.command("addcredits") & filters.user(OWNER_ID))
async def add_credits(client, message):
    try:
        _, uid, credits = message.text.split()
        uid = int(uid)
        credits = int(credits)

        users_collection.update_one(
            {"id": uid},
            {"$inc": {"paid_credits": credits}},
            upsert=True
        )

        await message.reply_text(
            f"✅ Successfully added {credits} paid credits to user {uid}"
        )
    except:
        await message.reply_text(
            "Usage: /addcredits <user_id> <credits>"
        )

# ✅️ **REFERRAL SYSTEM **
@bot.on_message(filters.command("referral"))
async def referral_handler(client, message):
    user_id = message.from_user.id
    referral_link = f"https://t.me/RundumBot?start=ref-{user_id}"

    text = (
        "👥 <b>Invite & Earn Rewards!</b>\n\n"
        "Share the link below with your friends. When they join and verify, you get bonus points every reset!\n\n"
        f"🔗 <b>Your Referral Link:</b>\n<code>{referral_link}</code>\n\n"
        "🏆 <b>Referral Tiers:</b>\n"
        "• 10 Referrals → <b>Silver</b> ⭐ (+5 pts/reset)\n"
        "• 30 Referrals → <b>Gold</b> 🌟 (+10 pts/reset)\n"
        "• 50 Referrals → <b>Diamond</b> 💎 (+20 pts/reset)\n\n"
        "⏳ <i>More referrals = more rewards!</i>"
    )

    await message.reply_text(text, parse_mode=ParseMode.HTML)

@bot.on_message(filters.command("myreferrals"))
async def my_referrals(client, message):
    user = get_user(message.from_user.id)
    referrals = user.get("referrals", [])
    count = len(referrals)
    tier_name = "None"

    for threshold, (name, _) in sorted(REFERRAL_TIERS.items(), reverse=True):
        if count >= threshold:
            tier_name = name.capitalize()
            break

    await message.reply_text(
        f"🤝 You have referred **{count}** user(s).\n"
        f"🏅 Your current referral tier: **{tier_name}**\n"
        "✨️ Referrals are permanent so, refer and earn points🔥.\n\n"
        "🔗 Share your referral link using /referral"
    )


@bot.on_message(filters.command("files") & filters.user(OWNER_ID))
async def total_files(client, message):
    total_files = collection.count_documents({})
    await message.reply_text(f"📂 **Total Indexed Files:** `{total_files}`")


@bot.on_message(filters.command("disclaimer"))
async def disclaimer_message(client, message):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Close", callback_data="close_disclaimer")]
    ])
    await message.reply_text(
        "**Disclaimer & Terms of Service**\n\n"
        "1. This bot is intended for educational and entertainment purposes only.\n"
        "2. We do not host or promote any copyrighted content.\n"
        "3. All media is shared from publicly available sources.\n"
        "4. Users are responsible for the content they access.\n"
        "5. We reserve the right to block users for misuse or abuse.\n\n"
        " **PAYMENT RULES**\n\n"
        "1. Must check all plans before paying.\n"
        "2. All plans are monthly based, weekly also available.\n"
        "3. No Refund will be given once purchased.\n"
        "4. Only serious buyers dm owner.\n"
        "5. Upi,gift cards(inr) are accepted.\n"
        "6. For foreign users, plan starts from $1.\n" 
        "7. FOR ANY ISSUE DM OWNER @XSUPPRT4BOT.\n\n" 
        "By using this bot, you agree to these terms.",
        reply_markup=keyboard
    )
    

@bot.on_callback_query(filters.regex("close_disclaimer"))
async def close_disclaimer_callback(client, callback_query: CallbackQuery):
    await callback_query.message.delete()


@bot.on_message(filters.command("about"))
async def about_command(client, message):
    await message.reply_text(
        text=(
            f"<b>○ Creator : <a href='https://t.me/Xsupprt4bot'>This Person</a>\n"
            f"○ Language : <code>Python3</code>\n"
            f"○ Library : <a href='https://docs.pyrogram.org/'>Pyrogram asyncio</a>\n"
            f"○ Source Code : <a href='https://t.me/Xsupprt3bot'>Click here </a>\n"
            f"○ Channel : @Allvidsbackup3\n"
            f"○ Support Group : @Xsupport_chats</b>"
        ),
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔒 Close", callback_data="close")]
        ])
    )

@bot.on_callback_query()
async def handle_close_button(client, query: CallbackQuery):
    if query.data == "close":
        await query.message.delete()
        try:
            await query.message.reply_to_message.delete()
        except:
            pass

#🔥premium expiry notification. 
async def premium_expiry_warning():
    warned_users = {}  # Track who has been warned

    while True:
        now = time.time()
        users = users_collection.find({"premium": {"$ne": None}})
        
        for user in users:
            user_id = user["id"]
            premium = user.get("premium", {})
            tier = premium.get("tier", "").capitalize()
            expiry = premium.get("expiry", 0)
            remaining = expiry - now

            if remaining <= 0:
                # Already expired
                if warned_users.get(user_id) != "expired":
                    try:
                        await bot.send_message(
                            user_id,
                            f"❌ Your <b>{tier}</b> premium plan has <b>expired</b>.\n"
                            "You have been moved back to the free plan.\n\n"
                            "Renew now to get back your bonus points!",
                            reply_markup=InlineKeyboardMarkup(
                                [[InlineKeyboardButton("💎 Contact Admin", url="https://t.me/Xsupprt4bot")]]
                            )
                        )
                        warned_users[user_id] = "expired"
                    except Exception as e:
                        logging.warning(f"Failed to send expiry message to {user_id}: {e}")
                continue

            if 3540 <= remaining <= 3660 and warned_users.get(user_id) != "1h":
                # ~1 hour left
                try:
                    await bot.send_message(
                        user_id,
                        f"⚠️ Your <b>{tier}</b> premium plan will expire in <b>1 hour</b>.\n\n"
                        "Renew now to continue enjoying bonus points!",
                        reply_markup=InlineKeyboardMarkup(
                            [[InlineKeyboardButton("💎 Contact Admin", url="https://t.me/Xsupprt4bot")]]
                        )
                    )
                    warned_users[user_id] = "1h"
                except Exception as e:
                    logging.warning(f"Failed to send 1h warning to {user_id}: {e}")

            elif 540 <= remaining <= 660 and warned_users.get(user_id) != "10m":
                # ~10 minutes left
                try:
                    await bot.send_message(
                        user_id,
                        f"⏳ Your <b>{tier}</b> premium plan will expire in <b>10 minutes</b>!\n\n"
                        "Don't miss out—renew now to keep enjoying your benefits.",
                        reply_markup=InlineKeyboardMarkup(
                            [[InlineKeyboardButton("💎 Contact Admin", url="https://t.me/Xsupprt4bot")]]
                        )
                    )
                    warned_users[user_id] = "10m"
                except Exception as e:
                    logging.warning(f"Failed to send 10m warning to {user_id}: {e}")

        await asyncio.sleep(300)  # Check every 5 minutes


# ✅ **Run the Bot**
if __name__ == "__main__":
    threading.Thread(target=start_health_check, daemon=True).start()
    loop = asyncio.get_event_loop()
    loop.create_task(premium_expiry_warning())
    bot.run()
    
