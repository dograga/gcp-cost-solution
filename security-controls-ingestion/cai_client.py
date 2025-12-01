"""Client for Cloud Asset Inventory"""

import logging
from typing import List, Dict, Any, AsyncIterator
from google.cloud import asset_v1
import config

logger = logging.getLogger(__name__)

class CAIClient:
    """Client for interacting with Cloud Asset Inventory"""
    
    def __init__(self):
        self.client = asset_v1.AssetServiceClient()
        self.scope = f"organizations/{config.GCP_ORGANIZATION_ID}"
        logger.info(f"Initialized CAI client for scope: {self.scope}")
    
    async def search_organization_policies(self) -> AsyncIterator[Dict[str, Any]]:
        """
        Search for Organization Policies across the entire hierarchy.
        
        Yields:
            Dictionary containing policy data
        """
        # Asset type for Organization Policies
        asset_types = ["cloudresourcemanager.googleapis.com/OrganizationPolicy"]
        
        # Search all resources in the scope
        request = asset_v1.SearchAllResourcesRequest(
            scope=self.scope,
            asset_types=asset_types,
            page_size=500
        )
        
        logger.info(f"Searching for assets of type: {asset_types}")
        
        try:
            # CAI client is synchronous, but we can wrap it or just use it directly
            # For simplicity in this async context, we'll iterate the pages
            # Note: In a true async app, we might want to run this in an executor
            
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
                    # Additional metadata might be in resource.additional_attributes
                    # But for Org Policies, the core config is often in the 'resource' itself
                    # However, search_all_resources returns metadata, not the full content.
                    # To get the content, we might need to read the asset or rely on what's indexed.
                    # For Org Policies, the 'state' (enforced/not) is key.
                }
                
                yield policy_data
                
            logger.info(f"Found {count} Organization Policies")
            
        except Exception as e:
            logger.error(f"Error searching CAI: {e}")
            raise
