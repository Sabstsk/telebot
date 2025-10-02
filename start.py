#!/usr/bin/env python3
"""
Startup script optimized for Render deployment
This ensures proper bot initialization in production environment
"""
import os
import sys
import time
import logging

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    """Main startup function for Render"""
    print("🚀 RENDER DEPLOYMENT STARTUP")
    print("=" * 50)
    
    # Set environment variables if not set
    port = os.environ.get('PORT', '10000')
    print(f"📡 Port: {port}")
    
    # Set RENDER environment variable to indicate we're on Render
    os.environ['RENDER'] = 'true'
    
    # Check required environment variables - WEBHOOK_URL is optional for Render
    required_vars = ['BOT_TOKEN', 'API_KEY']
    optional_vars = ['WEBHOOK_URL']
    missing_vars = []
    
    for var in required_vars:
        if not os.environ.get(var):
            missing_vars.append(var)
        else:
            if var == 'BOT_TOKEN':
                print(f"✅ {var}: SET (***{os.environ[var][-4:]})")
            else:
                print(f"✅ {var}: SET")
    
    # Check optional variables
    for var in optional_vars:
        if os.environ.get(var):
            print(f"✅ {var}: {os.environ[var]}")
        else:
            print(f"⚠️ {var}: NOT SET (will auto-generate)")
    
    if missing_vars:
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        print("Please set these in your Render dashboard")
        sys.exit(1)
    
    print("=" * 50)
    print("🔄 Starting bot application...")
    print("🚀 Flask will bind to port immediately!")
    
    # Import and run the main bot
    try:
        from bot import main as bot_main
        bot_main()
    except Exception as e:
        print(f"❌ Failed to start bot: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
