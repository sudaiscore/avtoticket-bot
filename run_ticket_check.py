import asyncio
import httpx

from src.config import settings, logger
from src.parser import fetch_data
from src.storage import load_state, save_state
from src.notifier import notify_changes, send_error_alert


async def run_once():
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)

    async with httpx.AsyncClient(limits=limits) as client:
        try:
            parse_result = await fetch_data(client, settings.target_url)

            if not parse_result.success:
                logger.warning(f"Parsing amalga oshmadi. Sabab: {parse_result.error}")
                return

            if not parse_result.trips:
                logger.info(f"Sahifa o‘qildi ({parse_result.source}), lekin mos reyslar topilmadi.")
                return

            if parse_result.confidence < settings.min_confidence:
                logger.warning(
                    f"Ishonchlilik past ({parse_result.confidence:.2f} < {settings.min_confidence}). Natija inkor qilindi."
                )
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
                        changes_to_notify.append(
                            {"trip": trip, "type": "oshdi", "prev": prev_trip.available_seats}
                        )

            if changes_to_notify:
                logger.info(f"Yangi {len(changes_to_notify)} ta o‘zgarish topildi.")
                await notify_changes(client, changes_to_notify)
            else:
                logger.info(f"Mos reyslar topildi: {len(current_trips)} ta. Yangi o‘zgarish yo‘q.")

            save_state(current_trips)

        except httpx.HTTPError as e:
            error_msg = f"Tarmoq xatosi: {e}"
            logger.error(error_msg)
            await send_error_alert(client, error_msg)
        except Exception as e:
            error_msg = f"Kutilmagan xatolik: {e}"
            logger.error(error_msg)
            await send_error_alert(client, error_msg)
            raise


if __name__ == "__main__":
    asyncio.run(run_once())