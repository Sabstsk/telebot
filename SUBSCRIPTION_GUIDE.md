# 💎 Subscription Management Guide

## 📋 Overview
The bot now includes a comprehensive subscription system that tracks all user details and payments in `subscriptions.json`.

## 💰 Pricing Plans

| Plan | Price | Searches/Day | Duration |
|------|-------|--------------|----------|
| 🆓 Free | ₹0 | 0 | Forever |
| 🔍 Single | ₹50 | 1 | 24 hours |
| 💎 Premium | ₹99 | 50 | 30 days |
| 🚀 Pro | ₹299 | 200 | 30 days |
| 👑 Lifetime | ₹8000 | 999 | Forever |

## 📁 Files Created

### `subscriptions.json`
Stores all user subscription data with:
- User ID, username, first name
- Current plan and payment amount
- Creation date and expiry date
- Search usage statistics
- Subscription status

### `add_subscription.py`
Admin script to manually add subscriptions:
```bash
python add_subscription.py <user_id> <username> <first_name> <plan> <payment_amount>
```

Example:
```bash
python add_subscription.py 123456789 "johndoe" "John Doe" "premium" 99
```

## 🛠️ Admin Features

### Admin Panel Access
- Use `/admin` command or click "👑 Admin Panel"
- Click "💎 Manage Subs" to view subscription management

### Subscription Management Features
- 📊 Total revenue tracking
- 👥 User count by plan
- 📋 Recent subscriber list
- 💰 Payment amount tracking

## 💳 Payment Process

1. **User selects plan** → Bot shows payment details
2. **User pays** via UPI/PhonePe/GPay:
   - UPI: `rajkumar@paytm`
   - PhonePe: `9876543210`
   - Google Pay: `rajkumar@oksbi`
3. **User sends screenshot** to @CRAZYPANEL1
4. **Admin activates** using `add_subscription.py` script

## 📊 Data Tracking

Each user record includes:
```json
{
  "user_id": 123456789,
  "username": "johndoe",
  "first_name": "John Doe",
  "plan": "premium",
  "payment_amount": 99,
  "created_date": "2025-09-18T23:00:00",
  "expires": "2025-10-18T23:00:00",
  "searches_used": 5,
  "last_reset": "2025-09-18",
  "total_searches": 25,
  "status": "active"
}
```

## 🔄 Automatic Features

- ✅ **Daily reset** of search counters at midnight
- ✅ **Expiry checking** on each bot interaction
- ✅ **Auto-save** subscription data after changes
- ✅ **User detail updates** when username/name changes

## 📈 Revenue Tracking

The admin panel shows:
- Total revenue from all plans
- User distribution across plans
- Recent subscriber activity
- Payment amounts per user

## 🚀 Usage Examples

### Add Premium User
```bash
python add_subscription.py 987654321 "premiumuser" "Premium User" "premium" 99
```

### Add Lifetime User
```bash
python add_subscription.py 555666777 "lifetimeuser" "Lifetime User" "lifetime" 8000
```

### Add Single Search
```bash
python add_subscription.py 111222333 "singleuser" "Single User" "single" 50
```

## 📱 Bot Commands

- `/start` - Main menu with subscription options
- `/admin` - Admin panel (admin only)
- `/check <number>` - Search with subscription limits
- Click "💎 Subscription" - View/upgrade plans

## 🔐 Security Features

- Admin-only access to subscription management
- Secure file-based storage
- User verification through Telegram usernames
- Payment verification through admin approval

## 💡 Tips for Admin

1. **Regular backups** of `subscriptions.json`
2. **Monitor revenue** through admin panel
3. **Verify payments** before adding subscriptions
4. **Track user engagement** through search statistics
5. **Update pricing** as needed in bot code

This system provides complete subscription management with detailed user tracking and revenue monitoring!
