# Project Inventory Setup

## Overview

The cost recommendation collector can now read project IDs from a Firestore inventory collection instead of querying the Resource Manager API. This is useful when:
- You have projects in complex folder structures
- You want to control which projects are scanned
- You have a centralized project inventory system

## Configuration

Add these settings to your `.env.dev` (or other environment file):

```bash
# Project Inventory Configuration
# Set to 'true' to read projects from inventory collection instead of API
USE_INVENTORY_COLLECTION=true

# Inventory database (optional - defaults to FIRESTORE_DATABASE if not specified)
INVENTORY_DATABASE=dashboard

# Collection name containing project documents
INVENTORY_COLLECTION=project_inventory

# Field name in inventory documents that contains the project ID
INVENTORY_PROJECT_ID_FIELD=project_id
```

**Note:** 
- `INVENTORY_DATABASE` is optional. If not specified, it defaults to the same database as `FIRESTORE_DATABASE`
- This allows you to have inventory in a different database within the same GCP project

## Inventory Collection Structure

Your inventory collection should contain documents with at least a project ID field. Example document structure:

```json
{
  "project_id": "my-project-123",
  "project_name": "My Project",
  "environment": "production",
  "team": "platform",
  // ... other fields are optional
}
```

The collector will:
1. Read all documents from the specified inventory collection
2. Extract the `project_id` field (or whatever field you specify in `INVENTORY_PROJECT_ID_FIELD`)
3. Use those project IDs to fetch recommendations

## How to Use

1. **Update your `.env.dev` file** with your inventory database and collection details
2. **Set `USE_INVENTORY_COLLECTION=true`**
3. **Run the collector** - it will automatically read from the inventory instead of the API

## Switching Back to API Mode

To switch back to using the Resource Manager API:

```bash
USE_INVENTORY_COLLECTION=false
```

Or simply remove/comment out the `USE_INVENTORY_COLLECTION` setting (defaults to false).

## Benefits

- ✅ **No API permissions needed** - doesn't require Resource Manager API access
- ✅ **Faster** - no API calls to list projects
- ✅ **Controlled** - only scan projects you explicitly add to inventory
- ✅ **Flexible** - can filter projects by adding/removing from inventory
- ✅ **Multi-threading** - still processes projects in parallel (3 threads by default)

## Example Workflow

1. Maintain a project inventory collection in Firestore
2. Add/remove projects from inventory as needed
3. Run the cost recommendation collector
4. It automatically picks up all projects from your inventory
