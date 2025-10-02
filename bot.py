
import telebot
from telebot import types
import requests
from requests.exceptions import ReadTimeout, ConnectionError, RequestException
import re
import time
import os
import json
import logging
import threading
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template_string, send_from_directory
from typing import Optional, Tuple, Dict, Any

# Configure logging with better performance
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# Optimize logging for better performance
logging.getLogger('werkzeug').setLevel(logging.WARNING)  # Reduce Flask logs
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

# Suppress some noisy logs
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('requests').setLevel(logging.WARNING)

# === CONFIGURATION ===
class Config:
    """Configuration class for better organization"""
    
    def __init__(self):
        # Bot Configuration
        self.BOT_TOKEN = os.getenv("BOT_TOKEN")
        self.CHAT_ID = os.getenv("CHAT_ID")
        self.ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "CRAZYPANEL1")
        self.ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "7490634345"))
        
        # API Configuration
        self.API_KEY = os.getenv("API_KEY")
        self.API_ENDPOINT_TEMPLATE = f"https://flipcartstore.serv00.net/INFO.php?api_key={self.API_KEY}&mobile={{number}}"
        
        # Server Configuration
        self.WEBHOOK_URL = os.getenv("WEBHOOK_URL")
        self.PORT = int(os.getenv("PORT", 5000))
        
        # Request Configuration
        self.REQUEST_TIMEOUT = 15
        self.MAX_RETRIES = 3
        self.RETRY_DELAY = 2.0
        
        # File Configuration
        self.SUBSCRIPTION_FILE = "subscriptions.json"
        
        # Validate required environment variables
        self._validate_config()
    
    def _validate_config(self):
        """Validate required configuration"""
        if not self.BOT_TOKEN:
            raise ValueError("BOT_TOKEN environment variable is required")
        if not self.API_KEY:
            raise ValueError("API_KEY environment variable is required")
        
        logger.info(f"✅ Configuration loaded successfully")
        logger.info(f"👑 Admin: @{self.ADMIN_USERNAME} (ID: {self.ADMIN_USER_ID})")
        logger.info(f"🌐 Webhook: {'Enabled' if self.WEBHOOK_URL else 'Disabled (Polling mode)'}")
        
        # Validate API key format
        if self.API_KEY and len(self.API_KEY) < 5:
            logger.warning(f"⚠️ API key seems too short: {len(self.API_KEY)} characters")
        elif self.API_KEY:
            logger.info(f"🔑 API key loaded: {self.API_KEY[:3]}***{self.API_KEY[-2:] if len(self.API_KEY) > 5 else '***'}")

# Initialize configuration
config = Config()

