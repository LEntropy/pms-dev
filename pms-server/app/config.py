from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List


class Settings(BaseSettings):
    app_name: str = "PMS Server"
    app_version: str = "0.1.0"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://pms:pms_secret@localhost:5432/pms"

    # Redis
    redis_url: str = "redis://:redis_secret@localhost:6379/0"

    # JWT
    jwt_private_key_path: str = "keys/private.pem"
    jwt_public_key_path: str = "keys/public.pem"
    jwt_algorithm: str = "RS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7
    jwt_agent_token_expire_days: int = 30

    # Security
    secret_key: str = "change_me_in_production"
    enrollment_token_expire_hours: int = 24

    # MinIO
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "pms_minio"
    minio_secret_key: str = "minio_secret"
    minio_secure: bool = False
    minio_bucket_patches: str = "patches"
    minio_bucket_agents: str = "agents"
    minio_presigned_url_expire_seconds: int = 3600

    # Agent
    agent_heartbeat_interval_seconds: int = 300
    agent_offline_threshold_seconds: int = 900  # 3 missed heartbeats

    # CORS
    cors_origins: List[str] = ["http://localhost:5173", "http://localhost:3000"]

    # SMTP (email notifications)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "pms@company.com"
    smtp_tls: bool = True

    # Agent upgrade
    latest_agent_version: str = ""
    agent_download_base_url: str = ""

    # LDAP / Active Directory
    ldap_url: str = ""
    ldap_bind_dn: str = ""
    ldap_bind_password: str = ""
    ldap_base_dn: str = "DC=company,DC=com"
    ldap_user_filter: str = "(&(objectClass=user)(objectCategory=person)(!(userAccountControl:1.2.840.113556.1.4.803:=2)))"

    # OpenVAS / GVM
    openvas_url: str = ""
    openvas_username: str = "admin"
    openvas_password: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
