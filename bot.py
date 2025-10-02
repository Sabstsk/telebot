# telegram_number_bot.py
# Simple Telegram bot that calls:
# https://flipcartstore.serv00.net/INFO.php?api_key=chxInfo&mobile=<mobile>
#
# Requirements:
#   pip install pyTelegramBotAPI requests
#
# Usage:
# 1) Create a .env file with your BOT_TOKEN and CHAT_ID (see .env file)
# 2) Install dependencies: pip install -r requirements.txt
# 3) Run: python bot.py
# 4) In Telegram send: /check 9876543210   OR just send the number.

import telebot
from telebot import types
import requests
import re
import time
import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import Flask, request, jsonify

# Load environment variables from .env file
load_dotenv()

# === CONFIG ===
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Load from environment variable
CHAT_ID = os.getenv("CHAT_ID")      # Load chat ID from environment variable
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "CRAZYPANEL1")  # Admin username
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "7490634345"))  # Admin user ID
API_KEY = os.getenv("API_KEY")  # Load from environment variable only
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Webhook URL for production
PORT = int(os.getenv("PORT", 5000))  # Port for Flask app
if not API_KEY:
    raise ValueError("API_KEY environment variable is required. Please check your .env file.")
API_ENDPOINT_TEMPLATE = f"https://flipcartstore.serv00.net/INFO.php?api_key={API_KEY}&mobile={{number}}"
REQUEST_TIMEOUT = 10  # seconds
MAX_RETRIES = 2
RETRY_DELAY = 1.0  # seconds between retries

# Subscription file management
SUBSCRIPTION_FILE = "subscriptions.json"

def load_subscriptions():
    """Load subscription data from JSON file."""
    try:
        if os.path.exists(SUBSCRIPTION_FILE):
            with open(SUBSCRIPTION_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                loaded_users = {}
                
                # Convert string dates back to datetime objects and convert user_id keys to integers
                for user_id_str, sub_data in data.get("users", {}).items():
                    # Convert user_id from string to integer
                    user_id = int(user_id_str)
                    
                    # Convert date strings back to datetime objects
                    if sub_data.get("expires"):
                        sub_data["expires"] = datetime.fromisoformat(sub_data["expires"])
                    if sub_data.get("last_reset"):
                        sub_data["last_reset"] = datetime.fromisoformat(sub_data["last_reset"]).date()
                    if sub_data.get("created_date"):
                        sub_data["created_date"] = datetime.fromisoformat(sub_data["created_date"])
                    
                    # Store with integer key
                    loaded_users[user_id] = sub_data
                
                print(f"Subscriptions loaded: {len(loaded_users)} users")
                return loaded_users
        return {}
    except Exception as e:
        print(f"Error loading subscriptions: {e}")
        return {}

def save_subscriptions():
    """Save subscription data to JSON file."""
    try:
        # Convert datetime objects to strings for JSON serialization
        users_data = {}
        for user_id, sub_data in user_subscriptions.items():
            users_data[str(user_id)] = sub_data.copy()
            if sub_data.get("expires"):
                users_data[str(user_id)]["expires"] = sub_data["expires"].isoformat()
            if sub_data.get("last_reset"):
                users_data[str(user_id)]["last_reset"] = sub_data["last_reset"].isoformat()
            if sub_data.get("created_date"):
                users_data[str(user_id)]["created_date"] = sub_data["created_date"].isoformat()
        
        data = {
            "users": users_data,
            "metadata": {
                "last_updated": datetime.now().isoformat(),
                "total_users": len(users_data),
                "version": "1.0"
            }
        }
        
        with open(SUBSCRIPTION_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"Subscriptions saved: {len(users_data)} users")
    except Exception as e:
        print(f"Error saving subscriptions: {e}")

def add_subscription_user(user_id, username, first_name, plan, payment_amount=0):
    """Add or update user subscription with full details."""
    # Check if user is admin (by user ID or username)
    is_admin = (user_id == ADMIN_USER_ID) or (username and username.upper() == ADMIN_USERNAME.upper())
    
    user_data = {
        "user_id": user_id,
        "username": username or "N/A",
        "first_name": first_name or "N/A",
        "plan": plan,
        "payment_amount": payment_amount,
        "created_date": datetime.now(),
        "expires": None,
        "searches_used": 0,
        "last_reset": datetime.now().date(),
        "total_searches": 0,
        "status": "active",
        "is_admin": is_admin
    }
    
    # Set expiry date based on plan
    if plan == "single":
        user_data["expires"] = datetime.now() + timedelta(days=1)
    elif plan == "lifetime":
        user_data["expires"] = datetime.now() + timedelta(days=361000)  # 100 years
    
    user_subscriptions[user_id] = user_data
    save_subscriptions()
    return user_data

# Storage for search history and stats
search_history = {}  # user_id: [list of searches]
bot_stats = {"total_searches": 0, "start_time": datetime.now()}
broadcast_mode = {}  # user_id: True when admin is in broadcast mode
admin_subscription_mode = {}  # user_id: True when admin is adding subscription

# Subscription system
user_subscriptions = load_subscriptions()  # Load existing subscriptions from file

# Ensure admin has lifetime subscription
if ADMIN_USER_ID not in user_subscriptions:
    print(f"👑 Creating lifetime subscription for admin (ID: {ADMIN_USER_ID})")
    user_subscriptions[ADMIN_USER_ID] = {
        "user_id": ADMIN_USER_ID,
        "username": ADMIN_USERNAME,
        "first_name": "Admin",
        "plan": "lifetime",
        "payment_amount": 0,  # Free for admin
        "created_date": datetime.now(),
        "expires": datetime.now() + timedelta(days=36500),  # 100 years
        "searches_used": 0,
        "last_reset": datetime.now().date(),
        "total_searches": 0,
        "status": "active",
        "is_admin": True
    }
    save_subscriptions()
else:
    # Ensure existing admin has proper admin status
    admin_sub = user_subscriptions[ADMIN_USER_ID]
    if admin_sub.get('plan') != 'lifetime' or not admin_sub.get('is_admin', False):
        print(f"🔄 Updating admin subscription to lifetime")
        admin_sub['plan'] = 'lifetime'
        admin_sub['is_admin'] = True
        admin_sub['expires'] = datetime.now() + timedelta(days=36500)
        admin_sub['payment_amount'] = 0
        save_subscriptions()

# Debug: Print loaded subscriptions at startup
print(f"🔄 Bot starting with {len(user_subscriptions)} existing subscriptions:")
for user_id, sub_data in user_subscriptions.items():
    admin_status = " (ADMIN)" if sub_data.get('is_admin', False) else ""
    print(f"  👤 User {user_id}: {sub_data['plan']} plan (expires: {sub_data.get('expires', 'Never')}){admin_status}")

subscription_plans = {
    "free": {"searches_per_day": 0, "price": 0, "duration_days": 0},
    "single": {"searches_per_day": 1, "price": 100, "duration_days": 1},      # ₹100 for 1 search
    "lifetime": {"searches_per_day": 999, "price": 8000, "duration_days": 36500}  # ₹8000 lifetime (100 years)
}
# =============

# Validate that required environment variables are loaded
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required. Please check your .env file.")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# simple number validator: allow optional +, digits, 10-15 digits total
NUMBER_RE = re.compile(r'^\+?\d{10,15}$')

def normalize_number(text: str) -> str | None:
    """Extract and normalize digits from input. Returns None if invalid."""
    text = text.strip()
    # remove spaces, hyphens, parentheses
    cleaned = re.sub(r'[\s\-\(\)]', '', text)
    # if it contains letters -> invalid
    if re.search(r'[A-Za-z]', cleaned):
        return None
    # keep leading + if present
    if cleaned.startswith('+'):
        candidate = cleaned
    else:
        candidate = re.sub(r'^\D+', '', cleaned)  
    if NUMBER_RE.match(candidate):
        return candidate
    # maybe the user passed number with country code prefix like 0 at start; try just digits
    digits = re.sub(r'\D', '', cleaned)
    if len(digits) >= 10 and len(digits) <= 15:
        return digits
    return None

def format_user_data(data_list):
    """Format JSON data with emojis for better readability."""
    if not data_list:
        return "❌ No data found"
    
    formatted_text = f"📱 **Mobile Number Search Results** 📱\n"
    formatted_text += f"🔍 Found {len(data_list)} record(s)\n\n"
    
    for i, record in enumerate(data_list, 1):
        formatted_text += f"📋 **Record {i}:**\n"
        formatted_text += f"👤 **Name:** {record.get('name', 'N/A')}\n"
        formatted_text += f"📞 **Mobile:** {record.get('mobile', 'N/A')}\n"
        formatted_text += f"👨‍👦 **Father's Name:** {record.get('father_name', 'N/A')}\n"
        formatted_text += f"🏠 **Address:** {record.get('address', 'N/A').replace('!!', ', ')}\n"
        
        if record.get('alt_mobile'):
            formatted_text += f"📱 **Alt Mobile:** {record.get('alt_mobile')}\n"
        
        formatted_text += f"🌐 **Circle:** {record.get('circle', 'N/A')}\n"
        formatted_text += f"🆔 **Adhar no::** {record.get('id_number', 'N/A')}\n"
        
        if record.get('email'):
            formatted_text += f"📧 **Email:** {record.get('email')}\n"
    
        
        if i < len(data_list):
            formatted_text += "\n" + "─" * 30 + "\n\n"
    
    return formatted_text

def create_main_keyboard():
    """Create simple main inline keyboard with essential options."""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("🔍 Check Number", callback_data="check_number"),
        types.InlineKeyboardButton("📈 Statistics", callback_data="statistics")
    )
    keyboard.add(
        types.InlineKeyboardButton("📋 History", callback_data="history"),
        types.InlineKeyboardButton("💎 Subscription", callback_data="subscription")
    )
    keyboard.add(
        types.InlineKeyboardButton("📊 My Subscription", callback_data="my_subscription"),
        types.InlineKeyboardButton("❓ Help", callback_data="help")
    )
    return keyboard