# === SUBSCRIPTION MANAGEMENT ===
class SubscriptionManager:
    """Manages user subscriptions with thread-safe operations"""
    
    def __init__(self):
        self.subscription_file = config.SUBSCRIPTION_FILE
        self.users = {}
        self._lock = threading.Lock()
        self._last_loaded = None
        self.load_subscriptions()
        self._ensure_admin_subscription()
    
    def load_subscriptions(self) -> None:
        """Load subscription data from JSON file with error handling"""
        try:
            if not os.path.exists(self.subscription_file):
                logger.info("📄 No subscription file found, starting fresh")
                self.users = {}
                return
            
            with open(self.subscription_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                loaded_users = {}
                
                # Convert string dates back to datetime objects
                for user_id_str, sub_data in data.get("users", {}).items():
                    try:
                        user_id = int(user_id_str)
                        
                        # Convert date strings back to datetime objects
                        if sub_data.get("expires"):
                            sub_data["expires"] = datetime.fromisoformat(sub_data["expires"])
                        if sub_data.get("last_reset"):
                            sub_data["last_reset"] = datetime.fromisoformat(sub_data["last_reset"]).date()
                        if sub_data.get("created_date"):
                            sub_data["created_date"] = datetime.fromisoformat(sub_data["created_date"])
                        
                        loaded_users[user_id] = sub_data
                        logger.debug(f"✅ Loaded user {user_id}: {sub_data.get('plan', 'unknown')} plan")
                        
                    except (ValueError, TypeError) as e:
                        logger.warning(f"⚠️ Skipping invalid user data for {user_id_str}: {e}")
                        continue
                
                self.users = loaded_users
                self._last_loaded = datetime.now()
                logger.info(f"📊 Successfully loaded {len(loaded_users)} user subscriptions")
                
                # Debug: Print loaded users for verification
                for user_id, sub_data in loaded_users.items():
                    plan = sub_data.get('plan', 'unknown')
                    expires = sub_data.get('expires', 'Never')
                    admin_status = " (ADMIN)" if sub_data.get('is_admin', False) else ""
                    logger.info(f"  👤 User {user_id}: {plan} plan (expires: {expires}){admin_status}")
                
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.error(f"❌ Error loading subscriptions: {e}")
            self.users = {}
            self._last_loaded = datetime.now()
        except Exception as e:
            logger.error(f"❌ Unexpected error loading subscriptions: {e}")
            self.users = {}
            self._last_loaded = datetime.now()
    
    def reload_if_needed(self) -> None:
        """Reload subscriptions if file has been modified"""
        try:
            if not os.path.exists(self.subscription_file):
                return
            
            file_mtime = datetime.fromtimestamp(os.path.getmtime(self.subscription_file))
            
            if self._last_loaded is None or file_mtime > self._last_loaded:
                logger.info("🔄 Subscription file modified, reloading...")
                self.load_subscriptions()
        except Exception as e:
            logger.warning(f"⚠️ Could not check file modification time: {e}")

    def save_subscriptions(self) -> bool:
        """Save subscription data to JSON file with thread safety"""
        with self._lock:
            try:
                # Convert datetime objects to strings for JSON serialization
                users_data = {}
                for user_id, sub_data in self.users.items():
                    users_data[str(user_id)] = sub_data.copy()
                    
                    # Convert datetime objects to ISO format strings
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
                        "version": "2.0",
                        "bot_version": "2.1"
                    }
                }
                
                # Create backup before saving
                if os.path.exists(self.subscription_file):
                    backup_file = f"{self.subscription_file}.backup"
                    try:
                        if os.path.exists(backup_file):
                            os.remove(backup_file)  # Remove old backup
                        os.rename(self.subscription_file, backup_file)
                        logger.debug(f"📋 Created backup: {backup_file}")
                    except Exception as backup_error:
                        logger.warning(f"⚠️ Backup creation failed: {backup_error}")
                
                with open(self.subscription_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                
                # Update last loaded time after successful save
                self._last_loaded = datetime.now()
                logger.info(f"💾 Saved {len(users_data)} user subscriptions")
                return True
                
            except Exception as e:
                logger.error(f"❌ Error saving subscriptions: {e}")
                return False

    def add_subscription_user(self, user_id: int, username: str, first_name: str, 
                            plan: str, payment_amount: int = 0) -> Dict[str, Any]:
        """Add or update user subscription with validation"""
        with self._lock:
            # Check if user is admin
            is_admin = (user_id == config.ADMIN_USER_ID) or \
                      (username and username.upper() == config.ADMIN_USERNAME.upper())
            
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
                user_data["expires"] = datetime.now() + timedelta(days=36500)  # 100 years
            
            self.users[user_id] = user_data
            self.save_subscriptions()
            
            logger.info(f"👤 Added/Updated subscription for user {user_id} ({username}): {plan} plan")
            return user_data
    
    def _ensure_admin_subscription(self):
        """Ensure admin has proper subscription"""
        admin_id = config.ADMIN_USER_ID
        if admin_id not in self.users:
            logger.info(f"👑 Creating admin subscription for ID: {admin_id}")
            self.add_subscription_user(
                admin_id, config.ADMIN_USERNAME, "Admin", "lifetime", 0
            )
        else:
            # Ensure existing admin has proper privileges
            admin_sub = self.users[admin_id]
            if admin_sub.get('plan') != 'lifetime' or not admin_sub.get('is_admin', False):
                logger.info(f"🔄 Updating admin subscription")
                admin_sub.update({
                    'plan': 'lifetime',
                    'is_admin': True,
                    'expires': datetime.now() + timedelta(days=36500),
                    'payment_amount': 0
                })
                self.save_subscriptions()
    
    def verify_subscription_persistence(self, user_id: int) -> bool:
        """Verify that a user's subscription persists after reload"""
        try:
            # Get current subscription
            current_sub = self.users.get(user_id)
            if not current_sub:
                return False
            
            # Force reload from file
            self.load_subscriptions()
            
            # Check if subscription still exists
            reloaded_sub = self.users.get(user_id)
            if not reloaded_sub:
                logger.error(f"❌ Subscription for user {user_id} lost after reload!")
                return False
            
            # Verify key fields match
            if (current_sub.get('plan') == reloaded_sub.get('plan') and
                current_sub.get('user_id') == reloaded_sub.get('user_id')):
                logger.info(f"✅ Subscription persistence verified for user {user_id}")
                return True
            else:
                logger.error(f"❌ Subscription data mismatch for user {user_id}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error verifying subscription persistence: {e}")
            return False

# Initialize subscription manager (will be done in background for faster startup)
subscription_manager = None

# Storage for search history and stats
search_history = {}  # user_id: [list of searches]
bot_stats = {"total_searches": 0, "start_time": datetime.now()}
broadcast_mode = {}  # user_id: True when admin is in broadcast mode
admin_subscription_mode = {}  # user_id: True when admin is adding subscription

# Subscription plans configuration
subscription_plans = {
    "free": {"searches_per_day": 0, "price": 0, "duration_days": 0},
    "single": {"searches_per_day": 1, "price": 100, "duration_days": 1},
    "lifetime": {"searches_per_day": 999, "price": 8000, "duration_days": 36500}
}


# Initialize bot with optimized settings
bot = telebot.TeleBot(config.BOT_TOKEN, parse_mode='Markdown', threaded=True)

# Configure bot to handle connection errors gracefully
telebot.apihelper.RETRY_ON_ERROR = True
telebot.apihelper.RETRY_TIMEOUT = 3
telebot.apihelper.MAX_RETRIES = 3
telebot.apihelper.READ_TIMEOUT = 30
telebot.apihelper.CONNECT_TIMEOUT = 15

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)

