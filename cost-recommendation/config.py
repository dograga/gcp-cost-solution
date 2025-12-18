"""
Configuration module for cost-recommendation cron job.
Uses Pydantic for settings management and validation.
"""

import os
from typing import List, Optional, Union
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from dotenv import load_dotenv

# Explicitly load .env files to ensure they are present in os.environ
# This helps if Pydantic's env_file logic is bypassed or behaves differently
# Load specific environment file FIRST (e.g., .env.dev) so it takes precedence over .env
# but does NOT override system environment variables.
env_name = os.getenv('APP_ENV') or os.getenv('ENVIRONMENT') or 'dev'
load_dotenv(f".env.{env_name.lower()}")
load_dotenv() # Load generic .env as fallback

class Settings(BaseSettings):
    """Base settings for the application."""
    
    # Application settings
    app_name: str = "CostRecommendationCollector"
    environment: str = "dev"
    log_level: str = "INFO"
    
    # GCP Project Configuration
    # Try to get from GCP_PROJECT_ID, then GCP_PROJECT (standard in Cloud Run), else None
    gcp_project_id: Optional[str] = Field(default=None, validation_alias="GCP_PROJECT_ID")
    
    @field_validator('gcp_project_id', mode='before')
    @classmethod
    def set_gcp_project_id(cls, v):
        if v:
            return v
        return os.getenv("GCP_PROJECT")

    # Billing Account Configuration
    # Comma-separated list of billing account IDs in env, converted to list
    # Use Union[str, List[str]] to handle env var string parsing
    billing_account_ids: Union[str, List[str]] = Field(default_factory=list)
    
    @field_validator('billing_account_ids', mode='before')
    @classmethod
    def split_comma_separated_string(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [i.strip() for i in v.split(',') if i.strip()]
        return v
    
    # Scope Configuration
    scope_type: str = "project"
    scope_id: Optional[str] = None
    
    @field_validator('scope_id')
    @classmethod
    def set_scope_id_default(cls, v, info):
        # If scope_id is not set, default to gcp_project_id
        if v is None and info.data.get('gcp_project_id'):
            return info.data['gcp_project_id']
        return v

    # Firestore Configuration
    firestore_database: str = "(default)"
    firestore_collection: str = "cost_recommendations"
    
    # Project Inventory Configuration
    use_inventory_collection: bool = True
    inventory_database: str = "dashboard"
    inventory_collection: str = "projects"
    inventory_project_id_field: str = "project_id"
    inventory_app_code_field: str = "app_code"
    inventory_bu_code_field: str = "bu_code"
    
    # Recommender Configuration
    recommender_types: Union[str, List[str]] = Field(default_factory=list)
    recommendation_state_filter: str = "ACTIVE"
    recommender_locations: Union[str, List[str]] = Field(default=["global"])
    
    @field_validator('recommender_types', 'recommender_locations', mode='before')
    @classmethod
    def split_list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [i.strip() for i in v.split(',') if i.strip()]
        return v
    
    # Performance Configuration
    max_workers: int = 10
    firestore_batch_size: int = 500
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore"
    )

class LocalSettings(Settings):
    """Local development settings."""
    environment: str = "local"
    log_level: str = "DEBUG"
    firestore_collection: str = "cost_recommendations_local"
    
    model_config = SettingsConfigDict(
        env_file=".env.local",
        case_sensitive=False,
        extra="ignore"
    )

class DevSettings(Settings):
    """Development environment settings."""
    environment: str = "dev"
    log_level: str = "DEBUG"
    firestore_collection: str = "cost_recommendations_dev"
    
    model_config = SettingsConfigDict(
        env_file=".env.dev",
        case_sensitive=False,
        extra="ignore"
    )

class UatSettings(Settings):
    """UAT environment settings."""
    environment: str = "uat"
    log_level: str = "INFO"
    firestore_collection: str = "cost_recommendations_uat"
    
    model_config = SettingsConfigDict(
        env_file=".env.uat",
        case_sensitive=False,
        extra="ignore"
    )

class ProdSettings(Settings):
    """Production environment settings."""
    environment: str = "prod"
    log_level: str = "WARNING"
    firestore_collection: str = "cost_recommendations"
    
    model_config = SettingsConfigDict(
        env_file=".env.prod",
        case_sensitive=False,
        extra="ignore"
    )

def get_settings_class():
    """Determine the settings class based on the environment."""
    env = (os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or "dev").lower()
    settings_map = {
        "local": LocalSettings,
        "dev": DevSettings,
        "uat": UatSettings,
        "prod": ProdSettings
    }
    return settings_map.get(env, DevSettings)

@lru_cache()
def get_settings() -> Settings:
    """Return a cached instance of the settings."""
    settings_class = get_settings_class()
    return settings_class()

# For backward compatibility during refactor if needed, but main.py should use get_settings()
CONFIG = get_settings().model_dump()
