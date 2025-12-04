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
        
        org_preventive_controls = []
        project_preventive_controls = []
        org_detective_controls = []
        project_detective_controls = []
        firewall_controls = []
        
        # Aggregation dictionaries for project-level controls
        # Key: {control_type}_{display_name}
        # Value: Control dict
        aggregated_project_controls = {}
        
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
                is_firewall = False
                
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
                    is_firewall = True
                elif asset_type == "compute.googleapis.com/SecurityPolicy":
                    category = "Network Security"
                    control_type = "cloud_armor_policy"
                    description = f"Cloud Armor Policy: {asset['display_name']}"
                elif asset_type == "iam.googleapis.com/Role":
                    category = "Identity & Access"
                    control_type = "iam_role"
                    description = f"IAM Role: {asset['display_name']}"

                # Check if it's a project-level control
                project_id = asset.get('project')
                if project_id:
                     # Clean project ID (remove 'projects/' prefix if present)
                    project_id = project_id.replace('projects/', '')
                    
                    # Create a unique key for aggregation
                    # We group by control type and display name (assuming standard naming)
                    agg_key = f"{control_type}_{asset['display_name']}"
                    
                    if agg_key in aggregated_project_controls:
                        # Update existing entry
                        aggregated_project_controls[agg_key]['projects'].append(project_id)
                    else:
                        # Create new entry
                        control = {
                            "id": agg_key, # Use aggregation key as ID
                            "title": asset['display_name'],
                            "description": description,
                            "category": category,
                            "severity": "HIGH", 
                            "remediation": "Review control configuration",
                            "source_data": asset, # Store first occurrence as representative
                            "type": control_type,
                            "projects": [project_id],
                            "is_aggregated": True,
                            "is_firewall": is_firewall, # Helper flag for sorting later
                            "is_preventive": is_preventive # Helper flag
                        }
                        aggregated_project_controls[agg_key] = control
                else:
                    # Non-project level (Org/Folder), treat as individual
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
                    
                    if is_firewall:
                        firewall_controls.append(control)
                    elif is_preventive:
                        org_preventive_controls.append(control)
                    else:
                        org_detective_controls.append(control)
            
            # Process aggregated controls and add to respective lists
            for key, control in aggregated_project_controls.items():
                # Remove helper flags
                is_fw = control.pop('is_firewall')
                is_prev = control.pop('is_preventive')
                
                if is_fw:
                    firewall_controls.append(control)
                elif is_prev:
                    project_preventive_controls.append(control)
                else:
                    project_detective_controls.append(control)
                    
        except Exception as e:
            logger.error(f"Failed to fetch Security Controls from CAI: {e}")

        # 2. Fetch Effective SHA Custom Modules from SCC (Detective)
        # These are usually Org/Folder level definitions, but can be project level.
        # For simplicity, if it has a project parent, we could aggregate.
        # But list_effective... usually returns modules effective at the scope.
        # Let's assume they are Org Detective for now unless we parse parent.
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
                org_detective_controls.append(control)
        except Exception as e:
            logger.error(f"Failed to fetch SHA Custom Modules: {e}")
        
        # 3. Add Built-in SHA Detectors (Static) - Detective
        # These are generic definitions, so Org Detective fits best.
        logger.info("Adding built-in Security Health Analytics detectors (Static Definitions)...")
        org_detective_controls.extend(SHA_DETECTORS)
        
        logger.info(f"Total Org Preventive Controls: {len(org_preventive_controls)}")
        logger.info(f"Total Project Preventive Controls: {len(project_preventive_controls)}")
        logger.info(f"Total Org Detective Controls: {len(org_detective_controls)}")
        logger.info(f"Total Project Detective Controls: {len(project_detective_controls)}")
        logger.info(f"Total Firewall Controls: {len(firewall_controls)}")
        
        # Upsert Org Preventive
        upserted_org_prev = await self.datastore.upsert_controls(
            org_preventive_controls, 
            self.datastore.org_preventive_collection
        )
        
        # Upsert Project Preventive
        upserted_proj_prev = await self.datastore.upsert_controls(
            project_preventive_controls, 
            self.datastore.project_preventive_collection
        )
        
        # Upsert Org Detective
        upserted_org_det = await self.datastore.upsert_controls(
            org_detective_controls, 
            self.datastore.org_detective_collection
        )
        
        # Upsert Project Detective
        upserted_proj_det = await self.datastore.upsert_controls(
            project_detective_controls, 
            self.datastore.project_detective_collection
        )
        
        # Upsert Firewall Controls
        upserted_firewall = await self.datastore.upsert_controls(
            firewall_controls, 
            self.datastore.firewall_collection
        )
        
        return {
            "total_loaded": len(org_preventive_controls) + len(project_preventive_controls) + len(org_detective_controls) + len(project_detective_controls) + len(firewall_controls),
            "total_upserted": upserted_org_prev + upserted_proj_prev + upserted_org_det + upserted_proj_det + upserted_firewall,
            "org_preventive_upserted": upserted_org_prev,
            "project_preventive_upserted": upserted_proj_prev,
            "org_detective_upserted": upserted_org_det,
            "project_detective_upserted": upserted_proj_det,
            "firewall_upserted": upserted_firewall
        }
