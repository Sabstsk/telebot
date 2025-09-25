# Mobile Number Lookup Bot - Flask Web App

A Telegram bot that provides mobile number lookup services, converted to run as a Flask web application for 24/7 deployment on platforms like Render.com.

## Features

- 🔍 Mobile number lookup with detailed information
- 💎 Subscription system (Free, Single, Lifetime plans)
- 👑 Admin panel with full management capabilities
- 📊 Statistics and search history tracking
- 🌐 Webhook support for production deployment
- 🔄 Automatic fallback to polling mode for development

## Deployment on Render.com

### Step 1: Environment Variables

Set these environment variables in your Render.com service:

```
BOT_TOKEN=your_telegram_bot_token
API_KEY=your_api_key
ADMIN_USERNAME=your_admin_username
ADMIN_USER_ID=your_admin_user_id
WEBHOOK_URL=https://your-app-name.onrender.com
PORT=10000
```

### Step 2: Deploy

1. Connect your GitHub repository to Render.com
2. Create a new Web Service
3. Set the build command: `pip install -r requirements.txt`
4. Set the start command: `gunicorn bot:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120`
5. Add the environment variables listed above
6. Deploy!

### Step 3: Set Webhook

After deployment, visit: `https://your-app-name.onrender.com/set_webhook`

This will automatically configure the Telegram webhook.

## Local Development

For local development, the bot will run in polling mode:

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables in .env file
BOT_TOKEN=your_bot_token
API_KEY=your_api_key
ADMIN_USERNAME=your_username
ADMIN_USER_ID=your_user_id

# Run locally (polling mode)
python bot.py
```

## API Endpoints

- `GET /` - Health check and bot status
- `POST /webhook` - Telegram webhook endpoint
- `GET /health` - Detailed health check with statistics
- `GET /set_webhook` - Manually set webhook URL

## Bot Commands

- `/start` - Welcome message and main menu
- `/help` - Complete help guide
- `/check <number>` - Search mobile number
- `/admin` - Admin panel (admin only)
- `/mystats` - Personal statistics
- `/pricing` - Subscription plans

## Admin Features

- 👥 View all users and their information
- 📊 Complete bot statistics
- 🗂️ All search history
- 💎 Subscription management
- ➕ Add subscriptions manually
- 📢 Broadcast messages to all users
- 🔄 Reset bot statistics

## Subscription Plans

- 🆓 **Free Plan**: 0 searches/day (upgrade required)
- 🔍 **Single Search**: ₹100 for 1 search (24 hours)
- 👑 **Lifetime Plan**: ₹8000 for unlimited searches forever

## Technical Details

- **Framework**: Flask + pyTelegramBotAPI
- **Database**: JSON file storage for subscriptions
- **Deployment**: Gunicorn WSGI server
- **Webhook**: Automatic setup for production
- **Fallback**: Polling mode for development

## File Structure

```
├── bot.py              # Main Flask application
├── requirements.txt    # Python dependencies
├── Procfile           # Render.com deployment config
├── runtime.txt        # Python version
├── subscriptions.json # User subscription data
├── .env              # Environment variables (local)
└── README.md         # This file
```

## Support

For support and issues, contact the admin: @CRAZYPANEL1