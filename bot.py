"""Telegram Bot with Webhook Support"""
import os
import logging
import requests
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv('BOT_TOKEN')
WEBAPP_URL = os.getenv('APP_URL', 'https://web-production-36eec.up.railway.app')
WEBHOOK_URL = f"{WEBAPP_URL}/api/webhook/telegram"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command"""
    keyboard = [
        [InlineKeyboardButton("🎨 Open Store", web_app=WebAppInfo(url=WEBAPP_URL))],
        [
            InlineKeyboardButton("🆓 Free", callback_data="free"),
            InlineKeyboardButton("ℹ️ Help", callback_data="help")
        ]
    ]
    
    await update.message.reply_text(
        "🎨 *Magazilla*\n\nYour design assets store ⭐",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def free_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show free products"""
    keyboard = [[
        InlineKeyboardButton(
            "🆓 Browse Free",
            web_app=WebAppInfo(url=f"{WEBAPP_URL}?filter=free")
        )
    ]]
    await update.message.reply_text(
        "Browse free design assets:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command"""
    help_text = """
🎨 *Magazilla Commands*

/start - Open the store
/free - Browse free products
/help - Show this help

💫 Premium products available with Telegram Stars ⭐
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')


def setup_webhook():
    """Setup Telegram webhook"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
    payload = {
        'url': WEBHOOK_URL,
        'allowed_updates': ['message', 'pre_checkout_query']
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        result = response.json()
        
        if result.get('ok'):
            print(f"✅ Webhook set: {WEBHOOK_URL}")
            return True
        else:
            print(f"❌ Webhook failed: {result.get('description')}")
            return False
    except Exception as e:
        print(f"❌ Webhook error: {e}")
        return False


def main():
    """Main bot function"""
    if not BOT_TOKEN:
        print("❌ No BOT_TOKEN")
        return
    
    print(f"🤖 Bot starting...")
    print(f"📱 WebApp: {WEBAPP_URL}")
    
    # Setup webhook for production
    if os.getenv('RAILWAY_ENVIRONMENT'):
        if setup_webhook():
            print("✅ Webhook mode (production)")
            return
    
    # Polling for development
    print("✅ Polling mode (development)")
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("free", free_command))
    app.add_handler(CommandHandler("help", help_command))
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
