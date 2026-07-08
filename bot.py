import os
import logging
import re
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
PSI_API_KEY = os.environ.get("PSI_API_KEY")  # optional but recommended (higher rate limits)

PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

CATEGORIES = ["performance", "accessibility", "best-practices", "seo"]
CATEGORY_LABELS = {
    "performance": "Performance",
    "accessibility": "Accessibility",
    "best-practices": "Best Practices",
    "seo": "SEO",
}


def normalize_url(text: str) -> str:
    text = text.strip()
    if not re.match(r"^https?://", text, re.IGNORECASE):
        text = "https://" + text
    return text


def score_emoji(score: float) -> str:
    if score >= 90:
        return "🟢"
    if score >= 50:
        return "🟠"
    return "🔴"


def run_pagespeed(url: str, strategy: str) -> dict:
    params = {
        "url": url,
        "strategy": strategy,
        "category": CATEGORIES,
    }
    if PSI_API_KEY:
        params["key"] = PSI_API_KEY

    resp = requests.get(PSI_ENDPOINT, params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


def format_result(url: str, strategy: str, data: dict) -> str:
    lighthouse = data.get("lighthouseResult", {})
    categories = lighthouse.get("categories", {})

    lines = [f"📊 *PageSpeed Insights* ({strategy.capitalize()})", f"🔗 {url}", ""]

    for key in CATEGORIES:
        cat = categories.get(key)
        if not cat:
            continue
        score = round(cat.get("score", 0) * 100)
        label = CATEGORY_LABELS.get(key, key)
        lines.append(f"{score_emoji(score)} *{label}:* {score}/100")

    audits = lighthouse.get("audits", {})
    metrics = {
        "first-contentful-paint": "First Contentful Paint",
        "largest-contentful-paint": "Largest Contentful Paint",
        "total-blocking-time": "Total Blocking Time",
        "cumulative-layout-shift": "Cumulative Layout Shift",
        "speed-index": "Speed Index",
    }
    metric_lines = []
    for key, label in metrics.items():
        audit = audits.get(key)
        if audit and "displayValue" in audit:
            metric_lines.append(f"• {label}: {audit['displayValue']}")

    if metric_lines:
        lines.append("")
        lines.append("*Key Metrics:*")
        lines.extend(metric_lines)

    return "\n".join(lines)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hi! I'm JESSYNAI Bot — a PageSpeed Insights bot.\n\n"
        "Send me any URL and I'll analyze it for Performance, Accessibility, "
        "Best Practices, and SEO — just like Google's PageSpeed Insights tool.\n\n"
        "Example: `example.com`",
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Just send me a URL (e.g. `example.com` or `https://example.com`) "
        "and choose Mobile, Desktop, or Both.",
        parse_mode="Markdown",
    )


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    url = normalize_url(text)

    context.user_data["pending_url"] = url

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📱 Mobile", callback_data="mobile"),
                InlineKeyboardButton("🖥 Desktop", callback_data="desktop"),
            ],
            [InlineKeyboardButton("🔁 Both", callback_data="both")],
        ]
    )
    await update.message.reply_text(
        f"Analyze which version of:\n{url}", reply_markup=keyboard
    )


async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    url = context.user_data.get("pending_url")
    if not url:
        await query.edit_message_text("Session expired — please send the URL again.")
        return

    choice = query.data
    strategies = ["mobile", "desktop"] if choice == "both" else [choice]

    await query.edit_message_text(f"⏳ Analyzing {url} ({choice})...")

    for strategy in strategies:
        try:
            data = run_pagespeed(url, strategy)
            message = format_result(url, strategy, data)
        except requests.exceptions.HTTPError as e:
            message = f"❌ Error analyzing {url} ({strategy}): {e}"
        except Exception as e:
            logger.exception("PageSpeed analysis failed")
            message = f"❌ Something went wrong analyzing {url} ({strategy}): {e}"

        await context.bot.send_message(
            chat_id=query.message.chat_id, text=message, parse_mode="Markdown"
        )


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is not set")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(handle_choice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))

    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
