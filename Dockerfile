# Common Dockerfile for all cron jobs
# Build with: docker build --build-arg JOB_NAME=<job-name> -t <image-name> .
# Example: docker build --build-arg JOB_NAME=cost-cron -t cost-cron:latest .

FROM python:3.11-slim

# Build argument to specify which job to build
ARG JOB_NAME
ENV JOB_NAME=${JOB_NAME}

# Set working directory
WORKDIR /app

# Copy requirements from the specific job directory
COPY ${JOB_NAME}/requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code from the specific job directory
COPY ${JOB_NAME}/main.py .
COPY ${JOB_NAME}/config.py .

# Copy environment configuration files
COPY ${JOB_NAME}/.env.* ./

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run the application
CMD ["python", "main.py"]
