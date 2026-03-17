from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    telegram_bot_token: str
    api_base_url: str = "http://localhost:8000"
    sqlite_path: str = "tg_bot/bot.sqlite3"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = BotSettings()