# Set template folder to current directory
app.template_folder = os.path.dirname(os.path.abspath(__file__))

# simple number validator: allow optional +, digits, 10-15 digits total
NUMBER_RE = re.compile(r'^\+?\d{10,15}$')

def normalize_number(text: str) -> Optional[str]:
    """Extract and normalize digits from input with improved validation"""
    if not text or not isinstance(text, str):
        return None
    
    text = text.strip()
    if not text:
        return None
    
    # Remove common separators and formatting
    cleaned = re.sub(r'[\s\-\(\)\.]', '', text)
    
    # Check for letters (invalid)
    if re.search(r'[A-Za-z]', cleaned):
        return None
    
    # Handle international format (+91, +1, etc.)
    if cleaned.startswith('+'):
        candidate = cleaned
    else:
        # Remove any leading non-digits
        candidate = re.sub(r'^\D+', '', cleaned)
    
    # Validate with regex
    if NUMBER_RE.match(candidate):
        return candidate
    
    # Fallback: extract just digits and validate length
    digits = re.sub(r'\D', '', cleaned)
    if 10 <= len(digits) <= 15:
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

def get_user_subscription(user_id: int, username: Optional[str] = None, first_name: Optional[str] = None) -> Dict[str, Any]:
    """Get user's current subscription status with improved handling"""
    
    # Wait for subscription manager to be initialized
    global subscription_manager
    if subscription_manager is None:
        # Fallback initialization if not ready
        subscription_manager = SubscriptionManager()
    
    # Reload subscriptions if file has been modified
    subscription_manager.reload_if_needed()
    
    # Check if user exists in subscription manager
    if user_id not in subscription_manager.users:
        logger.info(f"👤 New user detected: {user_id} ({username})")
        
        # Check if user is admin
        is_admin = is_admin_by_user_id(user_id, username)
        
        if is_admin:
            # Admin gets lifetime access
            logger.info(f"👑 Creating admin subscription for {user_id}")
            return subscription_manager.add_subscription_user(
                user_id, username or config.ADMIN_USERNAME, first_name or "Admin", "lifetime", 0
            )
        else:
            # New user gets free plan
            logger.info(f"🆓 Creating free subscription for {user_id}")
            return subscription_manager.add_subscription_user(
                user_id, username, first_name, "free", 0
            )
    
    subscription = subscription_manager.users[user_id]
    logger.debug(f"📋 Found existing subscription for {user_id}: {subscription.get('plan', 'unknown')} plan")
    
    # Update user details if provided
    updated = False
    if username and subscription.get("username") != username:
        subscription["username"] = username
        updated = True
        logger.debug(f"📝 Updated username for {user_id}: {username}")
    if first_name and subscription.get("first_name") != first_name:
        subscription["first_name"] = first_name
        updated = True
        logger.debug(f"📝 Updated first_name for {user_id}: {first_name}")
    
    # Check if subscription expired
    if subscription["expires"] and datetime.now() > subscription["expires"]:
        logger.warning(f"⏰ Subscription expired for {user_id}, downgrading to free")
        subscription["plan"] = "free"
        subscription["expires"] = None
        subscription["status"] = "expired"
        updated = True
    
    # Reset daily search count
    if subscription["last_reset"] != datetime.now().date():
        subscription["searches_used"] = 0
        subscription["last_reset"] = datetime.now().date()
        updated = True
        logger.debug(f"🔄 Reset daily search count for {user_id}")
    
    if updated:
        subscription_manager.save_subscriptions()
        logger.debug(f"💾 Saved updated subscription for {user_id}")
    
    return subscription

def can_user_search(user_id: int) -> Tuple[bool, str]:
    """Check if user can perform a search based on their subscription"""
    subscription = get_user_subscription(user_id)
    
    # Admin has unlimited access
    if subscription.get("is_admin", False):
        return True, ""
    
    plan = subscription_plans[subscription["plan"]]
    
    if subscription["searches_used"] >= plan["searches_per_day"]:
        return False, (
            f"❌ Daily limit reached! You've used {subscription['searches_used']}/{plan['searches_per_day']} searches.\n\n"
            f"🔍 **Single Search:** ₹100 for 1 search\n"
            f"👑 **Lifetime:** ₹8000 for unlimited searches forever!"
        )
    
    return True, ""

