"""Client for Cloud Asset Inventory"""

import logging
from typing import List, Dict, Any, AsyncIterator
from google.cloud import asset_v1
from config import get_settings

logger = logging.getLogger(__name__)

class CAIClient:
    """Client for interacting with Cloud Asset Inventory"""
    
    def __init__(self):
        self.settings = get_settings()
        self.client = asset_v1.AssetServiceClient()
        
        # Construct scope dynamically based on settings
        scope_type = self.settings.ingestion_scope_type.lower()
        scope_id = self.settings.ingestion_scope_id
        
        # Ensure scope type is pluralized correctly (organization -> organizations, folder -> folders)
        if not scope_type.endswith('s'):
            scope_type += 's'
            
        self.scope = f"{scope_type}/{scope_id}"
        logger.info(f"Initialized CAI client for scope: {self.scope}")
    
    async def search_security_controls(self) -> AsyncIterator[Dict[str, Any]]:
        """
        Search for security controls (Org Policies, VPC-SC, Network, IAM) across the hierarchy.
        
        Yields:
            Dictionary containing asset data
        """
        # Asset types for Security Controls
        asset_types = [
            "orgpolicy.googleapis.com/Policy",
            "accesscontextmanager.googleapis.com/AccessLevel",
            "accesscontextmanager.googleapis.com/ServicePerimeter",
            "compute.googleapis.com/Firewall",
            "compute.googleapis.com/SecurityPolicy", # Cloud Armor
            "iam.googleapis.com/Role"
        ]
        
        # Search all resources in the scope
        request = asset_v1.SearchAllResourcesRequest(
            scope=self.scope,
            asset_types=asset_types,
            page_size=500
        )
        
        logger.info(f"Searching for assets of type: {asset_types} in {self.scope}")
        
        try:
            # CAI client is synchronous, but we can wrap it or just use it directly
            # For simplicity in this async context, we'll iterate the pages
            
            response = self.client.search_all_resources(request=request)
            
            count = 0
            for resource in response:
                count += 1
                
                # Extract relevant data
                policy_data = {
                    "name": resource.name,
                    "asset_type": resource.asset_type,
                    "display_name": resource.display_name,
                    "project": resource.project,
                    "folders": list(resource.folders),
                    "organization": resource.organization,
                    "parent_full_resource_name": resource.parent_full_resource_name,
                    "parent_asset_type": resource.parent_asset_type,
                }
                
                yield policy_data
                
            logger.info(f"Found {count} Organization Policies")
            
        except Exception as e:
            logger.error(f"Error searching CAI: {e}")
            raise
