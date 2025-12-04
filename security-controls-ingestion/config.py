import os
from typing import Optional, List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from functools import lru_cache

class Settings(BaseSettings):
    # Application settings
    app_name: str = "SecurityControlsIngestion"
    app_version: str = "0.1.0"
    app_env: str = "local"
    debug: bool = False
    
    # Firestore/Datastore settings
    use_firestore: bool = True
    gcp_project_id: str = "your-gcp-project-id"
    firestore_database: str = "(default)"
    
    # Collection names
    # Collection names
    firestore_collection_controls: str = "controls"
    firestore_collection_firewall_rules: str = "firewall_rules"
    firestore_collection_iam_roles: str = "iam_roles"
    
    # Ingestion Scope Settings
    # Scope Type: "organization" or "folder"
    ingestion_scope_type: str = "organization"
    # Scope ID: The Organization ID or Folder ID
    ingestion_scope_id: str = "123456789"
    
    # Logging
    log_level: str = "INFO"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore"
    )

class LocalSettings(Settings):
    debug: bool = True
    log_level: str = "DEBUG"
    gcp_project_id: str = "local-dev-project"
    
    model_config = SettingsConfigDict(
        env_file=".env.local",
        case_sensitive=False,
        extra="ignore"
    )

class DevSettings(Settings):
    debug: bool = False
    app_env: str = "dev"
    log_level: str = "INFO"
    gcp_project_id: str = "opsengine-dev"
    
    model_config = SettingsConfigDict(
        env_file=".env.dev",
        case_sensitive=False,
        extra="ignore"
    )

class UatSettings(Settings):
    debug: bool = False
    app_env: str = "uat"
    log_level: str = "INFO"
    gcp_project_id: str = "opsengine-uat"
    
    model_config = SettingsConfigDict(
        env_file=".env.uat",
        case_sensitive=False,
        extra="ignore"
    )

class ProdSettings(Settings):
    debug: bool = False
    app_env: str = "prod"
    log_level: str = "WARNING"
    gcp_project_id: str = "opsengine-prod"
    
    model_config = SettingsConfigDict(
        env_file=".env.prod",
        case_sensitive=False,
        extra="ignore"
    )

def get_settings_class():
    # Check both APP_ENV and ENVIRONMENT for compatibility
    env = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "local")).lower()
    settings_map = {
        "local": LocalSettings,
        "dev": DevSettings,
        "uat": UatSettings,
        "prod": ProdSettings
    }
    return settings_map.get(env, LocalSettings)

@lru_cache()
def get_settings() -> Settings:
    settings_class = get_settings_class()
    return settings_class()
