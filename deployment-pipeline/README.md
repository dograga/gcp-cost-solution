# Deployment Pipeline - Version Scanner

Automated tool to scan Bitbucket repositories for microservice versions and generate deployment manifests with change tracking.

## Overview

This tool:
1. Scans configured Bitbucket repositories for version files
2. Fetches version values from specified branch (e.g., UAT)
3. Compares with existing versions to detect changes
4. Generates `services.yaml` with version and change status
5. Maintains version history for audit trail

## Features

- **Multi-Service Support**: Scan 10+ microservices in one run
- **Change Detection**: Automatically detects version changes
- **History Tracking**: Maintains version history (last 50 deployments)
- **Flexible Configuration**: Define services via environment variables
- **Bitbucket Integration**: Fetches files directly from Bitbucket API
- **YAML Output**: Generates deployment-ready YAML manifest

## Configuration

### Environment Variables (.env.dev)

```bash
# Bitbucket Configuration
BITBUCKET_BASE_URL=https://bitbucket.org/your-org
BITBUCKET_USERNAME=your-username
BITBUCKET_APP_PASSWORD=your-app-password
SOURCE_BRANCH=uat

# Services Configuration
# Path to YAML file containing services list
SERVICES_CONFIG_FILE=services_config.yaml

# Output Configuration
OUTPUT_FILE=services.yaml
KEEP_HISTORY=True
HISTORY_FILE=services_history.yaml

# Logging
LOG_LEVEL=INFO
```

### Services Configuration File (services_config.yaml)

Define all microservices in a separate YAML file for easier management:

```yaml
services:
  # Authentication & Authorization
  - name: auth-service
    repo_path: auth-api
    version_file: version.env
    version_variable: APP_VERSION
    
  - name: user-service
    repo_path: user-api
    version_file: version.env
    version_variable: APP_VERSION
    
  # Payment Services
  - name: payment-service
    repo_path: payment-api
    version_file: .env
    version_variable: VERSION
    
  # ... add more services (supports 30+ easily)
```

**Field Descriptions:**
- `name` - Service name (used in output)
- `repo_path` - Bitbucket repository path
- `version_file` - Path to version file within the repo (e.g., `version.env`, `.env`, `version.txt`)
- `version_variable` - Variable name to extract from file (e.g., `APP_VERSION`, `VERSION`)

**Supported File Formats:**

1. **ENV file with variable:**
   ```bash
   # version.env
   APP_VERSION=v1.2.5
   BUILD_NUMBER=123
   ```
   Config: `version_variable: APP_VERSION` → extracts `v1.2.5`

2. **Plain text file:**
   ```
   # version.txt
   v1.2.5
   ```
   Config: `version_variable: VERSION` → extracts `v1.2.5` (fallback)

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Run the Scanner

```bash
# Development environment
python main.py

# Production environment
ENVIRONMENT=prd python main.py
```

### Output Files

**services.yaml** - Main deployment manifest:
```yaml
metadata:
  generated_at: '2025-10-29T13:20:00'
  source_branch: uat
  total_services: 10
  changed_services: 3
services:
  - name: auth-service
    version: v1.2.5
    changed: true
    repo_path: auth-api
    version_file: version.env
    version_variable: APP_VERSION
  - name: user-service
    version: v2.1.0
    changed: false
    repo_path: user-api
    version_file: version.env
    version_variable: APP_VERSION
  - name: payment-service
    version: v3.0.1
    changed: true
    repo_path: payment-api
    version_file: .env
    version_variable: VERSION
```

**services_history.yaml** - Version history (last 50 runs):
```yaml
history:
  - metadata:
      generated_at: '2025-10-29T12:00:00'
      changed_services: 2
    services:
      - name: auth-service
        version: v1.2.4
        changed: true
  - metadata:
      generated_at: '2025-10-29T13:20:00'
      changed_services: 3
    services:
      - name: auth-service
        version: v1.2.5
        changed: true
```

## How It Works

### 1. Load Current Versions

If `services.yaml` exists, loads current versions:
```python
{
  'auth-service': 'v1.2.4',
  'user-service': 'v2.1.0'
}
```

### 2. Fetch New Versions

For each service, fetches version file from Bitbucket:
```
GET https://bitbucket.org/your-org/auth-api/raw/uat/version.txt
→ v1.2.5
```

### 3. Compare Versions

```python
current: v1.2.4
new:     v1.2.5
→ changed: True
```

### 4. Generate Output

Creates `services.yaml` with:
- Service name
- New version
- Changed flag (True/False)
- Repository metadata

### 5. Update History

Appends to `services_history.yaml` for audit trail

## Bitbucket Authentication

### Create App Password

1. Go to Bitbucket → Personal Settings → App passwords
2. Create new app password with permissions:
   - **Repositories**: Read
3. Copy the generated password
4. Set in `.env` file:
   ```bash
   BITBUCKET_USERNAME=your-username
   BITBUCKET_APP_PASSWORD=generated-app-password
   ```

### URL Format

