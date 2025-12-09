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
        
        controls_list = []
        self._controls_map = {} # Initialize map for deduplication
        firewall_rules_list = []
        iam_roles_list = []
        
        # 1. Fetch Security Controls from CAI (Org Policies, VPC-SC, Network, IAM)
        logger.info("Fetching Security Controls from CAI...")
        try:
            async for asset in self.cai_client.search_security_controls():
                asset_type = asset['asset_type']
                asset_name = asset.get('name', '')
                display_name = asset.get('display_name', 'Unknown')
                
                # Determine enforcement level based on asset name prefix
                enforcement_level = "resource" # Default
                project_id = None
                
                if asset_name.startswith("//cloudresourcemanager.googleapis.com/organizations/") or "/organizations/" in asset_name:
                    enforcement_level = "org"
                elif asset_name.startswith("//cloudresourcemanager.googleapis.com/folders/") or "/folders/" in asset_name:
                    enforcement_level = "folder"
                elif asset_name.startswith("//cloudresourcemanager.googleapis.com/projects/") or "/projects/" in asset_name:
                    enforcement_level = "project"
                    # Extract project ID
                    try:
                        parts = asset_name.split('/')
                        if "projects" in parts:
                            proj_idx = parts.index("projects")
                            if proj_idx + 1 < len(parts):
                                project_id = parts[proj_idx + 1]
                    except Exception:
                        pass
                
                # Determine category, service, and collection
                category = "preventive" # Default for CAI
                service = "Unknown"
                target_list = controls_list # Default collection
                is_firewall_or_iam = False
                
                canonical_id = asset_name.replace('/', '_')
                
                if asset_type == "orgpolicy.googleapis.com/Policy":
                    service = "Organization Policy"
                    # Extract constraint name for canonical ID
                    # Name format: .../policies/{constraint_name}
                    constraint_name = asset_name.split('/')[-1]
                    canonical_id = f"org_policy_{constraint_name}"
                    description = f"Organization Policy: {display_name}"
                    
                elif asset_type == "identity.accesscontextmanager.googleapis.com/AccessLevel":
                    service = "VPC Service Controls"
                    description = f"Access Level: {display_name}"
                    
                    # Determine scope based on project/folders fields
                    if asset.get('project'):
                        enforcement_level = "project"
                        project_id = asset.get('project')
                    elif asset.get('folders'):
                        enforcement_level = "folder"
                    else:
                        enforcement_level = "org"
                        
                elif asset_type == "identity.accesscontextmanager.googleapis.com/ServicePerimeter":
                    service = "VPC Service Controls"
                    description = f"Service Perimeter: {display_name}"
                    
                    # Determine scope based on project/folders fields
                    if asset.get('project'):
                        enforcement_level = "project"
                        project_id = asset.get('project')
                    elif asset.get('folders'):
                        enforcement_level = "folder"
                    else:
                        enforcement_level = "org"
                elif asset_type == "compute.googleapis.com/Firewall":
                    service = "VPC Firewall"
                    description = f"Firewall Rule: {display_name}"
                    target_list = firewall_rules_list
                    is_firewall_or_iam = True
                elif asset_type == "compute.googleapis.com/SecurityPolicy":
                    service = "Cloud Armor"
                    description = f"Cloud Armor Policy: {display_name}"
                elif asset_type == "iam.googleapis.com/Role":
                    service = "IAM"
                    description = f"IAM Role: {display_name}"
                    target_list = iam_roles_list
                    is_firewall_or_iam = True
                else:
                    description = f"Security Control: {display_name}"

                # For Firewall and IAM, we keep existing behavior (list)
                if is_firewall_or_iam:
                    control = {
                        "control_id": asset_name.replace('/', '_'),
                        "name": display_name,
                        "description": description,
                        "category": category,
                        "enforcement_level": enforcement_level,
                        "service": service,
                        "compliance_frameworks": [], # Placeholder
                        "created_at": "2025-12-04T12:00:00Z", # Should use actual timestamp in prod
                        "source_data": asset
                    }
                    target_list.append(control)
                else:
                    # For Controls (Org Policies, VPC-SC), we deduplicate
                    # Check if control already exists in our map (we'll use a map instead of list for these)
                    if not hasattr(self, '_controls_map'):
                        self._controls_map = {}
                    
                    if canonical_id in self._controls_map:
                        # Update existing control
                        existing_control = self._controls_map[canonical_id]
                        if project_id and project_id not in existing_control.get('project_ids', []):
                            existing_control['project_ids'].append(project_id)
                    else:
                        # Create new control
                        control = {
                            "control_id": canonical_id,
                            "name": display_name,
                            "description": description,
                            "category": category,
                            "enforcement_level": enforcement_level,
                            "service": service,
                            "compliance_frameworks": [], # Placeholder
                            "created_at": "2025-12-04T12:00:00Z", # Should use actual timestamp in prod
                            "source_data": asset,
                            "project_ids": [project_id] if project_id else []
                        }
                        self._controls_map[canonical_id] = control
                    
        except Exception as e:
            logger.error(f"Failed to fetch Security Controls from CAI: {e}")

        # Populate controls_list from map
        if hasattr(self, '_controls_map'):
            controls_list.extend(self._controls_map.values())

        # 2. Fetch Effective SHA Custom Modules from SCC (Detective)
        logger.info("Fetching Effective SHA Custom Modules from SCC...")
        try:
            async for module in self.scc_client.list_effective_sha_custom_modules():
                # Determine enforcement level (usually org/folder for modules, but check parent)
                # module['name'] format: organizations/123/securityHealthAnalyticsSettings/customModules/456
                enforcement_level = "org"
                if "folders/" in module['name']:
                    enforcement_level = "folder"
                elif "projects/" in module['name']:
                    enforcement_level = "project"

                control = {
                    "control_id": module['name'].replace('/', '_'),
                    "name": module['display_name'],
                    "description": f"SHA Custom Module: {module['display_name']}",
                    "category": "detective",
                    "enforcement_level": enforcement_level,
                    "service": "Security Command Center",
                    "compliance_frameworks": [],
                    "created_at": "2025-12-04T12:00:00Z",
                    "source_data": module
                }
                controls_list.append(control)
        except Exception as e:
            logger.error(f"Failed to fetch SHA Custom Modules: {e}")
        
        # 3. Add Built-in SHA Detectors (Static) - Detective
        logger.info("Adding built-in Security Health Analytics detectors (Static Definitions)...")
        for detector in SHA_DETECTORS:
             # SHA Detectors are generic definitions, usually Org level applicability
            control = {
                "control_id": detector['id'],
                "name": detector['title'],
                "description": detector['description'],
                "category": "detective",
                "enforcement_level": "org", # Generic definition
                "service": "Security Command Center",
                "compliance_frameworks": [],
                "created_at": "2025-12-04T12:00:00Z",
                "source_data": detector
            }
            controls_list.append(control)
        
        logger.info(f"Total Controls: {len(controls_list)}")
        logger.info(f"Total Firewall Rules: {len(firewall_rules_list)}")
        logger.info(f"Total IAM Roles: {len(iam_roles_list)}")
        
        # Upsert Controls
        upserted_controls = await self.datastore.upsert_controls(
            controls_list, 
            self.datastore.controls_collection
        )
        
        # Upsert Firewall Rules
        upserted_fw = await self.datastore.upsert_controls(
            firewall_rules_list, 
            self.datastore.firewall_rules_collection
        )
        
        # Upsert IAM Roles
        upserted_iam = await self.datastore.upsert_controls(
            iam_roles_list, 
            self.datastore.iam_roles_collection
        )
        
        return {
            "total_loaded": len(controls_list) + len(firewall_rules_list) + len(iam_roles_list),
            "total_upserted": upserted_controls + upserted_fw + upserted_iam,
            "controls_upserted": upserted_controls,
            "firewall_rules_upserted": upserted_fw,
            "iam_roles_upserted": upserted_iam
        }