def get_user_subscription(user_id, username=None, first_name=None):
    """Get user's current subscription status."""
    if user_id not in user_subscriptions:
        # Check if user is admin (by user ID or username)
        is_admin = (user_id == ADMIN_USER_ID) or (username and username.upper() == ADMIN_USERNAME.upper())
        
        if is_admin:
            # Admin gets lifetime access by default
            user_subscriptions[user_id] = {
                "user_id": user_id,
                "username": username or "N/A",
                "first_name": first_name or "N/A",
                "plan": "lifetime",
                "payment_amount": 0,  # Free for admin
                "created_date": datetime.now(),
                "expires": datetime.now() + timedelta(days=361000),  # 100 years
                "searches_used": 0,
                "last_reset": datetime.now().date(),
                "total_searches": 0,
                "status": "active",
                "is_admin": True
            }
        else:
            # New user gets free plan with full details
            user_subscriptions[user_id] = {
                "user_id": user_id,
                "username": username or "N/A",
                "first_name": first_name or "N/A",
                "plan": "free",
                "payment_amount": 0,
                "created_date": datetime.now(),
                "expires": None,
                "searches_used": 0,
                "last_reset": datetime.now().date(),
                "total_searches": 0,
                "status": "active",
                "is_admin": False
            }
        save_subscriptions()
    
    subscription = user_subscriptions[user_id]
    
    # Update user details if provided
    if username and subscription.get("username") != username:
        subscription["username"] = username
        save_subscriptions()
    if first_name and subscription.get("first_name") != first_name:
        subscription["first_name"] = first_name
        save_subscriptions()
    
    # Check if subscription expired
    if subscription["expires"] and datetime.now() > subscription["expires"]:
        subscription["plan"] = "free"
        subscription["expires"] = None
        subscription["status"] = "expired"
        save_subscriptions()
    
    # Reset daily search count
    if subscription["last_reset"] != datetime.now().date():
        subscription["searches_used"] = 0
        subscription["last_reset"] = datetime.now().date()
        save_subscriptions()
    
    return subscription

def can_user_search(user_id):
    """Check if user can perform a search based on their subscription."""
    # Check if user is admin by checking their subscription
    subscription = get_user_subscription(user_id)
    if subscription.get("is_admin", False):  # Admin has unlimited access
        return True, ""
    
    plan = subscription_plans[subscription["plan"]]
    
    if subscription["searches_used"] >= plan["searches_per_day"]:
        return False, f"❌ Daily limit reached! You've used {subscription['searches_used']}/{plan['searches_per_day']} searches.\n\n🔍 **Single Search:** ₹100 for 1 search\n👑 **Lifetime:** ₹8000 for unlimited searches forever!"
    
    return True, ""

def use_search_credit(user_id):
    """Deduct one search credit from user."""
    subscription = get_user_subscription(user_id)
    
    # Don't deduct credits from admin
    if not subscription.get("is_admin", False):
        subscription["searches_used"] += 1
    
    subscription["total_searches"] = subscription.get("total_searches", 0) + 1
    save_subscriptions()

def create_subscription_keyboard():
    """Create subscription plans keyboard."""
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton("🔍 Single Search - ₹100 (1 search)", callback_data="plan_single"),
        types.InlineKeyboardButton("👑 Lifetime Plan - ₹8000 (Unlimited forever)", callback_data="plan_lifetime"),
        types.InlineKeyboardButton("📊 My Subscription", callback_data="my_subscription"),
        types.InlineKeyboardButton("🔙 Back to Main", callback_data="back_main")
    )
    return keyboard

def is_admin(message):
    """Check if user is admin."""
    user_id = message.from_user.id
    username = message.from_user.username
    return (user_id == ADMIN_USER_ID) or (username and username.upper() == ADMIN_USERNAME.upper())

def is_admin_by_user_id(user_id, username):
    """Check if user is admin by user ID and username."""
    return (user_id == ADMIN_USER_ID) or (username and username.upper() == ADMIN_USERNAME.upper())

def create_admin_keyboard():
    """Create admin inline keyboard with management options."""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("👥 All Users", callback_data="admin_users"),
        types.InlineKeyboardButton("📊 Full Stats", callback_data="admin_stats")
    )
    keyboard.add(
        types.InlineKeyboardButton("🗂️ All History", callback_data="admin_history"),
        types.InlineKeyboardButton("💎 Manage Subs", callback_data="admin_subscriptions")
    )
    keyboard.add(
        types.InlineKeyboardButton("➕ Add Subscription", callback_data="admin_add_sub"),
        types.InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")
    )
    keyboard.add(
        types.InlineKeyboardButton("🛠️ Bot Control", callback_data="admin_control"),
        types.InlineKeyboardButton("🔄 Reset Stats", callback_data="admin_reset")
    )
    keyboard.add(
        types.InlineKeyboardButton("🔙 Back to Main", callback_data="back_main")
    )
    return keyboard

def create_admin_sub_keyboard():
    """Create admin subscription management keyboard."""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("🔍 Add Single (₹100)", callback_data="admin_sub_single"),
        types.InlineKeyboardButton("👑 Add Lifetime (₹8000)", callback_data="admin_sub_lifetime")
    )
    keyboard.add(
        types.InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel_sub"),
        types.InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")
    )
    return keyboard

def add_to_history(user_id, number, result_found=True):
    """Add search to user's history."""
    if user_id not in search_history:
        search_history[user_id] = []
    
    search_entry = {
        "number": number,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "result_found": result_found
    }
    
    search_history[user_id].append(search_entry)
    # Keep only last 10 searches per user
    if len(search_history[user_id]) > 10:
        search_history[user_id] = search_history[user_id][-10:]
    
    # Update global stats
    bot_stats["total_searches"] += 1