def use_search_credit(user_id: int) -> None:
    """Deduct one search credit from user"""
    subscription = get_user_subscription(user_id)
    
    # Don't deduct credits from admin
    if not subscription.get("is_admin", False):
        subscription["searches_used"] += 1
    
    subscription["total_searches"] = subscription.get("total_searches", 0) + 1
    subscription_manager.save_subscriptions()
    
    logger.info(f"📊 User {user_id} used search credit: {subscription['searches_used']}/{subscription_plans[subscription['plan']]['searches_per_day']}")

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

def is_admin(message) -> bool:
    """Check if user is admin with improved validation"""
    if not message or not message.from_user:
        return False
    
    user_id = message.from_user.id
    username = message.from_user.username
    
    return is_admin_by_user_id(user_id, username)

def is_admin_by_user_id(user_id: int, username: Optional[str]) -> bool:
    """Check if user is admin by user ID and username"""
    if user_id == config.ADMIN_USER_ID:
        return True
    
    if username and username.upper() == config.ADMIN_USERNAME.upper():
        return True
    
    # Check subscription manager for admin status
    if subscription_manager:
        user_sub = subscription_manager.users.get(user_id)
        if user_sub and user_sub.get('is_admin', False):
            return True
    
    return False

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

def query_api(number: str) -> Tuple[bool, str]:
    """Call the remote API with improved error handling and retries"""
    url = config.API_ENDPOINT_TEMPLATE.format(number=number)
    last_exc = None
    
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            logger.info(f"🔍 API Request attempt {attempt}/{config.MAX_RETRIES} for number: {number[:3]}***")
            
            resp = requests.get(
                url, 
                timeout=config.REQUEST_TIMEOUT,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'application/json, text/plain, */*',
                    'Connection': 'keep-alive'
                }
            )
            
            if resp.status_code == 200:
                try:
                    # Try to parse as JSON first
                    json_data = resp.json()
                    if isinstance(json_data, list) and len(json_data) > 0:
                        formatted_response = format_user_data(json_data)
                        logger.info(f"✅ API Success: Found {len(json_data)} record(s)")
                        return True, formatted_response
                    elif isinstance(json_data, dict) and json_data.get('status') == 'success':
                        # Handle different API response formats
                        data = json_data.get('data', [])
                        if data:
                            formatted_response = format_user_data(data if isinstance(data, list) else [data])
                            logger.info(f"✅ API Success: Found data")
                            return True, formatted_response
                    
                    logger.warning(f"⚠️ API returned empty or invalid data")
                    return True, "❌ No data found for this number"
                    
                except (json.JSONDecodeError, ValueError) as e:
                    # If not JSON, check if it's a valid text response
                    text_response = resp.text.strip()
                    if text_response and len(text_response) > 10:
                        logger.info(f"✅ API Success: Text response received")
                        return True, text_response
                    else:
                        logger.warning(f"⚠️ API returned invalid text response")
                        return True, "❌ No data found for this number"
            
            elif resp.status_code == 401:
                # Invalid API key
                error_msg = "❌ Invalid API key! Please check your API_KEY in environment variables."
                logger.error(f"🔑 API Authentication failed: {error_msg}")
                return False, error_msg
            
            elif resp.status_code == 429:
                # Rate limiting
                wait_time = config.RETRY_DELAY * (2 ** attempt)
                logger.warning(f"⚠️ Rate limited, waiting {wait_time}s before retry")
                time.sleep(wait_time)
                continue
            
            else:
                error_msg = f"API returned HTTP {resp.status_code}"
                if attempt == config.MAX_RETRIES:
                    return False, error_msg
                logger.warning(f"{error_msg}, retrying...")
                
        except (ReadTimeout, ConnectionError) as e:
            last_exc = e
            logger.warning(f"🌐 Network error on attempt {attempt}: {type(e).__name__}")
            if attempt < config.MAX_RETRIES:
                time.sleep(config.RETRY_DELAY * attempt)
        except RequestException as e:
            last_exc = e
            logger.error(f"❌ Request error on attempt {attempt}: {e}")
            if attempt < config.MAX_RETRIES:
                time.sleep(config.RETRY_DELAY)
        except Exception as e:
            last_exc = e
            logger.error(f"❌ Unexpected error on attempt {attempt}: {e}")
            break
    
    error_msg = f"Request failed after {config.MAX_RETRIES} attempts. Last error: {type(last_exc).__name__}: {str(last_exc)[:100]}"
    logger.error(error_msg)
    return False, error_msg

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

