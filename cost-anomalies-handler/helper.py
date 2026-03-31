import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional
from google.cloud import firestore

import config

logger = logging.getLogger(__name__)

# Initialize Firestore clients
# We initialize them here to be used by the helper classes
firestore_client = firestore.Client(
    project=config.GCP_PROJECT_ID,
    database=config.FIRESTORE_DATABASE
)

metadata_client = firestore.Client(
    project=config.GCP_PROJECT_ID,
    database=config.METADATA_DATABASE
)

class AnomalyMetadataEnricher:
    """Enriches anomaly data with project metadata"""
    
    def __init__(self):
        self.metadata_cache = {}
        self.cache_loaded = False
    
    def load_metadata(self) -> Dict[str, Dict[str, Any]]:
        """
        Load project metadata from Firestore.
        
        Returns:
            Dictionary mapping project_id to metadata
        """
        if self.cache_loaded:
            return self.metadata_cache
        
        logger.info("Loading project metadata from Firestore...")
        
        try:
            collection_ref = metadata_client.collection(config.METADATA_COLLECTION)
            docs = collection_ref.stream()
            
            metadata = {}
            for doc in docs:
                doc_dict = doc.to_dict()
                project_id = doc_dict.get(config.METADATA_PROJECT_ID_FIELD)
                
                if project_id:
                    # Extract only the fields we need
                    metadata_fields = {}
                    for field in config.METADATA_FIELD_LIST:
                        if field in doc_dict:
                            metadata_fields[field] = doc_dict[field]
                    
                    if metadata_fields:
                        metadata[project_id] = metadata_fields
            
            self.metadata_cache = metadata
            self.cache_loaded = True
            logger.info(f"Loaded metadata for {len(metadata)} projects")
            return metadata
            
        except Exception as e:
            logger.error(f"Error loading metadata: {e}")
            return {}
    
    def enrich_anomaly(self, anomaly: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrich anomaly with project metadata.
        
        Args:
            anomaly: Anomaly data from Pub/Sub message
            
        Returns:
            Enriched anomaly dictionary
        """
        metadata = self.load_metadata()
        
        # Extract project_id from anomaly
        project_id = anomaly.get('project_id') or anomaly.get('projectId')
        
        if project_id and project_id in metadata:
            # Add metadata fields
            for field, value in metadata[project_id].items():
                anomaly[field] = value
            logger.debug(f"Enriched anomaly for project: {project_id}")
        else:
            # Add null values for missing metadata fields
            for field in config.METADATA_FIELD_LIST:
                if field not in anomaly:
                    anomaly[field] = None
            if project_id:
                logger.warning(f"No metadata found for project: {project_id}")
        
        # Add processing metadata
        anomaly['processed_at'] = datetime.utcnow().isoformat()
        anomaly['handler_version'] = '1.0.0'
        
        return anomaly

# Initialize enricher instance to be used by main.py
enricher = AnomalyMetadataEnricher()

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