def query_api(number: str) -> tuple[bool, str]:
    """Call the remote API. Returns (success, result_text)."""
    url = API_ENDPOINT_TEMPLATE.format(number=number)
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
            # try to return response text (API may return json or plain text)
            if resp.status_code == 200:
                # Try to parse and format JSON response
                try:
                    json_data = resp.json()
                    if isinstance(json_data, list) and len(json_data) > 0:
                        # Format the data with emojis
                        formatted_response = format_user_data(json_data)
                        return True, formatted_response
                    else:
                        return True, "❌ No data found for this number"
                except (json.JSONDecodeError, ValueError):
                    # If not JSON, return raw text
                    return True, resp.text
            else:
                return False, f"API returned HTTP {resp.status_code}: {resp.text}"
        except Exception as e:
            last_exc = e
            time.sleep(RETRY_DELAY)
    return False, f"Request failed after {MAX_RETRIES} attempts. Last error: {last_exc}"

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    if is_admin(message):
        welcome_text = """
🤖 **Welcome Admin @CRAZYPANEL1!** 🤖
👑 **Admin Access - Unlimited Searches!**

🔍 **What I can do:**
• Search mobile number details instantly
• Show name, address, father's name, location
• Track search history and statistics
• Admin panel with full control

📱 **How to use:**
• Send a mobile number directly (e.g., 9876543210)
• Use /check <number> command
• Use /admin for admin panel

Choose an option below! 👇
        """
        keyboard = create_main_keyboard()
        # Add admin button to main keyboard for admin
        admin_button = types.InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel")
        keyboard.add(admin_button)
        bot.send_message(message.chat.id, welcome_text, reply_markup=keyboard, parse_mode='Markdown')
    else:
        welcome_text = """
🤖 **Welcome to Mobile Number Lookup Bot!** 🤖

🔍 **What I can do:**
• Search mobile number details instantly
• Show name, address, father's name, location, adhar number
• Track your search history
• Support multiple number formats

📱 **How to use:**
• Send a mobile number directly (e.g., 9876543210)
• Use /check <number> command
• Supports formats: 9876543210, +919876543210

💎 **Subscription Plans:**
• 🆓 Free: 0 searches/day (upgrade required)
• 🔍 Single: ₹100 for 1 search (24 hours)
• 👑 Lifetime: ₹8000 unlimited forever

🚀 **Get Started:**
Send any mobile number to try it out!
        """
        bot.send_message(message.chat.id, welcome_text, reply_markup=create_main_keyboard(), parse_mode='Markdown')

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    """Admin panel command - only accessible by admin."""
    if not is_admin(message):
        bot.reply_to(message, "❌ Access Denied! You are not authorized to use admin commands.")
        return
    
    admin_text = """
👑 **ADMIN PANEL** 👑
Welcome @CRAZYPANEL1!

🛠️ **Admin Controls Available:**
• View all users and their info
• Access complete bot statistics
• View all search history
• Add subscriptions instantly
• Reset bot statistics
• Broadcast messages to all users
• Bot control and management

Select an option below:
    """
    bot.send_message(message.chat.id, admin_text, reply_markup=create_admin_keyboard(), parse_mode='Markdown')

@bot.message_handler(commands=['cancel'])
def cancel_admin_action(message):
    """Cancel any ongoing admin action."""
    if not is_admin(message):
        return
    
    cancelled_actions = []
    
    if message.from_user.id in admin_subscription_mode:
        del admin_subscription_mode[message.from_user.id]
        cancelled_actions.append("subscription addition")
    
    if message.from_user.id in broadcast_mode:
        del broadcast_mode[message.from_user.id]
        cancelled_actions.append("broadcast mode")
    
    if cancelled_actions:
        bot.reply_to(message, f"❌ **Cancelled:** {', '.join(cancelled_actions)}", reply_markup=create_admin_keyboard(), parse_mode='Markdown')
    else:
        bot.reply_to(message, "ℹ️ **No active admin actions to cancel.**", reply_markup=create_admin_keyboard(), parse_mode='Markdown')

@bot.message_handler(commands=['info'])
def bot_info(message):
    """Show bot information."""
    info_text = """
ℹ️ **Bot Information** ℹ️

🤖 **Name:** Mobile Number Lookup Bot
⚡ **Version:** 2.0
🔧 **Developer:** @CRAZYPANEL1  
🌐 **API:** Flipcart Store API

🎯 **Features:**
• Mobile number lookup
• Personal info search
• Search history tracking
• Real-time statistics
• User-friendly interface

🔒 **Privacy:** Your searches are stored locally only for history purposes.
    """
    bot.send_message(message.chat.id, info_text, parse_mode='Markdown')

@bot.message_handler(commands=['status'])
def bot_status(message):
    """Show bot status."""
    uptime = datetime.now() - bot_stats["start_time"]
    status_text = f"""
🔋 **Bot Status** 🔋

✅ **Status:** Online & Running
⏰ **Uptime:** {str(uptime).split('.')[0]}
🔍 **Total Searches:** {bot_stats['total_searches']}
👥 **Active Users:** {len(search_history)}
🚀 **Started:** {bot_stats['start_time'].strftime('%Y-%m-%d %H:%M:%S')}

🌐 **API Status:** Connected
💾 **Database:** Operational
    """
    bot.send_message(message.chat.id, status_text, parse_mode='Markdown')

@bot.message_handler(commands=['mystats'])
def my_stats(message):
    """Show user's personal statistics."""
    user_id = message.from_user.id
    subscription = get_user_subscription(user_id)
    user_history = search_history.get(user_id, [])
    
    stats_text = f"""
📊 **Your Personal Stats** 📊

🆔 **Your ID:** `{user_id}`
📋 **Plan:** {subscription['plan'].title()}
🔍 **Total Searches:** {len(user_history)}
📈 **Searches Today:** {subscription['searches_used']}
📅 **Member Since:** {subscription.get('created_date', 'Unknown')}

📱 **Recent Activity:**
    """
    
    if user_history:
        for i, entry in enumerate(reversed(user_history[-3:]), 1):
            status = "✅" if entry['result_found'] else "❌"
            stats_text += f"\n{i}. {status} {entry['number']} - {entry['timestamp']}"
    else:
        stats_text += "\nNo searches yet!"
    
    bot.send_message(message.chat.id, stats_text, parse_mode='Markdown')

@bot.message_handler(commands=['clearhistory'])
def clear_history(message):
    """Clear user's search history."""
    user_id = message.from_user.id
    
    if user_id in search_history:
        search_history[user_id] = []
        bot.reply_to(message, "✅ **History Cleared!** Your search history has been deleted.", parse_mode='Markdown')
    else:
        bot.reply_to(message, "ℹ️ **No History Found!** You don't have any search history to clear.", parse_mode='Markdown')

@bot.message_handler(commands=['contact'])
def contact_info(message):
    """Show contact information."""
    contact_text = """
📞 **Contact Information** 📞

👨‍💼 **Admin:** @CRAZYPANEL1
💬 **Support:** Direct message to admin
📧 **Email:** Available on request

💳 **Payment Support:**
• UPI Issues: Contact admin
• Subscription Problems: Send screenshot
• Technical Help: Use /start and try again

⏰ **Response Time:** Usually within 24 hours
🔒 **Privacy:** All conversations are confidential
    """
    bot.send_message(message.chat.id, contact_text, parse_mode='Markdown')

@bot.message_handler(commands=['pricing'])
def show_pricing(message):
    """Show subscription pricing."""
    pricing_text = """
💰 **Subscription Pricing** 💰

🆓 **Free Plan:**
• 0 searches per day
• Basic features only
• Upgrade required for searches

🔍 **Single Search - ₹100:**
• 1 search valid for 24 hours
• Perfect for one-time use
• No monthly commitment
• Instant activation

👑 **Lifetime Plan - ₹8000:**
• Unlimited searches forever
• No monthly payments
• Priority support
• Advanced features
• One-time payment only

💳 **Payment Methods:**
⚠️ **Currently under maintenance - Contact admin directly**
• Admin will provide payment details
• Manual activation available

📝 **To upgrade:** Contact @CRAZYPANEL1 directly (Payment system under maintenance)
    """
    bot.send_message(message.chat.id, pricing_text, parse_mode='Markdown')

