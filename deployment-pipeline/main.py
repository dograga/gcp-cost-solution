#!/usr/bin/env python3
"""
Deployment Pipeline - Version Scanner
Scans Bitbucket repositories for microservice versions and generates deployment manifest.
"""

import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth
import yaml

# Import configuration
import config

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BitbucketClient:
    """Client for interacting with Bitbucket API."""
    
    def __init__(self, base_url: str, username: str, app_password: str):
        """
        Initialize Bitbucket client.
        
        Args:
            base_url: Bitbucket base URL (e.g., https://bitbucket.org/your-org)
            username: Bitbucket username
            app_password: Bitbucket app password
        """
        self.base_url = base_url.rstrip('/')
        self.auth = HTTPBasicAuth(username, app_password) if username and app_password else None
        self.session = requests.Session()
        if self.auth:
            self.session.auth = self.auth
        
        logger.info(f"Initialized Bitbucket client for: {self.base_url}")
    
    def fetch_file_content(
        self, 
        repo_path: str, 
        file_path: str, 
        branch: str = 'main'
    ) -> Optional[str]:
        """
        Fetch file content from Bitbucket repository.
        
        Args:
            repo_path: Repository path (e.g., 'auth-api')
            file_path: File path within repo (e.g., 'version.env')
            branch: Branch name (default: 'main')
            
        Returns:
            File content as string, or None if not found
        """
        # Bitbucket API URL format: /repos/{workspace}/{repo_slug}/src/{branch}/{path}
        url = f"{self.base_url}/{repo_path}/raw/{branch}/{file_path}"
        
        try:
            logger.info(f"[AUDIT] Fetching file from Bitbucket")
            logger.info(f"[AUDIT]   URL: {url}")
            logger.info(f"[AUDIT]   Repository: {repo_path}")
            logger.info(f"[AUDIT]   File: {file_path}")
            logger.info(f"[AUDIT]   Branch: {branch}")
            
            response = self.session.get(url, timeout=10)
            
            logger.info(f"[AUDIT] Response: HTTP {response.status_code}")
            
            if response.status_code == 200:
                content = response.text
                content_length = len(content)
                logger.info(f"[AUDIT] Successfully fetched file ({content_length} bytes)")
                logger.debug(f"File content preview: {content[:100]}...")
                return content
            elif response.status_code == 404:
                logger.error(f"[AUDIT] File not found: {repo_path}/{file_path} on branch {branch}")
                logger.error(f"[AUDIT] URL attempted: {url}")
                return None
            elif response.status_code == 401:
                logger.error(f"[AUDIT] Authentication failed (HTTP 401)")
                logger.error(f"[AUDIT] Check BITBUCKET_USERNAME and BITBUCKET_APP_PASSWORD")
                return None
            elif response.status_code == 403:
                logger.error(f"[AUDIT] Access forbidden (HTTP 403)")
                logger.error(f"[AUDIT] Check repository permissions for user")
                return None
            else:
                logger.error(f"[AUDIT] Unexpected error: HTTP {response.status_code}")
                logger.error(f"[AUDIT] Response body: {response.text[:200]}")
                return None
                
        except requests.exceptions.Timeout:
            logger.error(f"[AUDIT] Request timeout after 10s")
            logger.error(f"[AUDIT] URL: {url}")
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error(f"[AUDIT] Connection error: {e}")
            logger.error(f"[AUDIT] URL: {url}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"[AUDIT] Request failed: {e}")
            logger.error(f"[AUDIT] URL: {url}")
            return None
    
    def parse_version_from_file(self, file_content: str, variable_name: str) -> Optional[str]:
        """
        Parse version value from file content by variable name.
        
        Supports formats:
        - ENV files: APP_VERSION=v1.2.3
        - Plain text: v1.2.3 (if no variable name match)
        
        Args:
            file_content: Content of the version file
            variable_name: Variable name to search for (e.g., 'APP_VERSION')
            
        Returns:
            Version string or None if not found
        """
        if not file_content:
            return None
        
        # Try to find variable assignment (e.g., APP_VERSION=v1.2.3)
        for line in file_content.split('\n'):
            line = line.strip()
            
            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue
            
            # Check for variable assignment
            if '=' in line:
                parts = line.split('=', 1)
                var_name = parts[0].strip()
                var_value = parts[1].strip().strip('"').strip("'")
                
                if var_name == variable_name:
                    logger.debug(f"Found {variable_name}={var_value}")
                    return var_value
        
        # Fallback: if file is single line without '=', return as-is
        lines = [l.strip() for l in file_content.split('\n') if l.strip() and not l.strip().startswith('#')]
        if len(lines) == 1 and '=' not in lines[0]:
            logger.debug(f"Using plain text version: {lines[0]}")
            return lines[0]
        
        logger.warning(f"Could not find variable '{variable_name}' in file content")
        return None


class VersionManager:
    """Manages microservice versions and change tracking."""
    
    def __init__(self, output_file: str, history_file: str, keep_history: bool = True):
        """
        Initialize version manager.
        
        Args:
            output_file: Path to output services.yaml file
            history_file: Path to history file
            keep_history: Whether to keep version history
        """
        self.output_file = Path(output_file)
        self.history_file = Path(history_file)
        self.keep_history = keep_history
        self.current_versions = self._load_current_versions()
        
        logger.info(f"Initialized VersionManager (output: {output_file})")
        if self.current_versions:
            logger.info(f"Loaded {len(self.current_versions)} existing service versions")
    
    def _load_current_versions(self) -> Dict[str, str]:
        """
        Load current versions from existing services.yaml file.
        
        Returns:
            Dictionary mapping service name to version
        """
        if not self.output_file.exists():
            logger.info(f"No existing {self.output_file} found, starting fresh")
            return {}
        
        try:
            with open(self.output_file, 'r') as f:
                data = yaml.safe_load(f)
            
            if not data or 'services' not in data:
                return {}
            
            versions = {}
            for service in data['services']:
                versions[service['name']] = service.get('version', '')
            
            return versions
            
        except Exception as e:
            logger.error(f"Error loading current versions: {e}")
            return {}
    
    def check_version_changed(self, service_name: str, new_version: str) -> bool:
        """
        Check if version has changed from current version.
        
        Args:
            service_name: Name of the service
            new_version: New version string
            
        Returns:
            True if version changed, False otherwise
        """
        current_version = self.current_versions.get(service_name)
        
        if current_version is None:
            # New service
            logger.info(f"{service_name}: New service (version: {new_version})")
            return True
        
        if current_version != new_version:
            logger.info(f"{service_name}: Version changed {current_version} → {new_version}")
            return True
        
        logger.debug(f"{service_name}: Version unchanged ({new_version})")
        return False
    
    def save_services_yaml(self, services: List[Dict[str, any]]):
        """
        Save services configuration to YAML file.
        
        Args:
            services: List of service dictionaries
        """
        output_data = {
            'metadata': {
                'generated_at': datetime.utcnow().isoformat(),
                'source_branch': config.SOURCE_BRANCH,
                'total_services': len(services),
                'changed_services': sum(1 for s in services if s.get('changed', False))
            },
            'services': services
        }
        
        try:
            # Save main output file
            with open(self.output_file, 'w') as f:
                yaml.dump(output_data, f, default_flow_style=False, sort_keys=False)
            
            logger.info(f"Saved services configuration to {self.output_file}")
            
            # Save history if enabled
            if self.keep_history:
                self._save_history(output_data)
                
        except Exception as e:
            logger.error(f"Error saving services.yaml: {e}")
            raise
    
    def _save_history(self, data: Dict):
        """
        Append current version to history file.
        
        Args:
            data: Services data to append to history
        """
        try:
            history = []
            
            # Load existing history
            if self.history_file.exists():
                with open(self.history_file, 'r') as f:
                    existing = yaml.safe_load(f)
                    if existing and 'history' in existing:
                        history = existing['history']
            
            # Append new entry
            history.append(data)
            
            # Keep only last 50 entries
            if len(history) > 50:
                history = history[-50:]
            
            # Save history
            with open(self.history_file, 'w') as f:
                yaml.dump({'history': history}, f, default_flow_style=False)
            
            logger.debug(f"Updated history file: {self.history_file}")
            
        except Exception as e:
            logger.error(f"Error saving history: {e}")


class DeploymentPipeline:
    """Main deployment pipeline orchestrator."""
    
    def __init__(self):
        """Initialize deployment pipeline."""
        self.bitbucket = BitbucketClient(
            base_url=config.BITBUCKET_BASE_URL,
            username=config.BITBUCKET_USERNAME,
            app_password=config.BITBUCKET_APP_PASSWORD
        )
        
        self.version_manager = VersionManager(
            output_file=config.OUTPUT_FILE,
            history_file=config.HISTORY_FILE,
            keep_history=config.KEEP_HISTORY
        )
        
        logger.info("Initialized DeploymentPipeline")
    
    def fetch_service_version(self, service: Dict[str, str]) -> Optional[str]:
        """
        Fetch version for a single service.
        
        Args:
            service: Service configuration dictionary
            
        Returns:
            Version string or None if not found
        """
        # Fetch file content
        file_content = self.bitbucket.fetch_file_content(
            repo_path=service['repo_path'],
            file_path=service['version_file'],
            branch=config.SOURCE_BRANCH
        )
        
        if not file_content:
            return None
        
        # Parse version from file content using variable name
        version = self.bitbucket.parse_version_from_file(
            file_content=file_content,
            variable_name=service['version_variable']
        )
        
        return version
    
    def scan_all_services(self) -> List[Dict[str, any]]:
        """
        Scan all configured microservices for versions.
        
        Returns:
            List of service dictionaries with version and changed status
        """
        logger.info(f"Scanning {len(config.MICROSERVICES)} microservices...")
        
        services = []
        
        for service_config in config.MICROSERVICES:
            service_name = service_config['name']
            logger.info(f"Processing: {service_name}")
            
            # Fetch version from Bitbucket
            version = self.fetch_service_version(service_config)
            
            if version is None:
                logger.warning(f"Could not fetch version for {service_name}, using 'unknown'")
                version = 'unknown'
            
            # Check if version changed
            changed = self.version_manager.check_version_changed(service_name, version)
            
            # Build service entry
            service_entry = {
                'name': service_name,
                'version': version,
                'changed': changed,
                'repo_path': service_config['repo_path'],
                'version_file': service_config['version_file'],
                'version_variable': service_config['version_variable']
            }
            
            services.append(service_entry)
        
        return services
    
    def run(self):
        """Main execution method."""
        logger.info("=" * 60)
        logger.info("Starting Deployment Pipeline - Version Scanner")
        logger.info("=" * 60)
        logger.info(f"Environment: {config.ENVIRONMENT}")
        logger.info(f"Source Branch: {config.SOURCE_BRANCH}")
        logger.info(f"Output File: {config.OUTPUT_FILE}")
        logger.info("=" * 60)
        
        try:
            # Scan all services
            services = self.scan_all_services()
            
            # Generate statistics
            total_services = len(services)
            changed_services = sum(1 for s in services if s['changed'])
            unchanged_services = total_services - changed_services
            
            logger.info("=" * 60)
            logger.info("Scan Complete")
            logger.info(f"Total Services: {total_services}")
            logger.info(f"Changed: {changed_services}")
            logger.info(f"Unchanged: {unchanged_services}")
            logger.info("=" * 60)
            
            # List changed services
            if changed_services > 0:
                logger.info("Changed Services:")
                for service in services:
                    if service['changed']:
                        logger.info(f"  - {service['name']}: {service['version']}")
            
            # Save to YAML
            self.version_manager.save_services_yaml(services)
            
            logger.info("=" * 60)
            logger.info("Pipeline Completed Successfully")
            logger.info("=" * 60)
            
            return 0
            
        except Exception as e:
            logger.error(f"Pipeline failed: {e}", exc_info=True)
            return 1


if __name__ == "__main__":
    pipeline = DeploymentPipeline()
    exit_code = pipeline.run()
    sys.exit(exit_code)
