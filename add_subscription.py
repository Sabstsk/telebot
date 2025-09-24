#!/usr/bin/env python3
"""
Admin script to manually add subscriptions to the bot.
Usage: python add_subscription.py <user_id> <username> <first_name> <plan> <payment_amount>
Example: python add_subscription.py 123456789 "testuser" "Test User" "premium" 99
"""

import json
import sys
from datetime import datetime, timedelta

def add_subscription(user_id, username, first_name, plan, payment_amount):
    """Add a subscription to the JSON file."""
    
    # Load existing data
    try:
        with open('subscriptions.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {"users": {}, "metadata": {}}
    
    # Create user data
    user_data = {
        "user_id": int(user_id),
        "username": username,
        "first_name": first_name,
        "plan": plan,
        "payment_amount": int(payment_amount),
        "created_date": datetime.now().isoformat(),
        "expires": None,
        "searches_used": 0,
        "last_reset": datetime.now().date().isoformat(),
        "total_searches": 0,
        "status": "active"
    }
    
    # Set expiry date based on plan
    if plan == "single":
        user_data["expires"] = (datetime.now() + timedelta(days=1)).isoformat()
    elif plan in ["premium", "pro"]:
        user_data["expires"] = (datetime.now() + timedelta(days=30)).isoformat()
    elif plan == "lifetime":
        user_data["expires"] = (datetime.now() + timedelta(days=36500)).isoformat()
    
    # Add to data
    data["users"][str(user_id)] = user_data
    data["metadata"] = {
        "last_updated": datetime.now().isoformat(),
        "total_users": len(data["users"]),
        "version": "1.0"
    }
    
    # Save back to file
    with open('subscriptions.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Added subscription for {username} ({first_name})")
    print(f"   Plan: {plan}")
    print(f"   Amount: ₹{payment_amount}")
    print(f"   Expires: {user_data['expires']}")

if __name__ == "__main__":
    if len(sys.argv) != 6:
        print("Usage: python add_subscription.py <user_id> <username> <first_name> <plan> <payment_amount>")
        print("Plans: single, premium, pro, lifetime")
        print("Example: python add_subscription.py 123456789 testuser 'Test User' premium 99")
        sys.exit(1)
    
    user_id, username, first_name, plan, payment_amount = sys.argv[1:6]
    
    if plan not in ["single", "premium", "pro", "lifetime"]:
        print("❌ Invalid plan. Use: single, premium, pro, or lifetime")
        sys.exit(1)
    
    try:
        add_subscription(user_id, username, first_name, plan, payment_amount)
    except Exception as e:
        print(f"❌ Error: {e}")