@bot.message_handler(commands=['check'])
def handle_check(message):
    # Check subscription limits
    can_search, limit_message = can_user_search(message.from_user.id)
    if not can_search:
        bot.reply_to(message, limit_message, reply_markup=create_subscription_keyboard())
        return
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "Usage: /check <mobile_number>")
        return
    raw = args[1]
    number = normalize_number(raw)
    if not number:
        bot.reply_to(message, "I couldn't parse that number. Send digits like 9876543210 or +919876543210.")
        return
    
    # Use search credit
    use_search_credit(message.from_user.id)
    
    sent = bot.reply_to(message, f"🔍 Checking number: {number} ...")
    success, result = query_api(number)
    
    # Add to history
    add_to_history(message.from_user.id, number, success and "No data found" not in result)
    
    # Add subscription info to result
    subscription = get_user_subscription(message.from_user.id, message.from_user.username, message.from_user.first_name)
    plan_info = subscription_plans[subscription["plan"]]
    remaining = plan_info["searches_per_day"] - subscription["searches_used"]
    
    footer = f"\n\n📊 **Searches remaining today:** {remaining}/{plan_info['searches_per_day']}"
    if subscription["plan"] == "free":
        footer += f"\n🔍 **Single Search:** ₹100 | 👑 **Lifetime:** ₹8000"
    
    if success:
        bot.edit_message_text(chat_id=sent.chat.id, message_id=sent.message_id, text=f"📱 Result for {number}:\n\n{result}{footer}", parse_mode='Markdown')
    else:
        bot.edit_message_text(chat_id=sent.chat.id, message_id=sent.message_id, text=f"❌ Error querying API for {number}:\n\n{result}{footer}")

