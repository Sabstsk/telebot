# Render Deployment Guide

## Fixed Issues

### 1. ✅ Procfile Fixed
- **Issue**: Referenced `start.py` instead of `bot.py`
- **Fix**: Updated to use `python start.py`

### 2. ✅ render.yaml Updated
- **Issue**: startCommand was inconsistent
- **Fix**: Updated to use `python start.py`

### 3. ✅ Webhook Auto-Detection
- **Issue**: Hardcoded webhook URLs
- **Fix**: Now uses `RENDER_EXTERNAL_URL` environment variable

### 4. ✅ Logging Fixed
- **Issue**: File logging causing issues on Render
- **Fix**: Console-only logging on Render

### 5. ✅ Bot Manager Initialization
- **Issue**: Missing global variable declaration
- **Fix**: Added proper global variable initialization

## Environment Variables Required on Render

### Required:
- `BOT_TOKEN` - Your Telegram bot token
- `API_KEY` - Your API key for the mobile lookup service

### Optional (Auto-configured):
- `WEBHOOK_URL` - Will auto-detect from Render
- `PORT` - Set to 10000 by default
- `ADMIN_USERNAME` - Set to CRAZYPANEL1
- `ADMIN_USER_ID` - Set to 7490634345

## Deployment Steps

1. **Push code to GitHub**
2. **Connect to Render**
3. **Set environment variables** in Render dashboard:
   - `BOT_TOKEN=your_bot_token_here`
   - `API_KEY=your_api_key_here`
4. **Deploy** - Render will automatically use `render.yaml`

## Health Check URLs

After deployment, test these URLs:
- `https://your-app.onrender.com/health` - Bot health status
- `https://your-app.onrender.com/status` - Detailed status
- `https://your-app.onrender.com/webhook_status` - Webhook status

## Troubleshooting

### Bot Not Responding
1. Check logs in Render dashboard
2. Verify `BOT_TOKEN` is correctly set
3. Visit `/health` endpoint to check status
4. Visit `/set_webhook` to manually set webhook

### API Errors
1. Verify `API_KEY` is correctly set
2. Check `/debug` endpoint for API status
3. Test API manually via `/test_api?number=1234567890`

## Manual Webhook Setup (if needed)

If webhook isn't auto-configured:
1. Visit: `https://your-app.onrender.com/set_webhook`
2. Or use: `https://your-app.onrender.com/fix_webhook`

## Success Indicators

✅ Render logs show: "Flask server starting on 0.0.0.0:10000"
✅ Health endpoint returns: "status": "online"
✅ Webhook endpoint returns: "url": "https://your-app.onrender.com/webhook"
✅ Bot responds to messages in Telegram
