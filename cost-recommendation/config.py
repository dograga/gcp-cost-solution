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

# Scope Configuration (Project, Folder, or Organization)
# SCOPE_TYPE: 'project', 'folder', or 'organization'
SCOPE_TYPE = os.environ.get('SCOPE_TYPE', 'project').lower()
# SCOPE_ID: Project ID, Folder ID (folders/123456), or Org ID (organizations/123456)
SCOPE_ID = os.environ.get('SCOPE_ID', GCP_PROJECT_ID)

# Firestore Configuration
FIRESTORE_DATABASE = os.environ.get('FIRESTORE_DATABASE', '(default)')
FIRESTORE_COLLECTION = os.environ.get('FIRESTORE_COLLECTION', 'cost_recommendations')

# Project Inventory Configuration
# Set USE_INVENTORY_COLLECTION=true to read projects from Firestore inventory
USE_INVENTORY_COLLECTION = True
INVENTORY_DATABASE = "dashboard"
INVENTORY_COLLECTION = "projects"
INVENTORY_PROJECT_ID_FIELD = "project_id"

# Recommender Configuration
# Recommender types to fetch (comma-separated)
# Leave empty or set to empty string to fetch ALL available recommender types
RECOMMENDER_TYPES_STR = os.environ.get('RECOMMENDER_TYPES', '')
RECOMMENDER_TYPES = [r.strip() for r in RECOMMENDER_TYPES_STR.split(',') if r.strip()] if RECOMMENDER_TYPES_STR else []

# Filter recommendations by state (ACTIVE, CLAIMED, SUCCEEDED, FAILED, DISMISSED)
RECOMMENDATION_STATE_FILTER = os.environ.get('RECOMMENDATION_STATE_FILTER', 'ACTIVE')

# Recommender Locations
# Comma-separated list of locations to check (e.g., global,us-central1,us-central1-a)
# Defaults to 'global' if not specified
RECOMMENDER_LOCATIONS_STR = os.environ.get('RECOMMENDER_LOCATIONS', 'global')
RECOMMENDER_LOCATIONS = [l.strip() for l in RECOMMENDER_LOCATIONS_STR.split(',') if l.strip()]

# Performance Configuration
# Number of parallel threads for processing projects
MAX_WORKERS = int(os.environ.get('MAX_WORKERS', '10'))
# Batch size for saving recommendations to Firestore
FIRESTORE_BATCH_SIZE = int(os.environ.get('FIRESTORE_BATCH_SIZE', '500'))

# Logging Configuration
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

# Configuration summary
CONFIG = {
    'environment': ENVIRONMENT,
    'gcp_project_id': GCP_PROJECT_ID,
    'scope_type': SCOPE_TYPE,
    'scope_id': SCOPE_ID,
    'firestore_database': FIRESTORE_DATABASE,
    'firestore_collection': FIRESTORE_COLLECTION,
    'use_inventory_collection': USE_INVENTORY_COLLECTION,
    'inventory_database': INVENTORY_DATABASE,
    'inventory_collection': INVENTORY_COLLECTION,
    'inventory_project_id_field': INVENTORY_PROJECT_ID_FIELD,
    'recommender_types': RECOMMENDER_TYPES,
    'recommendation_state_filter': RECOMMENDATION_STATE_FILTER,
    'max_workers': MAX_WORKERS,
    'firestore_batch_size': FIRESTORE_BATCH_SIZE,
    'log_level': LOG_LEVEL,
}
