import asyncio
from typing import List, Dict, Any

# Mock data simulating CAI output
MOCK_ASSETS = [
    {
        "asset_type": "orgpolicy.googleapis.com/Policy",
        "name": "//cloudresourcemanager.googleapis.com/projects/project-a/policies/compute.disableSerialPortAccess",
        "display_name": "compute.disableSerialPortAccess",
    },
    {
        "asset_type": "orgpolicy.googleapis.com/Policy",
        "name": "//cloudresourcemanager.googleapis.com/projects/project-b/policies/compute.disableSerialPortAccess",
        "display_name": "compute.disableSerialPortAccess",
    },
    {
        "asset_type": "orgpolicy.googleapis.com/Policy",
        "name": "//cloudresourcemanager.googleapis.com/projects/project-a/policies/iam.disableServiceAccountKeyCreation",
        "display_name": "iam.disableServiceAccountKeyCreation",
    }
]

async def process_assets(assets):
    controls_map = {}
    
    for asset in assets:
        asset_type = asset['asset_type']
        asset_name = asset.get('name', '')
        display_name = asset.get('display_name', 'Unknown')
        
        # Logic to be implemented in ingestion_service.py
        # We want to extract a canonical ID and project ID
        
        project_id = None
        canonical_id = asset_name # Default to full name (current behavior)
        
        if "/projects/" in asset_name:
            parts = asset_name.split('/')
            try:
                proj_idx = parts.index("projects")
                project_id = parts[proj_idx + 1]
            except ValueError:
                pass

        # PROPOSED LOGIC (Simulated)
        if asset_type == "orgpolicy.googleapis.com/Policy":
            # Extract constraint name
            constraint = asset_name.split('/')[-1]
            canonical_id = f"org_policy_{constraint}"
        else:
            canonical_id = asset_name.replace('/', '_')
            
        # Deduplication
        if canonical_id in controls_map:
            control = controls_map[canonical_id]
            if project_id and project_id not in control['project_ids']:
                control['project_ids'].append(project_id)
        else:
            control = {
                "control_id": canonical_id,
                "name": display_name,
                "project_ids": [project_id] if project_id else []
            }
            controls_map[canonical_id] = control
            
    return list(controls_map.values())

async def main():
    print("Processing assets...")
    results = await process_assets(MOCK_ASSETS)
    
    print(f"\nTotal Controls: {len(results)}")
    for control in results:
        print(f"Control ID: {control['control_id']}")
        print(f"Project IDs: {control['project_ids']}")
        print("-" * 20)

if __name__ == "__main__":
    asyncio.run(main())
