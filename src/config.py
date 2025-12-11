from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    REDIS_URL: str = 'redis://localhost:6379'
    WEBSOCKET_URL: str = 'http://host.docker.internal:8000'

    class Config:
        env_file = '.env'


settings = Settings()