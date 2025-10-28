#!/usr/bin/env python3
"""
FastAPI application to handle GCP Cost Anomaly Pub/Sub messages.
Receives anomaly notifications, enriches with project metadata, and stores in Firestore.
"""

import os
import json
import base64
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import FastAPI, Request, HTTPException
from google.cloud import firestore
from pydantic import BaseModel

# Import configuration
import config

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

# Initialize Firestore clients
firestore_client = firestore.Client(
    project=config.GCP_PROJECT_ID,
    database=config.FIRESTORE_DATABASE
)

enrichment_client = firestore.Client(
    project=config.GCP_PROJECT_ID,
    database=config.ENRICHMENT_DATABASE
)

logger.info(f"Initialized Cost Anomaly Handler")
logger.info(f"Firestore database: {config.FIRESTORE_DATABASE}")
logger.info(f"Enrichment database: {config.ENRICHMENT_DATABASE}")


class PubSubMessage(BaseModel):
    """Pub/Sub message format"""
    message: Dict[str, Any]
    subscription: str


class AnomalyEnricher:
    """Enriches anomaly data with project metadata"""
    
    def __init__(self):
        self.enrichment_cache = {}
        self.cache_loaded = False
    
    def load_enrichment_data(self) -> Dict[str, Dict[str, Any]]:
        """
        Load project enrichment data from Firestore.
        
        Returns:
            Dictionary mapping project_id to enrichment data
        """
        if self.cache_loaded:
            return self.enrichment_cache
        
        logger.info("Loading project enrichment data from Firestore...")
        
        try:
            collection_ref = enrichment_client.collection(config.ENRICHMENT_COLLECTION)
            docs = collection_ref.stream()
            
            enrichment_data = {}
            for doc in docs:
                doc_dict = doc.to_dict()
                project_id = doc_dict.get(config.ENRICHMENT_PROJECT_ID_FIELD)
                
                if project_id:
                    # Extract only the fields we need
                    enrichment_fields = {}
                    for field in config.ENRICHMENT_FIELD_LIST:
                        if field in doc_dict:
                            enrichment_fields[field] = doc_dict[field]
                    
                    if enrichment_fields:
                        enrichment_data[project_id] = enrichment_fields
            
            self.enrichment_cache = enrichment_data
            self.cache_loaded = True
            logger.info(f"Loaded enrichment data for {len(enrichment_data)} projects")
            return enrichment_data
            
        except Exception as e:
            logger.error(f"Error loading enrichment data: {e}")
            return {}
    
    def enrich_anomaly(self, anomaly: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrich anomaly with project metadata.
        
        Args:
            anomaly: Anomaly data from Pub/Sub message
            
        Returns:
            Enriched anomaly dictionary
        """
        enrichment_data = self.load_enrichment_data()
        
        # Extract project_id from anomaly
        project_id = anomaly.get('project_id') or anomaly.get('projectId')
        
        if project_id and project_id in enrichment_data:
            # Add enrichment fields
            for field, value in enrichment_data[project_id].items():
                anomaly[field] = value
            logger.debug(f"Enriched anomaly for project: {project_id}")
        else:
            # Add null values for missing enrichment fields
            for field in config.ENRICHMENT_FIELD_LIST:
                if field not in anomaly:
                    anomaly[field] = None
            if project_id:
                logger.warning(f"No enrichment data found for project: {project_id}")
        
        # Add processing metadata
        anomaly['processed_at'] = datetime.utcnow().isoformat()
        anomaly['handler_version'] = '1.0.0'
        
        return anomaly


# Initialize enricher
enricher = AnomalyEnricher()


def save_anomaly_to_firestore(anomaly: Dict[str, Any]) -> str:
    """
    Save anomaly to Firestore.
    
    Args:
        anomaly: Enriched anomaly data
        
    Returns:
        Document ID
    """
    try:
        collection_ref = firestore_client.collection(config.FIRESTORE_COLLECTION)
        
        # Generate document ID from anomaly ID or use auto-generated
        doc_id = anomaly.get('anomaly_id') or anomaly.get('id')
        
        if doc_id:
            doc_ref = collection_ref.document(doc_id)
            doc_ref.set(anomaly, merge=True)
            logger.info(f"Saved anomaly with ID: {doc_id}")
        else:
            # Auto-generate ID
            doc_ref = collection_ref.add(anomaly)
            doc_id = doc_ref[1].id
            logger.info(f"Saved anomaly with auto-generated ID: {doc_id}")
        
        return doc_id
        
    except Exception as e:
        logger.error(f"Error saving anomaly to Firestore: {e}")
        raise


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
        "enrichment_cache_loaded": enricher.cache_loaded,
        "enrichment_projects_count": len(enricher.enrichment_cache)
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
        
        # Extract message
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
        enriched_anomaly = enricher.enrich_anomaly(anomaly_data)
        
        # Save to Firestore
        doc_id = save_anomaly_to_firestore(enriched_anomaly)
        
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
        enriched_anomaly = enricher.enrich_anomaly(anomaly)
        
        # Save to Firestore
        doc_id = save_anomaly_to_firestore(enriched_anomaly)
        
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
        enricher.cache_loaded = False
        enricher.enrichment_cache = {}
        enrichment_data = enricher.load_enrichment_data()
        
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
