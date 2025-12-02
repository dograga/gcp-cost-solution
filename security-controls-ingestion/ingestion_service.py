"""Service for ingesting security controls"""

import logging
from typing import Dict, Any
from firestore_datastore import Datastore
from cai_client import CAIClient
from scc_management_client import SCCManagementClient
from sha_detectors import SHA_DETECTORS

logger = logging.getLogger(__name__)

class IngestionService:
    """Service to ingest security controls from CAI, SCC, and static definitions"""
    
    def __init__(self, datastore: Datastore, cai_client: CAIClient, scc_client: SCCManagementClient):
        self.datastore = datastore
        self.cai_client = cai_client
        self.scc_client = scc_client
    
    async def ingest_controls(self) -> Dict[str, Any]:
        """
        Ingest security controls (Org Policies + SHA Detectors).
        """
        logger.info("Starting security controls ingestion...")
        
        preventive_controls = []
        detective_controls = []
        
        # 1. Fetch Security Controls from CAI (Org Policies, VPC-SC, Network, IAM)
        logger.info("Fetching Security Controls from CAI...")
        try:
            async for asset in self.cai_client.search_security_controls():
                asset_type = asset['asset_type']
                
                # Determine category and type based on asset_type
                category = "Unknown"
                control_type = "unknown"
                description = f"Security Control: {asset['display_name']}"
                is_preventive = True # Default for CAI assets
                
                if asset_type == "orgpolicy.googleapis.com/Policy":
                    category = "Organization Policy"
                    control_type = "organization_policy"
                    description = f"Organization Policy: {asset['display_name']}"
                elif asset_type == "identity.accesscontextmanager.googleapis.com/AccessLevel":
                    category = "VPC Service Controls"
                    control_type = "access_level"
                    description = f"Access Level: {asset['display_name']}"
                elif asset_type == "identity.accesscontextmanager.googleapis.com/ServicePerimeter":
                    category = "VPC Service Controls"
                    control_type = "service_perimeter"
                    description = f"Service Perimeter: {asset['display_name']}"
                elif asset_type == "compute.googleapis.com/Firewall":
                    category = "Network Security"
                    control_type = "firewall_rule"
                    description = f"Firewall Rule: {asset['display_name']}"
                elif asset_type == "compute.googleapis.com/SecurityPolicy":
                    category = "Network Security"
                    control_type = "cloud_armor_policy"
                    description = f"Cloud Armor Policy: {asset['display_name']}"
                elif asset_type == "iam.googleapis.com/Role":
                    category = "Identity & Access"
                    control_type = "iam_role"
                    description = f"IAM Role: {asset['display_name']}"

                control = {
                    "id": asset['name'].replace('/', '_'),
                    "title": asset['display_name'],
                    "description": description,
                    "category": category,
                    "severity": "HIGH", 
                    "remediation": "Review control configuration",
                    "source_data": asset,
                    "type": control_type
                }
                
                if is_preventive:
                    preventive_controls.append(control)
                else:
                    detective_controls.append(control)
                    
        except Exception as e:
            logger.error(f"Failed to fetch Security Controls from CAI: {e}")

        # 2. Fetch Effective SHA Custom Modules from SCC (Detective)
        logger.info("Fetching Effective SHA Custom Modules from SCC...")
        try:
            async for module in self.scc_client.list_effective_sha_custom_modules():
                control = {
                    "id": module['name'].replace('/', '_'),
                    "title": module['display_name'],
                    "description": f"SHA Custom Module: {module['display_name']}",
                    "category": "Security Health Analytics",
                    "severity": module['custom_config'].get('severity', 'MEDIUM'),
                    "remediation": module['custom_config'].get('recommendation', 'Review custom module configuration'),
                    "source_data": module,
                    "type": "sha_custom_module"
                }
                detective_controls.append(control)
        except Exception as e:
            logger.error(f"Failed to fetch SHA Custom Modules: {e}")
        
        # 3. Add Built-in SHA Detectors (Static) - Detective
        logger.info("Adding built-in Security Health Analytics detectors (Static Definitions)...")
        detective_controls.extend(SHA_DETECTORS)
        
        logger.info(f"Total Preventive Controls: {len(preventive_controls)}")
        logger.info(f"Total Detective Controls: {len(detective_controls)}")
        
        # Upsert Preventive Controls
        upserted_preventive = await self.datastore.upsert_controls(
            preventive_controls, 
            self.datastore.preventive_collection
        )
        
        # Upsert Detective Controls
        upserted_detective = await self.datastore.upsert_controls(
            detective_controls, 
            self.datastore.detective_collection
        )
        
        return {
            "total_loaded": len(preventive_controls) + len(detective_controls),
            "total_upserted": upserted_preventive + upserted_detective,
            "preventive_upserted": upserted_preventive,
            "detective_upserted": upserted_detective
        }
