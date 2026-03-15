import asyncio
import signal
import sys
import httpx
from datetime import datetime
from src.config import settings, logger
from src.parser import fetch_data
from src.storage import load_state, save_state
from src.notifier import send_telegram_message, notify_changes, send_error_alert, format_route_display

shutdown_event = asyncio.Event()

bot_status = {
    "last_check": "Hali tekshirilmadi",
    "last_source": "Noma'lum",
    "last_confidence": 0.0,
    "total_trips": 0
}

def setup_signal_handlers():
    if sys.platform != 'win32':
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, shutdown_event.set)
            except NotImplementedError: pass

def log_current_status():
    logger.info(
        f"[STATUS] Oxirgi so'rov: {bot_status['last_check']} | "
        f"Manba: {bot_status['last_source'].upper()} | "
        f"Ishonchlilik: {bot_status['last_confidence']:.2f} | "
        f"Mos reyslar: {bot_status['total_trips']} ta"
    )

async def check_tickets(client: httpx.AsyncClient):
    try:
        parse_result = await fetch_data(client, settings.target_url)
        bot_status["last_check"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not parse_result.success:
            logger.warning(f"Parsing amalga oshmadi. Sabab: {parse_result.error}")
            return

        bot_status["last_source"] = str(parse_result.source)
        bot_status["last_confidence"] = parse_result.confidence
        bot_status["total_trips"] = len(parse_result.trips)

        if not parse_result.trips:
            msg = f"Sahifa o'qildi ({parse_result.source}), lekin yo'nalish bo'yicha reyslar topilmadi."
            if settings.log_no_change_as_info: logger.info(msg)
            else: logger.debug(msg)
            return

        if parse_result.confidence < settings.min_confidence:
            logger.warning(f"Ishonchlilik past ({parse_result.confidence:.2f} < {settings.min_confidence}). Natija inkor qilindi.")
            return

        current_trips = {trip.unique_id: trip for trip in parse_result.trips}
        previous_trips = load_state()
        changes_to_notify = []

        for trip_id, trip in current_trips.items():
            if trip_id not in previous_trips:
                if trip.available_seats > 0:
                    changes_to_notify.append({"trip": trip, "type": "yangi", "prev": 0})
            else:
                prev_trip = previous_trips[trip_id]
                if prev_trip.available_seats == 0 and trip.available_seats > 0:
                    changes_to_notify.append({"trip": trip, "type": "ochildi", "prev": 0})
                elif trip.available_seats > prev_trip.available_seats and prev_trip.available_seats > 0:
                    changes_to_notify.append({"trip": trip, "type": "oshdi", "prev": prev_trip.available_seats})

        if changes_to_notify:
            logger.info(f"🎉 Yangi {len(changes_to_notify)} ta o'zgarish topildi!")
            await notify_changes(client, changes_to_notify)
        else:
            if settings.log_no_change_as_info: log_current_status()
            else: logger.debug(f"O'zgarish yo'q. Topilgan reyslar: {len(current_trips)}.")

        if not settings.test_mode:
            save_state(current_trips)

    except httpx.HTTPError as e:
        error_msg = f"Tarmoq xatosi: {e}"
        logger.error(error_msg)
        await send_error_alert(client, error_msg)
    except Exception as e:
        error_msg = f"Kutilmagan xatolik: {e}"
        logger.error(error_msg)
        await send_error_alert(client, error_msg)

async def main():
    setup_signal_handlers()
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)

    logger.info("===" * 15)
    logger.info("🚀 AVTOTICKET BOT ISHGA TUSHDI")
    logger.info(f"Target URL: {settings.target_url}")
    logger.info(f"Route Filter: {format_route_display()}")
    logger.info(f"Interval: Har {settings.check_interval} soniyada")
    logger.info(f"Min Confidence: {settings.min_confidence}")
    logger.info(f"Mode: {'TEST (Log only)' if settings.test_mode else 'PRODUCTION (Telegram Alerts)'}")
    logger.info("===" * 15)

    async with httpx.AsyncClient(limits=limits) as client:
        if settings.notify_on_startup:
            mode_badge = "🧪 [TEST REJIMI] " if settings.test_mode else "🟢 "
            short_url = settings.target_url.split('?')[0] if '?' in settings.target_url else settings.target_url

            startup_msg = (
                f"{mode_badge}<b>Bot monitoringni boshladi.</b>\n\n"
                f"📍 <b>Yo'nalish:</b> {format_route_display()}\n"
                f"🔗 <b>Manzil:</b> <a href='{settings.target_url}'>{short_url}</a>\n"
                f"⏱ <b>Tekshiruv oralig'i:</b> {settings.check_interval} soniya\n\n"
                f"<i>Bo'sh joy ochilishi bilan sizga shu yerga xabar beraman.</i>"
            )
            await send_telegram_message(client, startup_msg)

        while not shutdown_event.is_set():
            await check_tickets(client)
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=settings.check_interval)
            except asyncio.TimeoutError:
                continue

    logger.info("Bot ishi xavfsiz yakunlandi (Clean Shutdown).")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Dastur foydalanuvchi tomonidan to'xtatildi (Ctrl+C).")
        shutdown_event.set()