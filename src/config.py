import logging
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    telegram_bot_token: str
    telegram_chat_id: str
    target_url: str
    check_interval: int = 180
    test_mode: bool = False
    notify_on_startup: bool = True
    min_confidence: float = 0.70

    target_origin_keywords: str = "toshkent,ташкент,tashkent"
    target_destination_keywords: str = "shahrisabz,шахрисабз"
    require_all_route_keywords: bool = True

    max_message_trips: int = 10
    send_error_alerts: bool = False
    log_no_change_as_info: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()

log_level = logging.DEBUG if settings.test_mode else logging.INFO
logging.basicConfig(
    level=log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("AvtoTicketBot")