import httpx
import html
from datetime import datetime
from typing import List, Dict, Any
from src.config import settings, logger

def format_price(price_str: str) -> str:
    digits = ''.join(filter(str.isdigit, price_str))
    if digits: return f"{int(digits):,}".replace(",", " ")
    return price_str

def format_route_display() -> str:
    origin = settings.target_origin_keywords.split(',')[0].strip().title()
    dest = settings.target_destination_keywords.split(',')[0].strip().title()
    return f"{origin} ➡️ {dest}"

async def send_telegram_message(client: httpx.AsyncClient, text: str) -> bool:
    if settings.test_mode:
        logger.info(f"[TEST MODE] Telegram xabari yuborilmadi. Matn:\n{text}")
        return True

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        response = await client.post(url, json=payload, timeout=10.0)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            logger.error(f"Telegram API xatosi: {data.get('description')}")
            return False
        return True
    except Exception as e:
        logger.error(f"Telegram tarmog'iga ulanishda xatolik yuz berdi: {e}")
        return False

async def notify_changes(client: httpx.AsyncClient, changes: List[Dict[str, Any]]):
    if not changes: return

    changes.sort(key=lambda x: (-x['trip'].available_seats, x['trip'].departure_time))
    display_changes = changes[:settings.max_message_trips]

    grouped = {"yangi": [], "ochildi": [], "oshdi": []}
    for c in display_changes:
        grouped[c["type"]].append(c)

    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")

    header = (
        f"🚍 <b>AvtoTicket: {len(changes)} ta yangi imkoniyat!</b>\n"
        f"📍 Yo'nalish: <b>{format_route_display()}</b>\n\n"
    )

    footer = (
        "➖➖➖➖➖➖➖➖➖➖\n"
        "⚡️ <b>Hozir sotib olish tavsiya etiladi!</b>\n\n"
        f"🔗 <a href='{settings.target_url}'>Saytga o'tish va chipta olish</a>\n"
        f"⏱ <i>Oxirgi tekshiruv: {now_str}</i>"
    )

    MAX_SAFE_LEN = 3800
    msg = header
    limit_reached = False

    group_titles = {
        "yangi": "🆕 <b>YANGI REYSLAR QO'SHILDI:</b>\n",
        "ochildi": "🔓 <b>JOY OCHILDI (Oldin 0 edi):</b>\n",
        "oshdi": "📈 <b>JOY TASHLANDI / OSHDI:</b>\n"
    }

    for g_type in ["yangi", "ochildi", "oshdi"]:
        if not grouped[g_type]: continue

        group_header = group_titles[g_type]
        if len(msg) + len(group_header) + len(footer) > MAX_SAFE_LEN:
            limit_reached = True
            break

        msg += group_header

        for c in grouped[g_type]:
            trip = c["trip"]
            r_name = html.escape(trip.route_name)
            bus = html.escape(trip.bus_model)
            price = format_price(trip.price)

            item_str = ""
            if g_type == "yangi":
                item_str += f"🔹 <b>{trip.departure_time}</b> | 💺 ✅ <b>{trip.available_seats} ta joy</b> (Yangi)\n"
            elif g_type == "ochildi":
                item_str += f"🔹 <b>{trip.departure_time}</b> | 💺 <b>0 ➡️ {trip.available_seats} ta joy</b>\n"
            elif g_type == "oshdi":
                prev = c["prev"]
                item_str += f"🔹 <b>{trip.departure_time}</b> | 💺 <b>{prev} ➡️ {trip.available_seats} ta joy</b>\n"

            item_str += f"   💰 {price} so'm | 🚌 {bus}\n"
            item_str += f"   🛣 <i>{r_name}</i>\n\n"

            if len(msg) + len(item_str) + len(footer) > MAX_SAFE_LEN:
                limit_reached = True
                break

            msg += item_str

        if limit_reached: break

    if limit_reached:
        msg += "<i>... xabar uzunligi sababli qolganlari ko'rsatilmadi.</i>\n\n"
    elif len(changes) > settings.max_message_trips:
        msg += f"<i>... va yana {len(changes) - settings.max_message_trips} ta mos reys bor.</i>\n\n"

    msg += footer

    success = await send_telegram_message(client, msg)
    if success:
        logger.info("Foydalanuvchiga xavfsiz uzunlikdagi Telegram bildirishnomasi yuborildi.")

async def send_error_alert(client: httpx.AsyncClient, error_text: str):
    if not settings.send_error_alerts: return
    msg = f"⚠️ <b>AvtoTicket Bot: Tizimli Xatolik</b>\n\n<pre>{html.escape(error_text)}</pre>"
    await send_telegram_message(client, msg)