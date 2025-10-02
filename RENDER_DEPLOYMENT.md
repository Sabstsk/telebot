# 🚀 Render Deployment Guide for Telegram Bot

## ✅ Pre-Deployment Checklist

### 1. Required Files
- ✅ `bot.py` - Main bot application
- ✅ `start.py` - Render startup script
- ✅ `Procfile` - Process configuration
- ✅ `requirements.txt` - Python dependencies
- ✅ `test_interface.html` - Web interface
- ✅ `.env.example` - Environment variables template

### 2. Environment Variables (Set in Render Dashboard)

**Required Variables:**
```
BOT_TOKEN=your_telegram_bot_token_here
API_KEY=your_api_key_here
WEBHOOK_URL=https://your-app-name.onrender.com
ADMIN_USERNAME=CRAZYPANEL1
ADMIN_USER_ID=7490634345
PORT=10000
```

**Optional Variables:**
```
CHAT_ID=your_chat_id_here
```

## 🔧 Deployment Steps

### Step 1: Create Render Web Service
1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click "New" → "Web Service"
3. Connect your GitHub repository
4. Configure the service:
   - **Name**: `telegram-bot-app` (or your choice)
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python start.py`

### Step 2: Set Environment Variables
In Render dashboard, go to Environment tab and add all required variables.

### Step 3: Deploy
Click "Create Web Service" and wait for deployment.

## 🔍 Post-Deployment Verification

### 1. Check Deployment Status
Visit these URLs after deployment:

- **Main Interface**: `https://your-app.onrender.com/`
- **Health Check**: `https://your-app.onrender.com/health`
- **Debug Info**: `https://your-app.onrender.com/debug`
- **Status**: `https://your-app.onrender.com/status`

### 2. Verify Bot Status
Check the debug endpoint for:
- ✅ Bot Token: SET
- ✅ API Key: SET
- ✅ Webhook URL: SET
- ✅ Bot Info: Should show bot username and details
- ✅ Webhook Debug: Should show webhook URL and no errors

### 3. Test Bot Functionality
1. Send `/start` to your bot on Telegram
2. Try sending a mobile number
3. Check if bot responds properly

## 🐛 Troubleshooting

### Common Issues and Solutions

#### Issue 1: Bot Not Responding
**Check**: Visit `/debug` endpoint
**Solution**: 
- Verify BOT_TOKEN is correct
- Check webhook URL matches your Render app URL
- Visit `/set_webhook` to manually set webhook

#### Issue 2: Webhook Errors
**Check**: Look at `webhook_debug.last_error_message` in `/debug`
**Solution**:
- Ensure WEBHOOK_URL is exactly: `https://your-app.onrender.com`
- No trailing slash in WEBHOOK_URL
- Bot token must be valid

#### Issue 3: Environment Variables Not Set
**Check**: Visit `/debug` to see which variables are missing
**Solution**: Add missing variables in Render dashboard

#### Issue 4: App Crashes on Startup
**Check**: Render logs in dashboard
**Solution**: 
- Verify all required files are present
- Check Python syntax errors
- Ensure requirements.txt has all dependencies

### Debug Commands

```bash
# Check if webhook is set correctly
curl https://your-app.onrender.com/debug

# Manually set webhook
curl https://your-app.onrender.com/set_webhook

# Check health status
curl https://your-app.onrender.com/health
```

## 📊 Monitoring

### Health Check Endpoints
- `/health` - Detailed health information
- `/status` - Simple status check
- `/debug` - Complete debugging information
- `/ping` - Basic connectivity test

### Log Monitoring
Check Render logs for these success messages:
- `🤖 Bot connected: @your_bot_username`
- `✅ Webhook set successfully!`
- `🎉 Bot is ready for production on Render!`

## 🔄 Updates and Maintenance

### Updating the Bot
1. Push changes to your GitHub repository
2. Render will automatically redeploy
3. Check `/debug` endpoint after deployment
4. Verify bot functionality

### Manual Webhook Reset
If webhook stops working:
1. Visit `https://your-app.onrender.com/set_webhook`
2. Check response for success
3. Test bot functionality

## 📞 Support

If you encounter issues:
1. Check the debug endpoint first
2. Review Render deployment logs
3. Verify all environment variables are set correctly
4. Test webhook manually using `/set_webhook`

## 🎯 Success Indicators

Your deployment is successful when:
- ✅ Web interface loads at your Render URL
- ✅ `/debug` shows all components initialized
- ✅ Bot responds to `/start` command on Telegram
- ✅ Mobile number lookup works properly
- ✅ No webhook errors in debug info
