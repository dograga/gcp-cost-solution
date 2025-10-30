"""Configuration module for notification API"""

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

# API Configuration
API_HOST = os.environ.get('API_HOST', '0.0.0.0')
API_PORT = int(os.environ.get('API_PORT', '8080'))
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

# CORS Configuration
ALLOWED_ORIGINS = os.environ.get('ALLOWED_ORIGINS', '*').split(',')

# GCP Configuration
GCP_PROJECT_ID = os.environ.get('GCP_PROJECT_ID')
if not GCP_PROJECT_ID:
    raise ValueError(f"GCP_PROJECT_ID must be set in .env.{ENVIRONMENT} or environment variables")

# Firestore Configuration
FIRESTORE_COLLECTION = os.environ.get('FIRESTORE_COLLECTION', 'teams-notification-channels')

# Verification Configuration
VERIFICATION_CODE_EXPIRY_MINUTES = int(os.environ.get('VERIFICATION_CODE_EXPIRY_MINUTES', '15'))

print(f"Environment: {ENVIRONMENT}")
print(f"GCP Project: {GCP_PROJECT_ID}")
print(f"Firestore Collection: {FIRESTORE_COLLECTION}")
print(f"Verification Code Expiry: {VERIFICATION_CODE_EXPIRY_MINUTES} minutes")
