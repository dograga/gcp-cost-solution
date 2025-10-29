"""
Configuration module for deployment-pipeline.
Loads environment-specific settings from .env files.
"""

import os
from pathlib import Path
from typing import List, Dict
from dotenv import load_dotenv
import yaml

# Determine environment
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')

# Load environment-specific .env file
env_file = Path(__file__).parent / f'.env.{ENVIRONMENT}'
if env_file.exists():
    load_dotenv(env_file)
    print(f"Loaded configuration from {env_file}")
else:
    print(f"Warning: {env_file} not found, using environment variables or defaults")

# Bitbucket Configuration
BITBUCKET_BASE_URL = os.environ.get('BITBUCKET_BASE_URL')
if not BITBUCKET_BASE_URL:
    raise ValueError(f"BITBUCKET_BASE_URL must be set in .env.{ENVIRONMENT} or environment variables")

BITBUCKET_USERNAME = os.environ.get('BITBUCKET_USERNAME')
BITBUCKET_APP_PASSWORD = os.environ.get('BITBUCKET_APP_PASSWORD')
SOURCE_BRANCH = os.environ.get('SOURCE_BRANCH', 'uat')

# Services Configuration
SERVICES_CONFIG_FILE = os.environ.get('SERVICES_CONFIG_FILE', 'services_config.yaml')

def load_services_config(config_file: str) -> List[Dict[str, str]]:
    """
    Load services configuration from YAML file.
    
    Expected format:
    services:
      - name: service-name
        repo_path: repo-path
        version_file: version.env
        version_variable: APP_VERSION
    
    Returns:
        List of service dictionaries
    """
    config_path = Path(__file__).parent / config_file
    
    if not config_path.exists():
        raise FileNotFoundError(f"Services config file not found: {config_path}")
    
    try:
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f)
        
        if not data or 'services' not in data:
            raise ValueError(f"Invalid services config format in {config_file}")
        
        services = data['services']
        
        # Validate required fields
        for service in services:
            required_fields = ['name', 'repo_path', 'version_file', 'version_variable']
            for field in required_fields:
                if field not in service:
                    raise ValueError(f"Service {service.get('name', 'unknown')} missing required field: {field}")
        
        print(f"Loaded {len(services)} services from {config_file}")
        return services
        
    except yaml.YAMLError as e:
        raise ValueError(f"Error parsing YAML file {config_file}: {e}")

MICROSERVICES = load_services_config(SERVICES_CONFIG_FILE)

# Output Configuration
OUTPUT_FILE = os.environ.get('OUTPUT_FILE', 'services.yaml')
KEEP_HISTORY = os.environ.get('KEEP_HISTORY', 'True').lower() in ('true', '1', 'yes')
HISTORY_FILE = os.environ.get('HISTORY_FILE', 'services_history.yaml')

# Logging Configuration
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

# Configuration summary
CONFIG = {
    'environment': ENVIRONMENT,
    'bitbucket_base_url': BITBUCKET_BASE_URL,
    'source_branch': SOURCE_BRANCH,
    'microservices_count': len(MICROSERVICES),
    'output_file': OUTPUT_FILE,
    'keep_history': KEEP_HISTORY,
    'log_level': LOG_LEVEL,
}
