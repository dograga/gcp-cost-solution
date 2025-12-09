import os
import json
import time
import logging
from typing import Dict, Any
from google.cloud import pubsub_v1

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
PROJECT_ID = os.environ.get('GCP_PROJECT_ID')
TOPIC_ID = os.environ.get('TOPIC_ID', 'cost-anomalies')

if not PROJECT_ID:
    logger.error("GCP_PROJECT_ID environment variable is required.")
    exit(1)

def create_dummy_anomaly() -> Dict[str, Any]:
    """Creates a dummy cost anomaly payload resembling GCP format."""
    return {
        "anomalyId": f"anomaly-{int(time.time())}",
        "billingAccountId": "012345-6789AB-CDEF01",
        "creationTime": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        "cost": {
            "amount": 123.45,
            "currencyCode": "USD"
        },
        "budget": {
            "amount": 100.00,
            "currencyCode": "USD"
        },
        "anomalyScore": 0.85,
        "projectId": PROJECT_ID,
        "serviceName": "Compute Engine",
        "resourceName": f"projects/{PROJECT_ID}/zones/us-central1-a/instances/test-instance",
        "type": "SPIKE",
        "description": "Unusual spike in Compute Engine cost."
    }

def publish_message(project_id: str, topic_id: str):
    """Publishes a message to the specified Pub/Sub topic."""
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(project_id, topic_id)

    anomaly_data = create_dummy_anomaly()
    data_str = json.dumps(anomaly_data)
    data = data_str.encode("utf-8")

    logger.info(f"Publishing message to {topic_path}...")
    logger.info(f"Data: {data_str}")

    try:
        future = publisher.publish(topic_path, data)
        message_id = future.result()
        logger.info(f"Message published with ID: {message_id}")
    except Exception as e:
        logger.error(f"Failed to publish message: {e}")

if __name__ == "__main__":
    publish_message(PROJECT_ID, TOPIC_ID)
