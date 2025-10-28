#!/bin/bash
# Setup script for GCP Cost Anomaly Pub/Sub Topic
# This creates a Pub/Sub topic where GCP cost anomalies will be published

set -e

# Load environment variables
if [ -f .env.${ENVIRONMENT:-dev} ]; then
    export $(cat .env.${ENVIRONMENT:-dev} | grep -v '^#' | xargs)
fi

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}GCP Cost Anomaly Topic Setup${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Validate required variables
if [ -z "$GCP_PROJECT_ID" ]; then
    echo "Error: GCP_PROJECT_ID not set"
    exit 1
fi

if [ -z "$ANOMALY_TOPIC" ]; then
    echo "Error: ANOMALY_TOPIC not set"
    exit 1
fi

echo -e "${YELLOW}Project:${NC} $GCP_PROJECT_ID"
echo -e "${YELLOW}Topic:${NC} $ANOMALY_TOPIC"
echo ""

# Set the project
echo -e "${BLUE}Setting GCP project...${NC}"
gcloud config set project $GCP_PROJECT_ID

# Enable required APIs
echo -e "${BLUE}Enabling required APIs...${NC}"
gcloud services enable pubsub.googleapis.com
gcloud services enable cloudbilling.googleapis.com

# Create Pub/Sub topic
echo -e "${BLUE}Creating Pub/Sub topic...${NC}"
if gcloud pubsub topics describe $ANOMALY_TOPIC &>/dev/null; then
    echo -e "${YELLOW}Topic $ANOMALY_TOPIC already exists${NC}"
else
    gcloud pubsub topics create $ANOMALY_TOPIC
    echo -e "${GREEN}✓ Created topic: $ANOMALY_TOPIC${NC}"
fi

# Create dead-letter topic (optional, for failed messages)
DEAD_LETTER_TOPIC="${ANOMALY_TOPIC}-dead-letter"
echo -e "${BLUE}Creating dead-letter topic...${NC}"
if gcloud pubsub topics describe $DEAD_LETTER_TOPIC &>/dev/null; then
    echo -e "${YELLOW}Dead-letter topic $DEAD_LETTER_TOPIC already exists${NC}"
else
    gcloud pubsub topics create $DEAD_LETTER_TOPIC
    echo -e "${GREEN}✓ Created dead-letter topic: $DEAD_LETTER_TOPIC${NC}"
fi

# Set topic labels
echo -e "${BLUE}Setting topic labels...${NC}"
gcloud pubsub topics update $ANOMALY_TOPIC \
    --update-labels=purpose=cost-anomalies,environment=${ENVIRONMENT:-dev}

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Configure GCP Cost Anomaly Detection to publish to: $ANOMALY_TOPIC"
echo "2. Create a Pub/Sub subscription to process anomaly messages"
echo "3. Set up Cloud Function or Cloud Run to write anomalies to Firestore"
echo ""
echo -e "${YELLOW}Example subscription creation:${NC}"
echo "gcloud pubsub subscriptions create ${ANOMALY_TOPIC}-subscription \\"
echo "    --topic=$ANOMALY_TOPIC \\"
echo "    --ack-deadline=60 \\"
echo "    --message-retention-duration=7d \\"
echo "    --dead-letter-topic=$DEAD_LETTER_TOPIC \\"
echo "    --max-delivery-attempts=5"
echo ""
echo -e "${YELLOW}Topic ARN:${NC} projects/$GCP_PROJECT_ID/topics/$ANOMALY_TOPIC"
