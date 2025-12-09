#!/usr/bin/env python3
"""
FastAPI application to handle GCP Cost Anomaly Pub/Sub messages.
Receives anomaly notifications, enriches with project metadata, and stores in Firestore.
"""

import os
import json
import base64
import logging
from typing import Dict, Any

from fastapi import FastAPI, Request, HTTPException

# Import configuration and helpers
import config
from dataclass import PubSubMessage
import helper

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Cost Anomaly Handler",
    description="Handles GCP cost anomaly Pub/Sub messages and stores enriched data in Firestore",
    version="1.0.0"
)

logger.info(f"Initialized Cost Anomaly Handler")
logger.info(f"Firestore database: {config.FIRESTORE_DATABASE}")
logger.info(f"Enrichment database: {config.ENRICHMENT_DATABASE}")


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "cost-anomaly-handler",
        "version": "1.0.0"
    }


@app.get("/health")
async def health():
    """Detailed health check"""
    return {
        "status": "healthy",
        "firestore_database": config.FIRESTORE_DATABASE,
        "enrichment_database": config.ENRICHMENT_DATABASE,
        "enrichment_cache_loaded": helper.enricher.cache_loaded,
        "enrichment_projects_count": len(helper.enricher.enrichment_cache)
    }


@app.post("/pubsub/push")
async def handle_pubsub_push(request: Request):
    """
    Handle Pub/Sub push notification for cost anomalies.
    
    Expected message format from GCP Cost Anomaly Detection:
    {
        "message": {
            "data": "<base64-encoded-json>",
            "messageId": "...",
            "publishTime": "..."
        },
        "subscription": "..."
    }
    """
    try:
        # Parse request body
        body = await request.json()
        logger.debug(f"Received Pub/Sub message: {body}")
        
        # Validate message format using Pydantic model (optional, but good practice)
        # Note: We don't enforce strict validation here to avoid rejecting messages 
        # if the format changes slightly, but we check for key fields.
        if 'message' not in body:
            raise HTTPException(status_code=400, detail="Invalid Pub/Sub message format")
        
        message = body['message']
        
        # Decode base64 data
        if 'data' not in message:
            raise HTTPException(status_code=400, detail="No data in Pub/Sub message")
        
        data_bytes = base64.b64decode(message['data'])
        data_str = data_bytes.decode('utf-8')
        anomaly_data = json.loads(data_str)
        
        logger.info(f"Processing anomaly: {anomaly_data.get('anomaly_id', 'unknown')}")
        
        # Enrich anomaly with project metadata
        enriched_anomaly = helper.enricher.enrich_anomaly(anomaly_data)
        
        # Save to Firestore
        doc_id = helper.save_anomaly_to_firestore(enriched_anomaly)
        
        logger.info(f"Successfully processed and saved anomaly: {doc_id}")
        
        # Return 200 to acknowledge message
        return {
            "status": "success",
            "document_id": doc_id,
            "message": "Anomaly processed and saved"
        }
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON in message data: {str(e)}")
    
    except Exception as e:
        logger.error(f"Error processing Pub/Sub message: {e}", exc_info=True)
        # Return 500 to trigger retry
        raise HTTPException(status_code=500, detail=f"Error processing message: {str(e)}")


@app.post("/anomaly")
async def create_anomaly(anomaly: Dict[str, Any]):
    """
    Direct endpoint to create an anomaly (for testing).
    
    Args:
        anomaly: Anomaly data dictionary
    """
    try:
        logger.info(f"Received direct anomaly submission")
        
        # Enrich anomaly
        enriched_anomaly = helper.enricher.enrich_anomaly(anomaly)
        
        # Save to Firestore
        doc_id = helper.save_anomaly_to_firestore(enriched_anomaly)
        
        return {
            "status": "success",
            "document_id": doc_id,
            "message": "Anomaly created successfully"
        }
        
    except Exception as e:
        logger.error(f"Error creating anomaly: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reload-enrichment")
async def reload_enrichment():
    """Reload enrichment data cache"""
    try:
        helper.enricher.cache_loaded = False
        helper.enricher.enrichment_cache = {}
        enrichment_data = helper.enricher.load_enrichment_data()
        
        return {
            "status": "success",
            "projects_loaded": len(enrichment_data),
            "message": "Enrichment cache reloaded"
        }
        
    except Exception as e:
        logger.error(f"Error reloading enrichment data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