@bot.message_handler(commands=['verify_subs'])
def verify_subscriptions(message):
    """Admin command to verify subscription persistence"""
    if not is_admin(message):
        bot.reply_to(message, "❌ Access Denied! Admin only command.")
        return
    
    try:
        # Test subscription persistence for all users
        total_users = len(subscription_manager.users)
        verified_count = 0
        
        for user_id in list(subscription_manager.users.keys()):
            if subscription_manager.verify_subscription_persistence(user_id):
                verified_count += 1
        
        result_text = f"""
🔍 **Subscription Persistence Test** 🔍

📊 **Results:**
• Total Users: {total_users}
• Verified: {verified_count}
• Failed: {total_users - verified_count}

✅ **Status:** {'All subscriptions verified!' if verified_count == total_users else 'Some subscriptions have issues!'}

📁 **File:** {subscription_manager.subscription_file}
⏰ **Last Loaded:** {subscription_manager._last_loaded}
        """
        
        bot.send_message(message.chat.id, result_text, parse_mode='Markdown')
        
    except Exception as e:
        bot.reply_to(message, f"❌ Error during verification: {e}")

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
• Admin: @{config.ADMIN_USERNAME}
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
        # Use subscription_manager.users instead of undefined user_subscriptions
        user_subscriptions = subscription_manager.users if subscription_manager else {}
        
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
        if target_user_id in subscription_manager.users:
            target_username = subscription_manager.users[target_user_id].get("username", "N/A")
            target_first_name = subscription_manager.users[target_user_id].get("first_name", "N/A")
        
        # Add subscription
        user_data = subscription_manager.add_subscription_user(target_user_id, target_username, target_first_name, plan, price)
        
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

💬 **Activated by:** Admin @{config.ADMIN_USERNAME}
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
                broadcast_message = f"📢 **Admin Broadcast Message:**\n\n{broadcast_text}\n\n─────────────────\n💬 From: @{config.ADMIN_USERNAME}"
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


