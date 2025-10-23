"""
Configuration module for cost-recommendation cron job.
Loads environment-specific settings from .env files.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Determine environment
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')

# Load environment-specific .env file
env_file = Path(__file__).parent / f'.env.{ENVIRONMENT}'
if env_file.exists():
    load_dotenv(env_file)
    print(f"Loaded configuration from {env_file}")
else:
    print(f"Warning: {env_file} not found, using environment variables or defaults")

# GCP Project Configuration
GCP_PROJECT_ID = os.environ.get('GCP_PROJECT_ID')
if not GCP_PROJECT_ID:
    raise ValueError(f"GCP_PROJECT_ID must be set in .env.{ENVIRONMENT} or environment variables")

# Firestore Configuration
FIRESTORE_DATABASE = os.environ.get('FIRESTORE_DATABASE', '(default)')
FIRESTORE_COLLECTION = os.environ.get('FIRESTORE_COLLECTION', 'cost_recommendations')

# Recommender Configuration
# Recommender types to fetch (comma-separated)
# Leave empty or set to empty string to fetch ALL available recommender types
RECOMMENDER_TYPES_STR = os.environ.get('RECOMMENDER_TYPES', '')
RECOMMENDER_TYPES = [r.strip() for r in RECOMMENDER_TYPES_STR.split(',') if r.strip()] if RECOMMENDER_TYPES_STR else []

# Filter recommendations by state (ACTIVE, CLAIMED, SUCCEEDED, FAILED, DISMISSED)
RECOMMENDATION_STATE_FILTER = os.environ.get('RECOMMENDATION_STATE_FILTER', 'ACTIVE')

# Logging Configuration
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

# Configuration summary
CONFIG = {
    'environment': ENVIRONMENT,
    'gcp_project_id': GCP_PROJECT_ID,
    'firestore_database': FIRESTORE_DATABASE,
    'firestore_collection': FIRESTORE_COLLECTION,
    'recommender_types': RECOMMENDER_TYPES,
    'recommendation_state_filter': RECOMMENDATION_STATE_FILTER,
    'log_level': LOG_LEVEL,
}