@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    """Handle inline keyboard button clicks."""
    user_id = call.from_user.id
    
    if call.data == "check_number":
        bot.answer_callback_query(call.id)
        check_text = """
🔍 **Ready to Check Mobile Number!** 🔍

📱 **Send me a mobile number in any of these formats:**
• `9876543210`
• `+919876543210`
• `91-9876543210`
• `9876 543 210`

💡 **What you'll get:**
• Name of the number holder
• Father's name (if available)
• Complete address with location
• Alternative numbers (if linked)
• Circle/State information
• Email address (if available)
• Adhar number.


🚀 **Just type the number and send it!**

📊 **Your current plan:** Check "💎 Subscription" for details
        """
        bot.send_message(call.message.chat.id, check_text, parse_mode='Markdown')
    
    elif call.data == "statistics":
        bot.answer_callback_query(call.id)
        uptime = datetime.now() - bot_stats["start_time"]
        stats_text = f"""
📊 **Bot Statistics** 📊

🔍 **Total Searches:** {bot_stats['total_searches']}
⏰ **Bot Uptime:** {str(uptime).split('.')[0]}
👥 **Active Users:** {len(search_history)}
🚀 **Started:** {bot_stats['start_time'].strftime('%Y-%m-%d %H:%M:%S')}

📈 **Your Stats:**
• Searches made: {len(search_history.get(user_id, []))}
        """
        bot.send_message(call.message.chat.id, stats_text, parse_mode='Markdown')
    
    elif call.data == "history":
        bot.answer_callback_query(call.id)
        user_history = search_history.get(user_id, [])
        if not user_history:
            bot.send_message(call.message.chat.id, "📋 No search history found. Start by searching a mobile number!")
        else:
            history_text = "📋 **Your Recent Searches:**\n\n"
            for i, entry in enumerate(reversed(user_history[-5:]), 1):
                status = "✅" if entry['result_found'] else "❌"
                history_text += f"{i}. {status} {entry['number']} - {entry['timestamp']}\n"
            bot.send_message(call.message.chat.id, history_text, parse_mode='Markdown')
    
    
    elif call.data == "help":
        bot.answer_callback_query(call.id)
        help_text = """
❓ **Complete Help Guide** ❓

📱 **How to Search Numbers:**
• **Direct:** Just send `9876543210`
• **Command:** Use `/check 9876543210`
• **Formats:** 9876543210, +919876543210, 91-9876543210

🔧 **Available Commands:**
• `/start` - Show main menu with all options
• `/help` - Show this detailed help guide
• `/check <number>` - Search specific mobile number
• `/admin` - Admin panel (admin only)
• `/cancel` - Cancel any ongoing admin action

📊 **Using the Bot:**
• **📈 Statistics** - View your search stats & bot uptime
• **📋 History** - See your last 10 searches with results
• **💎 Subscription** - View/upgrade your plan
• **📊 My Subscription** - Check plan details & get your ID

💎 **Subscription System:**
• **🆓 Free Plan:** 0 searches/day (must upgrade)
• **🔍 Single Search:** ₹100 for 1 search (24 hours)
• **👑 Lifetime Plan:** ₹8000 for unlimited searches forever

💳 **How to Upgrade:**
1. Click "💎 Subscription" button
2. Choose your preferred plan
3. Contact @CRAZYPANEL1 directly for payment details
4. Get activated within 24 hours

🔍 **What You Get:**
• **Name** of the number holder
• **Father's Name** (if available)
• **Address** with full location details
• **Alternative Numbers** (if linked)
• **Circle/State** information
• **Email** (if available)
• **Adhar number**


💡 **Pro Tips:**
• Use "📊 My Subscription" to find your User ID
• Share your User ID with admin for quick activation
• Check "📋 History" to see successful vs failed searches
• Lifetime plan = best value for regular users

🆘 **Support:**
• Contact: @CRAZYPANEL1
• Payment Issues: Send screenshot to admin
• Technical Help: Use /start and try again

🚀 **Quick Start:**
1. Send any mobile number to try it out
2. Check your free plan status
3. Upgrade when you need more searches!
        """
        bot.send_message(call.message.chat.id, help_text, parse_mode='Markdown')
    
    
    
    
    elif call.data == "admin_panel":
        bot.answer_callback_query(call.id)
        if not is_admin_by_user_id(call.from_user.id, call.from_user.username):
            bot.send_message(call.message.chat.id, "❌ Access Denied! You are not authorized.")
            return
        admin_text = """
👑 **ADMIN PANEL** 👑
Welcome @CRAZYPANEL1!

🛠️ **Admin Controls Available:**
• View all users and their info
• Access complete bot statistics
• View all search history
• Reset bot statistics
• Broadcast messages to all users
• Bot control and management

Select an option below:
        """
        bot.send_message(call.message.chat.id, admin_text, reply_markup=create_admin_keyboard(), parse_mode='Markdown')
    
    elif call.data == "admin_users":
        bot.answer_callback_query(call.id)
        if not is_admin_by_user_id(call.from_user.id, call.from_user.username):
            bot.send_message(call.message.chat.id, "❌ Access Denied!")
            return
        
        users_text = "👥 **ALL USERS INFO** 👥\n\n"
        if not search_history:
            users_text += "No users have used the bot yet."
        else:
            for i, (user_id, history) in enumerate(search_history.items(), 1):
                users_text += f"**User {i}:**\n"
                users_text += f"🆔 ID: `{user_id}`\n"
                users_text += f"🔍 Searches: {len(history)}\n"
                if history:
                    users_text += f"📅 Last Search: {history[-1]['timestamp']}\n"
                    users_text += f"📞 Last Number: {history[-1]['number']}\n"
                users_text += "\n" + "─" * 25 + "\n\n"
        
        bot.send_message(call.message.chat.id, users_text, parse_mode='Markdown')
    
    elif call.data == "admin_stats":
        bot.answer_callback_query(call.id)
        if not is_admin_by_user_id(call.from_user.id, call.from_user.username):
            bot.send_message(call.message.chat.id, "❌ Access Denied!")
            return
        
        uptime = datetime.now() - bot_stats["start_time"]
        total_user_searches = sum(len(history) for history in search_history.values())
        
        stats_text = f"""
📊 **COMPLETE BOT STATISTICS** 📊

🤖 **Bot Info:**
• Bot Name: Mobile Number Lookup Bot
• Admin: @{ADMIN_USERNAME}
• Version: 2.0 (Admin Edition)

📈 **Usage Stats:**
• Total Searches: {bot_stats['total_searches']}
• Total Users: {len(search_history)}
• Active Sessions: {len(search_history)}
• Average Searches per User: {total_user_searches/len(search_history) if search_history else 0:.1f}

⏰ **Time Stats:**
• Bot Started: {bot_stats['start_time'].strftime('%Y-%m-%d %H:%M:%S')}
• Current Uptime: {str(uptime).split('.')[0]}
• Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

🔍 **Search Stats:**
• Successful Searches: {sum(1 for history in search_history.values() for entry in history if entry['result_found'])}
• Failed Searches: {sum(1 for history in search_history.values() for entry in history if not entry['result_found'])}
        """
        bot.send_message(call.message.chat.id, stats_text, parse_mode='Markdown')
    
    elif call.data == "admin_history":
        bot.answer_callback_query(call.id)
        if not is_admin_by_user_id(call.from_user.id, call.from_user.username):
            bot.send_message(call.message.chat.id, "❌ Access Denied!")
            return
        
        history_text = "🗂️ **ALL SEARCH HISTORY** 🗂️\n\n"
        if not search_history:
            history_text += "No search history available."
        else:
            for user_id, history in search_history.items():
                history_text += f"👤 **User ID:** `{user_id}`\n"
                for entry in history[-3:]:  # Show last 3 searches per user
                    status = "✅" if entry['result_found'] else "❌"
                    history_text += f"  {status} {entry['number']} - {entry['timestamp']}\n"
                history_text += "\n"
        
        bot.send_message(call.message.chat.id, history_text, parse_mode='Markdown')
    
    elif call.data == "admin_subscriptions":
        bot.answer_callback_query(call.id)
        if not is_admin_by_user_id(call.from_user.id, call.from_user.username):
            bot.send_message(call.message.chat.id, "❌ Access Denied!")
            return
        
        subs_text = "💎 **SUBSCRIPTION MANAGEMENT** 💎\n\n"
        if not user_subscriptions:
            subs_text += "No subscription users found."
        else:
            total_revenue = 0
            plan_counts = {"free": 0, "single": 0, "lifetime": 0}
            
            for user_id, sub_data in user_subscriptions.items():
                plan_counts[sub_data["plan"]] += 1
                total_revenue += sub_data.get("payment_amount", 0)
            
            subs_text += f"📊 **Summary:**\n"
            subs_text += f"👥 Total Users: {len(user_subscriptions)}\n"
            subs_text += f"💰 Total Revenue: ₹{total_revenue}\n\n"
            
            subs_text += f"📋 **Plan Distribution:**\n"
            subs_text += f"🆓 Free: {plan_counts['free']} users\n"
            subs_text += f"🔍 Single: {plan_counts['single']} users\n"
            subs_text += f"👑 Lifetime: {plan_counts['lifetime']} users\n\n"
            
            subs_text += f"👤 **Recent Subscribers:**\n"
            # Show last 5 paid subscribers
            paid_users = [(uid, data) for uid, data in user_subscriptions.items() if data["plan"] != "free"]
            paid_users.sort(key=lambda x: x[1].get("created_date", datetime.min), reverse=True)
            
            for i, (user_id, sub_data) in enumerate(paid_users[:5], 1):
                plan_emoji = {"single": "🔍", "lifetime": "👑"}.get(sub_data["plan"], "❓")
                subs_text += f"{i}. {plan_emoji} @{sub_data.get('username', 'N/A')} - {sub_data['plan'].title()} (₹{sub_data.get('payment_amount', 0)})\n"
                subs_text += f"   📅 {sub_data.get('created_date', 'N/A')}\n"
        
        bot.send_message(call.message.chat.id, subs_text, parse_mode='Markdown')
    
    elif call.data == "admin_reset":
        bot.answer_callback_query(call.id)
        if not is_admin_by_user_id(call.from_user.id, call.from_user.username):
            bot.send_message(call.message.chat.id, "❌ Access Denied!")
            return
        
        # Reset statistics
        bot_stats["total_searches"] = 0
        bot_stats["start_time"] = datetime.now()
        search_history.clear()
        
        bot.send_message(call.message.chat.id, "🔄 **Bot statistics have been reset!**\n\nAll search history and statistics have been cleared.", parse_mode='Markdown')
    
    elif call.data == "admin_add_sub":
        bot.answer_callback_query(call.id)
        if not is_admin_by_user_id(call.from_user.id, call.from_user.username):
            bot.send_message(call.message.chat.id, "❌ Access Denied!")
            return
        
        add_sub_text = """
➕ **ADD SUBSCRIPTION** ➕

🎯 **How to add subscription:**
1. Click the plan type below
2. Send user ID when prompted
3. Subscription will be activated instantly

💡 **To find User ID:**
- Ask user to send any message to bot
- Check admin panel → All Users
- Copy the user ID from there

Select plan to add:
        """
        bot.send_message(call.message.chat.id, add_sub_text, reply_markup=create_admin_sub_keyboard(), parse_mode='Markdown')
    
    elif call.data.startswith("admin_sub_"):
        bot.answer_callback_query(call.id)
        if not is_admin_by_user_id(call.from_user.id, call.from_user.username):
            bot.send_message(call.message.chat.id, "❌ Access Denied!")
            return
        
        plan_type = call.data.replace("admin_sub_", "")
        plan_info = subscription_plans[plan_type]
        
        # Set admin in subscription mode with plan type
        admin_subscription_mode[call.from_user.id] = {
            "plan": plan_type,
            "price": plan_info["price"]
        }
        
        plan_names = {
            "single": "🔍 Single Search",
            "lifetime": "👑 Lifetime Plan"
        }
        
        prompt_text = f"""
➕ **Adding {plan_names[plan_type]} (₹{plan_info['price']})**

📝 **Send the User ID** of the person you want to give this subscription to.

💡 **Example:** `123456789`

❌ **Send /cancel to abort**
        """
        bot.send_message(call.message.chat.id, prompt_text, parse_mode='Markdown')
    
    elif call.data == "admin_cancel_sub":
        bot.answer_callback_query(call.id)
        if call.from_user.id in admin_subscription_mode:
            del admin_subscription_mode[call.from_user.id]
        bot.send_message(call.message.chat.id, "❌ **Subscription addition cancelled.**", reply_markup=create_admin_keyboard(), parse_mode='Markdown')
    
    elif call.data == "admin_broadcast":
        bot.answer_callback_query(call.id)
        if not is_admin_by_user_id(call.from_user.id, call.from_user.username):
            bot.send_message(call.message.chat.id, "❌ Access Denied!")
            return
        
        # Set broadcast mode for admin
        broadcast_mode[call.from_user.id] = True
        
        cancel_keyboard = types.InlineKeyboardMarkup()
        cancel_keyboard.add(types.InlineKeyboardButton("❌ Cancel Broadcast", callback_data="cancel_broadcast"))
        
        bot.send_message(call.message.chat.id, "📢 **Broadcast Mode Activated!**\n\n✍️ **Send your message now** and it will be broadcasted to all bot users.\n\n📊 **Users to receive:** " + str(len(search_history)) + " users", reply_markup=cancel_keyboard, parse_mode='Markdown')
    
    elif call.data == "admin_control":
        bot.answer_callback_query(call.id)
        if not is_admin_by_user_id(call.from_user.id, call.from_user.username):
            bot.send_message(call.message.chat.id, "❌ Access Denied!")
            return
        
        control_text = """
🛠️ **BOT CONTROL PANEL** 🛠️

🔧 **Available Controls:**
• Bot is currently running normally
• All systems operational
• API connection active
• Database functioning

⚙️ **Admin Commands:**
• /admin - Access admin panel
• /start - Restart bot interface
• /check <number> - Test number lookup

📊 **Current Status:** ✅ Online
🔋 **Performance:** Optimal
        """
        bot.send_message(call.message.chat.id, control_text, parse_mode='Markdown')
    
    elif call.data == "cancel_broadcast":
        bot.answer_callback_query(call.id)
        if call.from_user.id in broadcast_mode:
            del broadcast_mode[call.from_user.id]
        bot.send_message(call.message.chat.id, "❌ **Broadcast cancelled!**\n\nReturning to admin panel...", reply_markup=create_admin_keyboard(), parse_mode='Markdown')
    
    elif call.data == "subscription":
        bot.answer_callback_query(call.id)
        subscription = get_user_subscription(user_id)
        plan_info = subscription_plans[subscription["plan"]]
        
        if subscription["plan"] == "free":
            plan_emoji = "🆓"
            plan_name = "Free Plan"
        elif subscription["plan"] == "single":
            plan_emoji = "🔍"
            plan_name = "Single Search"
        else:
            plan_emoji = "👑"
            plan_name = "Lifetime Plan"
        
        expires_text = ""
        if subscription["expires"]:
            expires_text = f"\n📅 **Expires:** {subscription['expires'].strftime('%Y-%m-%d')}"
        
        subscription_text = f"""
💎 **Subscription Plans** 💎

{plan_emoji} **Current Plan:** {plan_name}
📊 **Daily Searches:** {subscription['searches_used']}/{plan_info['searches_per_day']}
💰 **Price:** ₹{plan_info['price']}{expires_text}

🆓 **Free Plan:** 0 searches/day
🔍 **Single Search:** ₹100 - 1 search (24 hours)
👑 **Lifetime Plan:** ₹8000 - Unlimited searches forever

🆔 **Your ID:** `{user_id}`
💡 **To upgrade:** Send your ID to @CRAZYPANEL1

Choose a plan below to upgrade:
        """
        bot.send_message(call.message.chat.id, subscription_text, reply_markup=create_subscription_keyboard(), parse_mode='Markdown')
    
    elif call.data == "my_subscription":
        bot.answer_callback_query(call.id)
        subscription = get_user_subscription(user_id)
        plan_info = subscription_plans[subscription["plan"]]
        
        status_text = f"""
📊 **Your Subscription Status** 📊

🆔 **Your ID:** `{user_id}`
📋 **Plan:** {subscription['plan'].title()}
🔍 **Daily Limit:** {plan_info['searches_per_day']} searches
📈 **Used Today:** {subscription['searches_used']} searches
⏰ **Remaining:** {plan_info['searches_per_day'] - subscription['searches_used']} searches

💰 **Plan Cost:** ₹{plan_info['price']}

💡 **To Upgrade Your Subscription:**
1. 📋 **Copy your ID:** `{user_id}`
2. 💬 **Send this ID to admin:** @CRAZYPANEL1
3. 💳 **Admin will help you with payment**
4. ⚡ **Instant activation after payment**

📞 **Contact Admin:** @CRAZYPANEL1
• Send your ID: `{user_id}`
• Choose your plan (Single ₹100 or Lifetime ₹8000)
• Admin will provide payment details
• मैन्युअल एक्टिवेशन के लिए एडमिन को अपना ID भेजें
        """
        
        if subscription["expires"]:
            status_text += f"\n📅 **Expires:** {subscription['expires'].strftime('%Y-%m-%d %H:%M')}"
        
        bot.send_message(call.message.chat.id, status_text, parse_mode='Markdown')
    
    elif call.data == "plan_single":
        bot.answer_callback_query(call.id)
        maintenance_text = """
🔧 **Payment System Under Maintenance** 🔧

🔍 **Single Search Plan - ₹100**

⚠️ **सिस्टम मेंटेनेंस में है!**
• Automatic payment currently disabled
• हमारा ऑटोमेटिक पेमेंट सिस्टम बंद है
• फिलहाल एडमिन के जरिए ही एक्टिवेशन होगा

✅ **What you can do:**
• Contact admin for manual payment & activation
• Admin will guide you through the payment process
• एडमिन आपको पेमेंट की पूरी जानकारी देंगे

👨‍💼 **Contact Admin:**
• Telegram: @CRAZYPANEL1
• Direct message for instant help
• मैन्युअल एक्टिवेशन के लिए एडमिन से बात करें

🙏 **Sorry for the inconvenience!**
        """
        bot.send_message(call.message.chat.id, maintenance_text, parse_mode='Markdown')
    
    elif call.data == "plan_lifetime":
        bot.answer_callback_query(call.id)
        maintenance_text = """
🔧 **Payment System Under Maintenance** 🔧

👑 **Lifetime Plan - ₹8000**

⚠️ **सिस्टम मेंटेनेंस में है!**
• Automatic payment currently disabled
• हमारा ऑटोमेटिक पेमेंट सिस्टम बंद है
• फिलहाल एडमिन के जरिए ही एक्टिवेशन होगा

✅ **What you can do:**
• Contact admin for manual payment & activation
• Admin will guide you through the payment process
• एडमिन आपको पेमेंट की पूरी जानकारी देंगे

👨‍💼 **Contact Admin:**
• Telegram: @CRAZYPANEL1
• Direct message for instant help
• मैन्युअल एक्टिवेशन के लिए एडमिन से बात करें

💎 **Lifetime Plan Benefits:**
• Unlimited searches forever
• No monthly payments
• Priority support
• Best value for money

🙏 **Sorry for the inconvenience!**
        """
        bot.send_message(call.message.chat.id, maintenance_text, parse_mode='Markdown')
    
    elif call.data == "back_main":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "🔙 Returning to main menu...", reply_markup=create_main_keyboard())
    
    # Command suggestion handlers
    elif call.data == "cmd_start":
        bot.answer_callback_query(call.id)
        send_welcome(call.message)
    
    elif call.data == "cmd_check":
        bot.answer_callback_query(call.id)
        check_text = """
🔍 **Ready to Check Mobile Number!** 🔍

📱 **Send me a mobile number in any of these formats:**
• `9876543210`
• `+919876543210`
• `91-9876543210`
• `9876 543 210`

💡 **What you'll get:**
• Name of the number holder
• Father's name (if available)
• Complete address with location
• Alternative numbers (if linked)
• Circle/State information
• Email address (if available)
• Adhar number

🚀 **Just type the number and send it!**

📊 **Your current plan:** Check "💎 Subscription" for details
        """
        bot.send_message(call.message.chat.id, check_text, parse_mode='Markdown')
    
    elif call.data == "cmd_help":
        bot.answer_callback_query(call.id)
        # Trigger the help section from the existing help handler
        help_text = """
❓ **Complete Help Guide** ❓

📱 **How to Search Numbers:**
• **Direct:** Just send `9876543210`
• **Command:** Use `/check 9876543210`
• **Formats:** 9876543210, +919876543210, 91-9876543210

🔧 **Available Commands:**
• `/start` - Show main menu with all options
• `/help` - Show this detailed help guide
• `/check <number>` - Search specific mobile number
• `/admin` - Admin panel (admin only)
• `/cancel` - Cancel any ongoing admin action

📊 **Using the Bot:**
• **📈 Statistics** - View your search stats & bot uptime
• **📋 History** - See your last 10 searches with results
• **💎 Subscription** - View/upgrade your plan
• **📊 My Subscription** - Check plan details & get your ID

💎 **Subscription System:**
• **🆓 Free Plan:** 0 searches/day (must upgrade)
• **🔍 Single Search:** ₹100 for 1 search (24 hours)
• **👑 Lifetime Plan:** ₹8000 for unlimited searches forever

💳 **How to Upgrade:**
1. Click "💎 Subscription" button
2. Choose your preferred plan
3. Contact @CRAZYPANEL1 directly for payment details
4. Get activated within 24 hours

🔍 **What You Get:**
• **Name** of the number holder
• **Father's Name** (if available)
• **Address** with full location details
• **Alternative Numbers** (if linked)
• **Circle/State** information
• **Email** (if available)
• **Adhar number**

💡 **Pro Tips:**
• Use "📊 My Subscription" to find your User ID
• Share your User ID with admin for quick activation
• Check "📋 History" to see successful vs failed searches
• Lifetime plan = best value for regular users

🆘 **Support:**
• Contact: @CRAZYPANEL1
• Payment Issues: Send screenshot to admin
• Technical Help: Use /start and try again

🚀 **Quick Start:**
1. Send any mobile number to try it out
2. Check your free plan status
3. Upgrade when you need more searches!
        """
        bot.send_message(call.message.chat.id, help_text, parse_mode='Markdown')
    
    elif call.data == "cmd_admin":
        bot.answer_callback_query(call.id)
        admin_panel(call.message)
    
    elif call.data == "cmd_mystats":
        bot.answer_callback_query(call.id)
        my_stats(call.message)
    
    elif call.data == "cmd_pricing":
        bot.answer_callback_query(call.id)
        show_pricing(call.message)
    
    elif call.data == "cmd_contact":
        bot.answer_callback_query(call.id)
        contact_info(call.message)
    
    elif call.data == "cmd_cancel":
        bot.answer_callback_query(call.id)
        cancel_admin_action(call.message)

