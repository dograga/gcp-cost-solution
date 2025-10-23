# Docker Build Instructions

This repository uses a common Dockerfile in the root directory to build all cron jobs. This approach reduces duplication and ensures consistency across all jobs.

## Common Dockerfile

The `Dockerfile` in the root directory accepts a `JOB_NAME` build argument to specify which cron job to build.

### Build Arguments

- `JOB_NAME`: The name of the cron job directory (e.g., `cost-cron`, `cost-recommendation`)

## Building Images

### Cost Cron Job

```bash
# Build the cost-cron image
docker build --build-arg JOB_NAME=cost-cron -t gcr.io/YOUR_PROJECT_ID/cost-cron:latest .

# Push to Google Container Registry
docker push gcr.io/YOUR_PROJECT_ID/cost-cron:latest
```

### Cost Recommendation Job

```bash
# Build the cost-recommendation image
docker build --build-arg JOB_NAME=cost-recommendation -t gcr.io/YOUR_PROJECT_ID/cost-recommendation:latest .

# Push to Google Container Registry
docker push gcr.io/YOUR_PROJECT_ID/cost-recommendation:latest
```

## Directory Structure

Each cron job directory must contain:
- `main.py` - Main application code
- `config.py` - Configuration module
- `requirements.txt` - Python dependencies
- `.env.*` - Environment-specific configuration files

## How It Works

The common Dockerfile:
1. Accepts the `JOB_NAME` build argument
2. Copies `requirements.txt` from the specified job directory
3. Installs dependencies
4. Copies `main.py` and `config.py` from the job directory
5. Copies all `.env.*` files for environment-specific configuration
6. Sets up the Python environment and runs `main.py`

## Benefits

- **Consistency**: All jobs use the same base image and build process
- **Maintainability**: Updates to the build process only need to be made in one place
- **Simplicity**: No need to maintain separate Dockerfiles for each job
- **Flexibility**: Each job can have its own dependencies and configuration

## Adding New Cron Jobs

To add a new cron job:

1. Create a new directory under the root (e.g., `new-job/`)
2. Add the required files:
   - `main.py`
   - `config.py`
   - `requirements.txt`
   - `.env.example`, `.env.dev`, `.env.uat`, `.env.prd`
3. Build using the common Dockerfile:
   ```bash
   docker build --build-arg JOB_NAME=new-job -t gcr.io/YOUR_PROJECT_ID/new-job:latest .
   ```

No need to create a separate Dockerfile!