**Bitbucket Cloud:**
```
BITBUCKET_BASE_URL=https://bitbucket.org/your-workspace
```

**Bitbucket Server:**
```
BITBUCKET_BASE_URL=https://bitbucket.company.com/projects/YOUR_PROJECT
```

## Integration with Deployment Pipeline

### Use in CI/CD

```bash
# 1. Run version scanner
python main.py

# 2. Check if any services changed
CHANGED=$(yq eval '.metadata.changed_services' services.yaml)

if [ "$CHANGED" -gt 0 ]; then
  echo "Deploying $CHANGED services..."
  
  # 3. Deploy only changed services
  yq eval '.services[] | select(.changed == true) | .name' services.yaml | while read service; do
    echo "Deploying $service..."
    # Your deployment command here
  done
else
  echo "No changes detected, skipping deployment"
fi
```

### Example: Deploy with Helm

```bash
# Deploy changed services
yq eval '.services[] | select(.changed == true)' services.yaml -o json | jq -c '.' | while read service; do
  NAME=$(echo $service | jq -r '.name')
  VERSION=$(echo $service | jq -r '.version')
  
  helm upgrade --install $NAME ./charts/$NAME \
    --set image.tag=$VERSION \
    --namespace production
done
```

## Example Workflow

### Initial Run (No existing services.yaml)

```
2025-10-29 13:20:00 - INFO - Starting Deployment Pipeline
2025-10-29 13:20:00 - INFO - No existing services.yaml found, starting fresh
2025-10-29 13:20:01 - INFO - auth-service: New service (version: v1.2.5)
2025-10-29 13:20:02 - INFO - user-service: New service (version: v2.1.0)
2025-10-29 13:20:03 - INFO - payment-service: New service (version: v3.0.1)
2025-10-29 13:20:04 - INFO - Total Services: 3
2025-10-29 13:20:04 - INFO - Changed: 3
2025-10-29 13:20:04 - INFO - Saved services configuration to services.yaml
```

### Subsequent Run (With changes)

```
2025-10-29 14:00:00 - INFO - Starting Deployment Pipeline
2025-10-29 14:00:00 - INFO - Loaded 3 existing service versions
2025-10-29 14:00:01 - INFO - auth-service: Version changed v1.2.5 → v1.2.6
2025-10-29 14:00:02 - INFO - user-service: Version unchanged (v2.1.0)
2025-10-29 14:00:03 - INFO - payment-service: Version unchanged (v3.0.1)
2025-10-29 14:00:04 - INFO - Total Services: 3
2025-10-29 14:00:04 - INFO - Changed: 1
2025-10-29 14:00:04 - INFO - Changed Services:
2025-10-29 14:00:04 - INFO -   - auth-service: v1.2.6
```

## Error Handling

### File Not Found

If version file doesn't exist in repository:
```
WARNING - File not found: auth-api/version.txt on branch uat
WARNING - Could not fetch version for auth-service, using 'unknown'
```

Service will be marked with `version: unknown`

### Authentication Failed

```
ERROR - Request failed for auth-api/version.txt: 401 Unauthorized
```

Check Bitbucket credentials in `.env` file

### Network Issues

```
ERROR - Request failed for auth-api/version.txt: Connection timeout
```

Retries are not automatic - rerun the script

## Best Practices

1. **Version File Format**: Use semantic versioning (v1.2.3)
2. **Consistent Naming**: Keep version files in same location across repos
3. **Branch Strategy**: Use dedicated branch (e.g., `uat`) for version tracking
4. **History Retention**: Keep last 50 deployments for audit
5. **CI/CD Integration**: Run before each deployment
6. **Review Changes**: Always review changed services before deploying

## Troubleshooting

### No Services Detected

Check `MICROSERVICES` format in `.env`:
```bash
# Correct
MICROSERVICES=auth-service:auth-api:version.txt,user-service:user-api:version.txt

# Wrong (missing colons)
MICROSERVICES=auth-service,user-service
```

### All Services Show as Changed

Delete `services.yaml` to reset:
```bash
rm services.yaml
python main.py
```

### Bitbucket API Rate Limiting

Add delays between requests or use service account with higher limits

## Advanced Configuration

### Custom Version File Paths

Different paths per service:
```bash
MICROSERVICES=auth-service:auth-api:version.txt,user-service:user-api:config/VERSION,payment-service:payment-api:.version
```

### Multiple Branches

Run for different branches:
```bash
# UAT
SOURCE_BRANCH=uat OUTPUT_FILE=services_uat.yaml python main.py

# Production
SOURCE_BRANCH=main OUTPUT_FILE=services_prd.yaml python main.py
```

### Disable History

```bash
KEEP_HISTORY=False python main.py
```

## Future Enhancements

- [ ] Add support for GitHub/GitLab
- [ ] Parallel repository scanning
- [ ] Slack/Teams notifications for changes
- [ ] Automatic PR creation for version updates
- [ ] Rollback capability using history
- [ ] Version validation (semantic versioning check)
- [ ] Diff view between versions
