# 📱 Telegram Notification Configuration Guide

> QuantDinger supports real-time strategy signal notifications via Telegram Bot.

---

## 📋 Table of Contents

- [Prerequisites](#prerequisites)
- [Step 1: Create a Telegram Bot](#step-1-create-a-telegram-bot)
- [Step 2: Obtain Bot Token](#step-2-obtain-bot-token)
- [Step 3: Get Your User ID](#step-3-get-your-user-id)
- [Step 4: Configure Environment Variables](#step-4-configure-environment-variables)
- [Step 5: Enable Telegram Notifications in Strategy](#step-5-enable-telegram-notifications-in-strategy)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

- Telegram client installed (mobile or desktop)
- Active Telegram account
- QuantDinger backend service deployed and running

---

## Step 1: Create a Telegram Bot

1. Search for **@BotFather** in Telegram (official bot management tool)
2. Send the `/newbot` command to create a new bot
3. Enter a display name for your bot (e.g., `QuantDinger Signal Bot`)
4. Choose a unique username ending with `bot` (e.g., `quantdinger_signal_bot`)

<img src="./screenshots/notification_telegram_token.png" alt="Create Telegram Bot" width="100%" style="border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">

---

## Step 2: Obtain Bot Token

Upon successful creation, BotFather will provide an **HTTP API Token** in this format:

```
123456789:ABCdefGHIjklMNOpqrsTUVwxyz
```

> ⚠️ **Security Notice**: Keep this token secure and never share it publicly. If compromised, use `/revoke` command in BotFather to regenerate immediately.

---

## Step 3: Get Your User ID

### Method 1: Via Telegram API (Recommended)

1. First, send any message to your newly created bot (e.g., `/start`)
2. Visit the following URL in your browser (replace `YOUR_BOT_TOKEN` with your actual token):

```
https://api.telegram.org/bot{YOUR_BOT_TOKEN}/getUpdates
```

**Example**:
```
https://api.telegram.org/bot123456789:ABCdefGHIjklMNOpqrsTUVwxyz/getUpdates
```

3. Locate the `chat.id` field in the JSON response — this is your User ID

<img src="./screenshots/notification_telegram_userid_get.png" alt="Get User ID" width="100%" style="border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">

### Method 2: Via @userinfobot

1. Search for **@userinfobot** in Telegram
2. Send any message, and it will reply with your User ID

---

## Step 4: Configure Environment Variables

Add the Bot Token to your `backend_api_python/.env` file:

```bash
# Telegram Bot Token (required)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
```

Restart the backend service after configuration to apply changes.

---

## Step 5: Enable Telegram Notifications in Strategy

In the strategy configuration page under "Signal Notifications":

1. Enable the **Telegram** notification channel
2. Enter your Telegram User ID in the designated field

<img src="./screenshots/notification_telegram_userid.png" alt="Configure User ID" width="100%" style="border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">

> 💡 **Tip**: You can enter multiple User IDs (comma-separated) or group/channel IDs for multi-recipient notifications.

---

## Troubleshooting

### Q: Not receiving notifications?

1. Ensure you've sent a message to the bot first (bot must be activated)
2. Verify `TELEGRAM_BOT_TOKEN` environment variable is correctly configured
3. Double-check the User ID is correct
4. Review backend logs for error messages

### Q: Can I send to groups?

Yes. Add the bot to a group, then use the group ID (negative number) as the target. Obtain the group ID using the same method as personal ID.

### Q: What's the token format?

Token format is `numbers:alphanumeric_string`, e.g., `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`

---

## Related Documentation

- [Email SMTP Notification Configuration](./NOTIFICATION_EMAIL_CONFIG_EN.md)
- [SMS Notification Configuration](./NOTIFICATION_SMS_CONFIG_EN.md)
- [Strategy Development Guide](./STRATEGY_DEV_GUIDE.md)