def create_command_suggestions_keyboard():
    """Create command suggestions keyboard."""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("/start", callback_data="cmd_start"),
        types.InlineKeyboardButton("/check", callback_data="cmd_check")
    )
    keyboard.add(
        types.InlineKeyboardButton("/help", callback_data="cmd_help"),
        types.InlineKeyboardButton("/admin", callback_data="cmd_admin")
    )
    keyboard.add(
        types.InlineKeyboardButton("/mystats", callback_data="cmd_mystats"),
        types.InlineKeyboardButton("/pricing", callback_data="cmd_pricing")
    )
    keyboard.add(
        types.InlineKeyboardButton("/contact", callback_data="cmd_contact"),
        types.InlineKeyboardButton("/cancel", callback_data="cmd_cancel")
    )
    keyboard.add(
        types.InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_main")
    )
    return keyboard

@bot.message_handler(func=lambda m: True)
def handle_all_messages(message):
    # Handle command suggestions when user types just "/"
    if message.text and message.text.strip() == "/":
        suggestions_text = """
💡 **Available Commands** 💡

🤖 **Basic Commands:**
• `/start` - Show main menu and welcome message
• `/help` - Complete help guide with instructions
• `/check <number>` - Search specific mobile number

📊 **Information Commands:**
• `/mystats` - Your personal statistics
• `/pricing` - View subscription plans and pricing
• `/contact` - Get support and contact info

🛠️ **Utility Commands:**
• `/cancel` - Cancel any ongoing admin action
• `/admin` - Admin panel (admin only)

💡 **Quick Tip:** You can also send a mobile number directly without any command!

**Examples:**
• `9876543210`
• `+919876543210`
• `/check 9876543210`

Click any command below to use it! 👇
        """
        bot.send_message(message.chat.id, suggestions_text, reply_markup=create_command_suggestions_keyboard(), parse_mode='Markdown')
        return
    
    # Check if admin is in subscription mode
    if message.from_user.id in admin_subscription_mode and is_admin_by_user_id(message.from_user.id, message.from_user.username):
        # Handle subscription addition
        if message.text and message.text.strip() == "/cancel":
            del admin_subscription_mode[message.from_user.id]
            bot.reply_to(message, "❌ **Subscription addition cancelled.**", reply_markup=create_admin_keyboard(), parse_mode='Markdown')
            return
        
        try:
            target_user_id = int(message.text.strip())
        except (ValueError, AttributeError):
            bot.reply_to(message, "❌ **Invalid User ID!** Please send a valid numeric user ID.\n\n💡 Example: `123456789`\n\n❌ Send /cancel to abort", parse_mode='Markdown')
            return
        
        # Get subscription details
        sub_details = admin_subscription_mode[message.from_user.id]
        plan = sub_details["plan"]
        price = sub_details["price"]
        
        # Try to get user info from existing data or create placeholder
        target_username = "N/A"
        target_first_name = "N/A"
        
        # Check if user exists in subscriptions
        if target_user_id in user_subscriptions:
            target_username = user_subscriptions[target_user_id].get("username", "N/A")
            target_first_name = user_subscriptions[target_user_id].get("first_name", "N/A")
        
        # Add subscription
        user_data = add_subscription_user(target_user_id, target_username, target_first_name, plan, price)
        
        # Remove admin from subscription mode
        del admin_subscription_mode[message.from_user.id]
        
        # Send confirmation
        plan_names = {
            "single": "🔍 Single Search",
            "lifetime": "👑 Lifetime Plan"
        }
        
        confirmation_text = f"""
✅ **Subscription Added Successfully!** ✅

👤 **User ID:** `{target_user_id}`
📋 **Plan:** {plan_names[plan]}
💰 **Amount:** ₹{price}
📅 **Expires:** {user_data['expires'].strftime('%Y-%m-%d %H:%M') if user_data['expires'] else 'Never'}

🎉 **The user can now use their subscription immediately!**
        """
        
        bot.send_message(message.chat.id, confirmation_text, reply_markup=create_admin_keyboard(), parse_mode='Markdown')
        
        # Notify the user if possible
        try:
            user_notification = f"""
🎉 **Subscription Activated!** 🎉

✅ **Plan:** {plan_names[plan]}
💰 **Value:** ₹{price}
📅 **Valid Until:** {user_data['expires'].strftime('%Y-%m-%d') if user_data['expires'] else 'Forever'}

🚀 **You can now use the bot with your new subscription!**

💬 **Activated by:** Admin @{ADMIN_USERNAME}
            """
            bot.send_message(target_user_id, user_notification, parse_mode='Markdown')
        except Exception as e:
            print(f"Could not notify user {target_user_id}: {e}")
        
        return
    
    # Check if admin is in broadcast mode
    elif message.from_user.id in broadcast_mode and is_admin_by_user_id(message.from_user.id, message.from_user.username):
        # Handle broadcast message
        broadcast_text = message.text
        if not broadcast_text:
            bot.reply_to(message, "❌ Please send a text message to broadcast.")
            return
        
        # Remove admin from broadcast mode
        del broadcast_mode[message.from_user.id]
        
        # Get all users to broadcast to
        users_to_broadcast = list(search_history.keys())
        successful_broadcasts = 0
        failed_broadcasts = 0
        
        # Send broadcast message to all users
        for user_id in users_to_broadcast:
            try:
                broadcast_message = f"📢 **Admin Broadcast Message:**\n\n{broadcast_text}\n\n─────────────────\n💬 From: @{ADMIN_USERNAME}"
                bot.send_message(user_id, broadcast_message, parse_mode='Markdown')
                successful_broadcasts += 1
            except Exception as e:
                failed_broadcasts += 1
        
        # Send confirmation to admin
        confirmation_text = f"""
📢 **Broadcast Complete!** 📢

✅ **Successfully sent to:** {successful_broadcasts} users
❌ **Failed to send to:** {failed_broadcasts} users
📊 **Total users:** {len(users_to_broadcast)} users

**Your message:**
"{broadcast_text}"
        """
        bot.send_message(message.chat.id, confirmation_text, reply_markup=create_admin_keyboard(), parse_mode='Markdown')
        return
    
    # If user sends a (single) number, auto-check it
    text = message.text or ""
    number = normalize_number(text)
    if number:
        # Check subscription limits
        can_search, limit_message = can_user_search(message.from_user.id)
        if not can_search:
            bot.reply_to(message, limit_message, reply_markup=create_subscription_keyboard())
            return
        
        # Use search credit
        use_search_credit(message.from_user.id)
        
        sent = bot.reply_to(message, f"🔍 Checking number: {number} ...")
        success, result = query_api(number)
        
        # Add to history
        add_to_history(message.from_user.id, number, success and "No data found" not in result)
        
        # Add subscription info to result
        subscription = get_user_subscription(message.from_user.id)
        plan_info = subscription_plans[subscription["plan"]]
        remaining = plan_info["searches_per_day"] - subscription["searches_used"]
        
        footer = f"\n\n📊 **Searches remaining today:** {remaining}/{plan_info['searches_per_day']}"
        if subscription["plan"] == "free":
            footer += f"\n🔍 **Single Search:** ₹100 | 👑 **Lifetime:** ₹8000"
        
        if success:
            bot.edit_message_text(chat_id=sent.chat.id, message_id=sent.message_id, text=f"📱 Result for {number}:\n\n{result}{footer}", parse_mode='Markdown')
        else:
            bot.edit_message_text(chat_id=sent.chat.id, message_id=sent.message_id, text=f"❌ Error querying API for {number}:\n\n{result}{footer}")
    else:
        suggestion_text = """
❓ **I didn't understand that!** ❓

📱 **Try these instead:**
• Send a mobile number: `9876543210`
• Use command: `/check 9876543210`
• Supported formats: 9876543210, +919876543210

💡 **Quick Suggestions:**
• Click "🔍 Check Number" to get started
• Use "❓ Help" for detailed instructions
• Check "💎 Subscription" to see your plan
• View "📋 History" for past searches

🚀 **Examples that work:**
• `9876543210`
• `+919876543210`
• `/check 9876543210`

Choose an option below or send a valid mobile number! 👇
        """
        bot.send_message(message.chat.id, suggestion_text, reply_markup=create_main_keyboard(), parse_mode='Markdown')

