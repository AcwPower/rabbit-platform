from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str
    secret_key: str
    contact_key: str
    public_origin: str = 'http://127.0.0.1:5173'
    cookie_secure: bool = True
    ocr_url: str = 'http://127.0.0.1:8102'
    ocr_secret: str
    smtp_host: str = ''
    smtp_port: int = 587
    smtp_user: str = ''
    smtp_password: str = ''
    smtp_from: str = ''
    smtp_starttls: bool = True
    teammate_recruitment_enabled: bool = False
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

settings = Settings()
if len(settings.secret_key) < 32:
    raise RuntimeError('SECRET_KEY must contain at least 32 characters')