@app.route('/', methods=['GET'])
def home():
    """Serve the test interface HTML file"""
    try:
        # Try to read from current directory first
        html_file_path = os.path.join(os.path.dirname(__file__), 'test_interface.html')
        if os.path.exists(html_file_path):
            with open(html_file_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            return html_content
        else:
            # Fallback to current working directory
            with open('test_interface.html', 'r', encoding='utf-8') as f:
                html_content = f.read()
            return html_content
    except (FileNotFoundError, IOError) as e:
        logger.warning(f"Could not load test_interface.html: {e}")
        return """<!DOCTYPE html>
<html><head><title>Bot Server</title><meta charset="UTF-8"></head>
<body style="font-family: Arial, sans-serif; text-align: center; padding: 50px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; min-height: 100vh; margin: 0;">
<h1>🤖 Telegram Bot Server is Running!</h1>
<p style="font-size: 1.2em;">✅ Server is online and ready</p>
<p>📱 Bot is operational</p>
<p>👑 Admin: @CRAZYPANEL1</p>
<p style="margin-top: 30px; opacity: 0.8;">Port: {}</p>
</body></html>""".format(config.PORT)

@app.route('/ping', methods=['GET'])
def ping():
    """Simple ping endpoint for health checks"""
    return "pong", 200

@app.route('/ready', methods=['GET'])
def ready():
    """Immediate readiness check for deployment platforms"""
    return f"READY ON PORT {config.PORT}", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle incoming webhook requests from Telegram"""
    try:
        # Log webhook received for debugging
        logger.debug("📨 Webhook request received")
        
        json_str = request.get_data().decode('UTF-8')
        if not json_str:
            logger.warning("⚠️ Empty webhook data received")
            return jsonify({"status": "error", "message": "Empty data"}), 400
        
        # Parse and process update
        update = telebot.types.Update.de_json(json_str)
        if update:
            logger.debug(f"🔄 Processing update: {update.update_id}")
            bot.process_new_updates([update])
            return jsonify({"status": "ok", "update_id": update.update_id})
        else:
            logger.warning("⚠️ Invalid update data")
            return jsonify({"status": "error", "message": "Invalid update"}), 400
            
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}")
        logger.exception("Webhook error details:")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Enhanced health check endpoint with bot status"""
    try:
        uptime = datetime.now() - bot_stats["start_time"]
        
        # Check bot status
        bot_status = "unknown"
        webhook_info = None
        
        try:
            # Try to get bot info to verify it's working
            bot_info = bot.get_me()
            if config.WEBHOOK_URL:
                webhook_info = bot.get_webhook_info()
                bot_status = "webhook_active" if webhook_info.url else "webhook_inactive"
            else:
                bot_status = "polling_mode"
        except Exception as e:
            bot_status = f"error: {str(e)[:50]}"
        
        health_data = {
            "status": "healthy",
            "uptime": str(uptime).split('.')[0],
            "total_searches": bot_stats['total_searches'],
            "active_users": len(search_history),
            "subscription_users": len(subscription_manager.users) if subscription_manager else 0,
            "bot_version": "2.1",
            "admin": config.ADMIN_USERNAME,
            "bot_status": bot_status,
            "environment": "production" if config.WEBHOOK_URL else "development",
            "timestamp": datetime.now().isoformat()
        }
        
        # Add webhook info if available
        if webhook_info:
            health_data["webhook_info"] = {
                "url": webhook_info.url,
                "pending_updates": webhook_info.pending_update_count,
                "last_error": webhook_info.last_error_message
            }
        
        return jsonify(health_data)
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/status', methods=['GET'])
def status_check():
    """Simple status endpoint for deployment platforms"""
    try:
        bot_status = bool(subscription_manager and bot_manager)
        return jsonify({
            "status": "online",
            "message": "Server is ready! 🚀",
            "bot_running": bot_status,
            "port": config.PORT,
            "test_interface": f"http://localhost:{config.PORT}/",
            "version": "2.1"
        })
    except Exception as e:
        return jsonify({
            "status": "partial",
            "message": "Server running but bot may have issues",
            "error": str(e),
            "port": config.PORT
        }), 200

@app.route('/debug', methods=['GET'])
def debug_info():
    """Debug endpoint for deployment troubleshooting"""
    try:
        debug_data = {
            "environment_variables": {
                "BOT_TOKEN": "SET" if config.BOT_TOKEN else "NOT SET",
                "API_KEY": "SET" if config.API_KEY else "NOT SET", 
                "WEBHOOK_URL": config.WEBHOOK_URL or "NOT SET",
                "ADMIN_USERNAME": config.ADMIN_USERNAME,
                "ADMIN_USER_ID": config.ADMIN_USER_ID,
                "PORT": config.PORT
            },
            "bot_status": {
                "subscription_manager": "INITIALIZED" if subscription_manager else "NOT INITIALIZED",
                "bot_manager": "INITIALIZED" if bot_manager else "NOT INITIALIZED",
                "total_subscriptions": len(subscription_manager.users) if subscription_manager else 0
            },
            "deployment_mode": "PRODUCTION (Webhook)" if config.WEBHOOK_URL else "DEVELOPMENT (Polling)",
            "flask_status": "RUNNING",
            "timestamp": datetime.now().isoformat()
        }
        
        # Try to get bot info
        try:
            bot_info = bot.get_me()
            debug_data["bot_info"] = {
                "username": bot_info.username,
                "first_name": bot_info.first_name,
                "id": bot_info.id,
                "can_join_groups": bot_info.can_join_groups,
                "can_read_all_group_messages": bot_info.can_read_all_group_messages,
                "supports_inline_queries": bot_info.supports_inline_queries
            }
        except Exception as e:
            debug_data["bot_info"] = {"error": str(e)}
        
        # Try to get webhook info if in production
        if config.WEBHOOK_URL:
            try:
                webhook_info = bot.get_webhook_info()
                debug_data["webhook_debug"] = {
                    "url": webhook_info.url,
                    "has_custom_certificate": webhook_info.has_custom_certificate,
                    "pending_update_count": webhook_info.pending_update_count,
                    "last_error_message": webhook_info.last_error_message,
                    "last_error_date": str(webhook_info.last_error_date) if webhook_info.last_error_date else None,
                    "max_connections": webhook_info.max_connections,
                    "allowed_updates": webhook_info.allowed_updates
                }
            except Exception as e:
                debug_data["webhook_debug"] = {"error": str(e)}
        
        return jsonify(debug_data)
        
    except Exception as e:
        return jsonify({
            "error": "Debug endpoint failed",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/test_webhook', methods=['POST'])
def test_webhook():
    """Test webhook endpoint to verify it's receiving data"""
    try:
        data = request.get_json() or {}
        headers = dict(request.headers)
        
        logger.info(f"🧪 Test webhook received data: {data}")
        logger.info(f"🧪 Test webhook headers: {headers}")
        
        return jsonify({
            "status": "success",
            "message": "Test webhook received data",
            "data_received": data,
            "headers_received": headers,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"❌ Test webhook error: {e}")
        return jsonify({
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    """Set webhook URL (for manual setup if needed)"""
    if config.WEBHOOK_URL and config.WEBHOOK_URL.strip():
        try:
            webhook_url = f"{config.WEBHOOK_URL.rstrip('/')}/webhook"
            
            # Remove existing webhook first
            bot.remove_webhook()
            time.sleep(1)
            
            # Set new webhook
            result = bot.set_webhook(url=webhook_url)
            
            if result:
                # Get webhook info for verification
                webhook_info = bot.get_webhook_info()
                return jsonify({
                    "status": "success",
                    "message": f"Webhook set to {webhook_url}",
                    "webhook_info": {
                        "url": webhook_info.url,
                        "has_custom_certificate": webhook_info.has_custom_certificate,
                        "pending_update_count": webhook_info.pending_update_count,
                        "last_error_message": webhook_info.last_error_message,
                        "last_error_date": webhook_info.last_error_date
                    }
                })
            else:
                return jsonify({
                    "status": "error",
                    "message": "Failed to set webhook"
                }), 500
                
        except Exception as e:
            logger.error(f"Manual webhook setup failed: {e}")
            return jsonify({
                "status": "error",
                "message": str(e)
            }), 500
    else:
        return jsonify({
            "status": "error",
            "message": "WEBHOOK_URL environment variable not set or empty"
        }), 400

def setup_webhook():
    """Setup webhook on startup with improved error handling"""
    if config.WEBHOOK_URL:
        try:
            webhook_url = f"{config.WEBHOOK_URL}/webhook"
            bot.remove_webhook()
            time.sleep(1)  # Give time for webhook removal
            bot.set_webhook(url=webhook_url)
            logger.info(f"✅ Webhook set to: {webhook_url}")
        except Exception as e:
            logger.error(f"❌ Failed to set webhook: {e}")
            raise
    else:
        logger.info("⚠️ WEBHOOK_URL not set, running in polling mode")

class BotManager:
    """Manages bot polling with improved error handling and recovery"""
    
    def __init__(self):
        self.retry_delay = 5
        self.max_retry_delay = 60
        self.is_running = False
        self.consecutive_errors = 0
        self.max_consecutive_errors = 10
    
    def start_polling(self):
        """Start bot polling with enhanced error recovery"""
        logger.info("🔄 Starting bot polling...")
        self.is_running = True
        
        while self.is_running:
            try:
                # Clear webhook before polling
                try:
                    bot.remove_webhook()
                    time.sleep(2)
                except Exception as e:
                    logger.warning(f"Could not remove webhook: {e}")
                
                logger.info("🤖 Bot polling started successfully")
                self.consecutive_errors = 0  # Reset error counter
                
                bot.infinity_polling(
                    timeout=30,
                    long_polling_timeout=30,
                    allowed_updates=['message', 'callback_query']
                )
                
            except (ReadTimeout, ConnectionError) as e:
                self._handle_network_error(e)
            except Exception as e:
                self._handle_general_error(e)
            
            if self.is_running:
                logger.info(f"🔄 Reconnecting in {self.retry_delay} seconds...")
                time.sleep(self.retry_delay)
                self._adjust_retry_delay()
    
    def _handle_network_error(self, error):
        """Handle network-related errors"""
        self.consecutive_errors += 1
        logger.warning(f"🌐 Network error #{self.consecutive_errors}: {type(error).__name__}")
        
        if self.consecutive_errors >= self.max_consecutive_errors:
            logger.error(f"❌ Too many consecutive errors ({self.consecutive_errors}). Stopping bot.")
            self.is_running = False
            return
        
        # Exponential backoff for network errors
        self.retry_delay = min(self.retry_delay * 1.5, self.max_retry_delay)
    
    def _handle_general_error(self, error):
        """Handle general errors"""
        self.consecutive_errors += 1
        logger.error(f"❌ Bot error #{self.consecutive_errors}: {type(error).__name__}: {str(error)[:150]}")
        
        if self.consecutive_errors >= self.max_consecutive_errors:
            logger.error(f"❌ Critical: Too many errors. Bot stopping.")
            self.is_running = False
            return
    
    def _adjust_retry_delay(self):
        """Adjust retry delay based on error count"""
        if self.consecutive_errors == 0:
            self.retry_delay = 5  # Reset to minimum
        else:
            self.retry_delay = min(self.retry_delay * 2, self.max_retry_delay)
    
    def stop(self):
        """Stop the bot polling"""
        self.is_running = False
        logger.info("🛑 Bot polling stopped")

def main():
    """Main application entry point optimized for Render deployment"""
    try:
        # Print port binding message IMMEDIATELY
        print(f"🚀 Binding to port {config.PORT}...")
        
        # Detect environment
        is_production = bool(config.WEBHOOK_URL and config.WEBHOOK_URL.strip())
        env_name = "PRODUCTION (Render)" if is_production else "DEVELOPMENT (Local)"
        print(f"🌐 Environment: {env_name}")
        
        if is_production:
            print(f"🔗 Webhook URL: {config.WEBHOOK_URL}")
            print(f"📱 Test interface: {config.WEBHOOK_URL}/")
        else:
            print(f"📱 Test interface: http://localhost:{config.PORT}/")
        
        # Initialize components immediately for production
        global bot_manager, subscription_manager
        
        try:
            logger.info("🔄 Initializing core components...")
            
            # Initialize subscription manager first
            subscription_manager = SubscriptionManager()
            logger.info(f"📊 Loaded {len(subscription_manager.users)} subscriptions")
            
            # Initialize bot manager
            bot_manager = BotManager()
            logger.info("🤖 Mobile Number Lookup Bot v2.1 Ready!")
            logger.info(f"👑 Admin: @{config.ADMIN_USERNAME} (ID: {config.ADMIN_USER_ID})")
            
        except Exception as e:
            logger.error(f"❌ Component initialization failed: {e}")
            logger.exception("Initialization error:")
        
        # Setup bot mode based on environment
        def setup_bot_mode():
            try:
                if is_production:
                    logger.info("🌐 Setting up production webhook mode...")
                    setup_webhook_for_render()
                else:
                    logger.info("🖥️ Setting up local polling mode...")
                    setup_local_polling()
            except Exception as e:
                logger.error(f"❌ Bot mode setup failed: {e}")
                logger.exception("Bot setup error:")
        
        # Start bot setup in background for production, immediate for local
        if is_production:
            # For production, setup after Flask starts
            setup_thread = threading.Thread(target=setup_bot_mode, daemon=True)
            setup_thread.start()
        else:
            # For local, setup immediately
            setup_bot_mode()
        
        # Configure Flask for production
        app.config['JSON_SORT_KEYS'] = False
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False
        
        # Start Flask app
        print(f"🌐 Flask server starting on 0.0.0.0:{config.PORT}")
        print(f"🔍 Health: {config.WEBHOOK_URL or f'http://localhost:{config.PORT}'}/health")
        print(f"🐛 Debug: {config.WEBHOOK_URL or f'http://localhost:{config.PORT}'}/debug")
        
        app.run(
            host='0.0.0.0', 
            port=config.PORT, 
            debug=False, 
            use_reloader=False, 
            threaded=True
        )
            
    except KeyboardInterrupt:
        print("🛑 Received shutdown signal")
        if 'bot_manager' in globals():
            bot_manager.stop()
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        # Emergency Flask startup
        try:
            print(f"🚨 Emergency Flask startup on port {config.PORT}")
            print(f"📱 Emergency test interface: http://localhost:{config.PORT}/")
            app.run(host='0.0.0.0', port=config.PORT, debug=False, threaded=True)
        except:
            raise e
    finally:
        print("👋 Bot shutdown complete")

def setup_webhook_for_render():
    """Setup webhook specifically for Render deployment"""
    try:
        # Wait for Flask to be fully ready
        logger.info("🔄 Waiting for Flask to be ready...")
        time.sleep(5)  # Give more time for Render
        
        logger.info(f"🔗 Setting up Render webhook: {config.WEBHOOK_URL}")
        
        # Test bot connection first
        try:
            bot_info = bot.get_me()
            logger.info(f"🤖 Bot connected: @{bot_info.username} ({bot_info.first_name})")
        except Exception as e:
            logger.error(f"❌ Bot connection failed: {e}")
            return
        
        # Remove existing webhook
        try:
            bot.remove_webhook(drop_pending_updates=True)
            time.sleep(2)
            logger.info("🗑️ Cleared existing webhook and pending updates")
        except Exception as e:
            logger.warning(f"⚠️ Webhook removal warning: {e}")
        
        # Set new webhook with proper URL
        webhook_url = f"{config.WEBHOOK_URL.rstrip('/')}/webhook"
        logger.info(f"🔗 Setting webhook to: {webhook_url}")
        
        result = bot.set_webhook(
            url=webhook_url,
            max_connections=10,
            drop_pending_updates=True
        )
        
        if result:
            logger.info("✅ Webhook set successfully!")
            
            # Verify webhook immediately
            time.sleep(1)
            webhook_info = bot.get_webhook_info()
            
            logger.info(f"📊 Webhook verification:")
            logger.info(f"  URL: {webhook_info.url}")
            logger.info(f"  Pending updates: {webhook_info.pending_update_count}")
            logger.info(f"  Max connections: {webhook_info.max_connections}")
            
            if webhook_info.last_error_message:
                logger.error(f"❌ Webhook error: {webhook_info.last_error_message}")
                logger.error(f"  Error date: {webhook_info.last_error_date}")
            else:
                logger.info("✅ No webhook errors detected")
                
            logger.info("🎉 Bot is ready for production on Render!")
        else:
            logger.error("❌ Failed to set webhook")
            
    except Exception as e:
        logger.error(f"❌ Render webhook setup failed: {e}")
        logger.exception("Full webhook error:")

def setup_local_polling():
    """Setup polling for local development"""
    try:
        logger.info("📱 Setting up local polling mode...")
        
        # Clear any existing webhook
        try:
            bot.remove_webhook()
            time.sleep(1)
            logger.info("🗑️ Cleared webhook for local mode")
        except:
            pass
        
        # Start polling in background
        def polling_worker():
            try:
                logger.info("🔄 Starting bot polling...")
                bot_manager.start_polling()
            except Exception as e:
                logger.error(f"❌ Polling failed: {e}")
        
        polling_thread = threading.Thread(target=polling_worker, daemon=True)
        polling_thread.start()
        
        logger.info("🎉 Bot polling started for local development!")
        
    except Exception as e:
        logger.error(f"❌ Local polling setup failed: {e}")
        logger.exception("Polling setup error:")

if __name__ == "__main__":
    # Print immediate startup messages for deployment platforms
    print("=" * 50)
    print("  TELEGRAM BOT SERVER STARTING")
    print("=" * 50)
    print(f"  Port: {config.PORT}")
    print(f"  Host: 0.0.0.0")
    print(f"  Status: BINDING TO PORT NOW...")
    if config.WEBHOOK_URL:
        print(f"  Production URL: {config.WEBHOOK_URL}")
    else:
        print(f"  Local URL: http://localhost:{config.PORT}/")
    print("=" * 50)
    main()
