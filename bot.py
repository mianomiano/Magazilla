import os, json, logging, requests
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, PreCheckoutQueryHandler, CallbackQueryHandler
from dotenv import load_dotenv
load_dotenv()
logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.getenv('BOT_TOKEN')
WEBAPP = os.getenv('APP_URL','')

async def start(u: Update, c):
    kb = [[InlineKeyboardButton("🎨 Open Store", web_app=WebAppInfo(url=WEBAPP))],
          [InlineKeyboardButton("🆓 Free", callback_data="free"),InlineKeyboardButton("ℹ️ Help", callback_data="help")]]
    await u.message.reply_text(f"🎨 *Magazilla*\n\nDesign assets store ⭐",reply_markup=InlineKeyboardMarkup(kb),parse_mode='Markdown')

async def cb(u: Update, c):
    q = u.callback_query; await q.answer()
    if q.data=="free":
        await q.edit_message_text("Free:",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🆓 Free",web_app=WebAppInfo(url=f"{WEBAPP}?filter=free"))]]))
    elif q.data=="help":
        await q.edit_message_text("🎨 /start /free /help\n\nStars ⭐ for premium")

async def precheckout(u: Update, c): await u.pre_checkout_query.answer(ok=True)

async def paid(u: Update, c):
    p = u.message.successful_payment
    try:
        pid = int(p.invoice_payload.split('_')[1])
        requests.post(f"{WEBAPP}/api/verify-purchase",json={'user_id':u.effective_user.id,'product_id':pid,'payment_id':p.telegram_payment_charge_id,'stars_paid':p.total_amount},timeout=10)
        kb = [[InlineKeyboardButton("⬇️ Download",web_app=WebAppInfo(url=f"{WEBAPP}/product/{pid}?user_id={u.effective_user.id}"))]]
        await u.message.reply_text("🎉 *Paid!*",reply_markup=InlineKeyboardMarkup(kb),parse_mode='Markdown')
    except: await u.message.reply_text("✅ Paid!")

def main():
    if not BOT_TOKEN: print("❌ No BOT_TOKEN"); return
    print(f"🤖 Bot starting...\n📱 {WEBAPP}\n✅ Running")
    a = Application.builder().token(BOT_TOKEN).build()
    a.add_handler(CommandHandler("start",start))
    a.add_handler(CommandHandler("free",lambda u,c:u.message.reply_text("Free:",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🆓",web_app=WebAppInfo(url=f"{WEBAPP}?filter=free"))]]))))
    a.add_handler(CommandHandler("help",lambda u,c:u.message.reply_text("🎨 /start /free /help")))
    a.add_handler(CallbackQueryHandler(cb))
    a.add_handler(PreCheckoutQueryHandler(precheckout))
    a.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT,paid))
    a.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__=='__main__': main()
