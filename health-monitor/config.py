"""
Configuration module for health-monitor job.
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

# Organization Configuration
ORGANIZATION_ID = os.environ.get('ORGANIZATION_ID')
if not ORGANIZATION_ID:
    raise ValueError(f"ORGANIZATION_ID must be set in .env.{ENVIRONMENT} or environment variables")

# Firestore Configuration
FIRESTORE_DATABASE = os.environ.get('FIRESTORE_DATABASE', '(default)')
REGION_STATUS_COLLECTION = os.environ.get('REGION_STATUS_COLLECTION', 'region_status')
EVENTS_COLLECTION = os.environ.get('EVENTS_COLLECTION', 'health_events')

# Regions to Monitor
# Comma-separated list of regions to monitor
REGIONS_STR = os.environ.get('REGIONS', 'asia-southeast1,asia-southeast2,asia-south1,asia-south2,global')
REGIONS = [r.strip() for r in REGIONS_STR.split(',') if r.strip()]

# Event Categories to Monitor
# Comma-separated list of event categories (leave empty for all)
EVENT_CATEGORIES_STR = os.environ.get('EVENT_CATEGORIES', '')
EVENT_CATEGORIES = [c.strip() for c in EVENT_CATEGORIES_STR.split(',') if c.strip()] if EVENT_CATEGORIES_STR else []

# Logging Configuration
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

# Configuration summary
CONFIG = {
    'environment': ENVIRONMENT,
    'gcp_project_id': GCP_PROJECT_ID,
    'organization_id': ORGANIZATION_ID,
    'firestore_database': FIRESTORE_DATABASE,
    'region_status_collection': REGION_STATUS_COLLECTION,
    'events_collection': EVENTS_COLLECTION,
    'regions': REGIONS,
    'event_categories': EVENT_CATEGORIES,
    'log_level': LOG_LEVEL,
}
