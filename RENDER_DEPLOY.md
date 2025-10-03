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

### 6. ✅ Callback Query Error Handling
- **Issue**: "query is too old" errors causing bot crashes
- **Fix**: Added safe callback query handler with error handling
- **Fix**: Auto-clear pending updates on startup

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

### Bot Not Responding (webhook_inactive)
If you see `"bot_status":"webhook_inactive"` and `"url":""` in health check:

**Quick Fix:**
1. Visit: `https://your-app.onrender.com/set_webhook`
2. This will auto-detect your Render URL and set the webhook
3. Check: `https://your-app.onrender.com/health` - should show webhook active

**If you have pending updates:**
1. Visit: `https://your-app.onrender.com/clear_updates`
2. Then visit: `https://your-app.onrender.com/set_webhook`

### API Errors
1. Verify `API_KEY` is correctly set
2. Check `/debug` endpoint for API status
3. Test API manually via `/test_api?number=1234567890`

### Environment Variables
1. Verify `BOT_TOKEN` is correctly set
2. Check logs in Render dashboard for validation errors

## Manual Webhook Setup Options

1. **Auto-detect URL**: `https://your-app.onrender.com/set_webhook`
2. **Force webhook**: `https://your-app.onrender.com/force_webhook`
3. **Clear pending updates**: `https://your-app.onrender.com/clear_updates`

## Success Indicators

✅ Render logs show: "Flask server starting on 0.0.0.0:10000"
✅ Health endpoint returns: "status": "online"
✅ Webhook endpoint returns: "url": "https://your-app.onrender.com/webhook"
✅ Bot responds to messages in Telegram