# Flask routes for webhook
@app.route('/', methods=['GET'])
def index():
    """Health check endpoint and server status page"""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Mobile Number Lookup Bot</title>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                margin: 0;
                padding: 0;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
            }
            .container {
                text-align: center;
                padding: 2rem;
                background: rgba(255, 255, 255, 0.1);
                border-radius: 20px;
                backdrop-filter: blur(10px);
                box-shadow: 0 8px 32px rgba(31, 38, 135, 0.37);
                border: 1px solid rgba(255, 255, 255, 0.18);
                max-width: 500px;
                margin: 20px;
            }
            .status-badge {
                background: #10b981;
                color: white;
                padding: 8px 16px;
                border-radius: 20px;
                font-size: 14px;
                font-weight: bold;
                display: inline-block;
                margin-bottom: 20px;
                animation: pulse 2s infinite;
            }
            @keyframes pulse {
                0% { transform: scale(1); }
                50% { transform: scale(1.05); }
                100% { transform: scale(1); }
            }
            h1 {
                font-size: 2.5rem;
                margin-bottom: 1rem;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
            }
            .bot-emoji {
                font-size: 4rem;
                margin-bottom: 1rem;
                animation: bounce 2s infinite;
            }
            @keyframes bounce {
                0%, 20%, 50%, 80%, 100% { transform: translateY(0); }
                40% { transform: translateY(-10px); }
                60% { transform: translateY(-5px); }
            }
            .info {
                background: rgba(255, 255, 255, 0.2);
                padding: 1.5rem;
                border-radius: 15px;
                margin: 20px 0;
                text-align: left;
            }
            .info h3 {
                margin-top: 0;
                color: #fbbf24;
            }
            .admin-info {
                background: rgba(16, 185, 129, 0.2);
                padding: 1rem;
                border-radius: 10px;
                margin-top: 20px;
            }
            .telegram-link {
                display: inline-block;
                background: #0088cc;
                color: white;
                padding: 12px 24px;
                border-radius: 25px;
                text-decoration: none;
                font-weight: bold;
                margin-top: 20px;
                transition: all 0.3s ease;
            }
            .telegram-link:hover {
                background: #006699;
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            }
            .stats {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
                gap: 15px;
                margin-top: 20px;
            }
            .stat-item {
                background: rgba(255, 255, 255, 0.1);
                padding: 15px;
                border-radius: 10px;
                text-align: center;
            }
            .stat-number {
                font-size: 1.5rem;
                font-weight: bold;
                color: #fbbf24;
            }
            .stat-label {
                font-size: 0.9rem;
                opacity: 0.8;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="status-badge">🟢 SERVER IS READY</div>
            <div class="bot-emoji">🤖</div>
            <h1>Mobile Number Lookup Bot</h1>
            <p style="font-size: 1.2rem; opacity: 0.9;">Your Telegram bot is running successfully!</p>
            
            <div class="info">
                <h3>📱 Bot Features</h3>
                <ul style="text-align: left;">
                    <li>🔍 Mobile number lookup</li>
                    <li>📊 Search history tracking</li>
                    <li>💎 Subscription management</li>
                    <li>👑 Admin panel</li>
                </ul>
            </div>
            
            <div class="stats">
                <div class="stat-item">
                    <div class="stat-number">✅</div>
                    <div class="stat-label">Online</div>
                </div>
                <div class="stat-item">
                    <div class="stat-number">🚀</div>
                    <div class="stat-label">Ready</div>
                </div>
                <div class="stat-item">
                    <div class="stat-number">⚡</div>
                    <div class="stat-label">Fast</div>
                </div>
            </div>
            
            <div class="admin-info">
                <strong>👑 Admin:</strong> @""" + ADMIN_USERNAME + """<br>
                <strong>🌐 Status:</strong> All systems operational<br>
                <strong>📡 API:</strong> Connected
            </div>
            
            <a href="https://t.me/""" + BOT_TOKEN.split(':')[0] + """" class="telegram-link" target="_blank">
                📱 Open Bot in Telegram
            </a>
            
            <p style="margin-top: 30px; opacity: 0.7; font-size: 0.9rem;">
                🔧 Powered by Flask & Python | 🚀 Deployed Successfully
            </p>
        </div>
    </body>
    </html>
    """

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle incoming webhook requests from Telegram"""
    try:
        json_str = request.get_data().decode('UTF-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return jsonify({"status": "ok"})
    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Additional health check endpoint"""
    uptime = datetime.now() - bot_stats["start_time"]
    return jsonify({
        "status": "healthy",
        "uptime": str(uptime).split('.')[0],
        "total_searches": bot_stats['total_searches'],
        "active_users": len(search_history),
        "timestamp": datetime.now().isoformat()
    })

@app.route('/status', methods=['GET'])
def status_check():
    """Simple status endpoint for deployment platforms"""
    return jsonify({
        "status": "online",
        "message": "Server is ready! 🚀",
        "bot_running": True,
        "port": PORT
    })

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    """Set webhook URL (for manual setup if needed)"""
    if WEBHOOK_URL:
        try:
            webhook_url = f"{WEBHOOK_URL}/webhook"
            bot.remove_webhook()
            bot.set_webhook(url=webhook_url)
            return jsonify({
                "status": "success",
                "message": f"Webhook set to {webhook_url}"
            })
        except Exception as e:
            return jsonify({
                "status": "error",
                "message": str(e)
            }), 500
    else:
        return jsonify({
            "status": "error",
            "message": "WEBHOOK_URL environment variable not set"
        }), 400

def setup_webhook():
    """Setup webhook on startup"""
    if WEBHOOK_URL:
        try:
            webhook_url = f"{WEBHOOK_URL}/webhook"
            bot.remove_webhook()
            bot.set_webhook(url=webhook_url)
            print(f"✅ Webhook set to: {webhook_url}")
        except Exception as e:
            print(f"❌ Failed to set webhook: {e}")
    else:
        print("⚠️ WEBHOOK_URL not set, running in polling mode for development")

def start_bot_polling():
    """Start bot in polling mode (runs in a separate thread)"""
    print("🔄 Starting bot polling in background...")
    try:
        bot.infinity_polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        print(f"Bot polling stopped with error: {e}")
        # Restart the bot
        import time
        time.sleep(5)
        start_bot_polling()

if __name__ == "__main__":
    print("🤖 Mobile Number Lookup Bot Starting...")
    print(f"👑 Admin: @{ADMIN_USERNAME}")
    print("📱 Bot is ready! Send /start to begin.")
    
    # Always run Flask app to bind to port (required for deployment platforms)
    if WEBHOOK_URL:
        print("🌐 Running in webhook mode for production...")
        setup_webhook()
        print(f"🚀 Flask app starting on port {PORT}")
        app.run(host='0.0.0.0', port=PORT, debug=False)
    else:
        print("🔄 Running in hybrid mode (Flask + Polling)...")
        print(f"🌐 Flask server will run on port {PORT}")
        print("🤖 Bot will use polling for Telegram updates")
        
        # Start bot polling in a separate thread
        import threading
        polling_thread = threading.Thread(target=start_bot_polling, daemon=True)
        polling_thread.start()
        
        # Run Flask app (this keeps the main thread alive and binds to port)
        print(f"🚀 Flask app starting on port {PORT}")
        app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)
