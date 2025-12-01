"""Service for ingesting security controls"""

import logging
from typing import Dict, Any
from firestore_datastore import Datastore
from cai_client import CAIClient

logger = logging.getLogger(__name__)

class IngestionService:
    """Service to ingest security controls from CAI"""
    
    def __init__(self, datastore: Datastore, cai_client: CAIClient):
        self.datastore = datastore
        self.cai_client = cai_client
    
    async def ingest_controls(self) -> Dict[str, Any]:
        """
        Ingest security controls (Org Policies) from CAI.
        """
        logger.info("Starting security controls ingestion from CAI...")
        
        controls = []
        async for policy in self.cai_client.search_organization_policies():
            # Transform to Firestore schema
            # Use the resource name as the ID (hashed or cleaned)
            # For now, we'll just use the name as is, or a derived ID
            
            control = {
                "id": policy['name'].replace('/', '_'), # Simple ID generation
                "title": policy['display_name'],
                "description": f"Organization Policy: {policy['display_name']}",
                "category": "Organization Policy",
                "severity": "HIGH", # Default for Org Policies
                "remediation": "Review Organization Policy configuration",
                "source_data": policy,
                "type": "organization_policy"
            }
            controls.append(control)
        
        logger.info(f"Fetched {len(controls)} policies from CAI")
        
        upserted_count = await self.datastore.upsert_controls(controls)
        
        return {
            "total_loaded": len(controls),
            "total_upserted": upserted_count
        }
