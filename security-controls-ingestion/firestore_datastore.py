"""Firestore datastore for Security Controls Ingestion"""

from typing import List, Dict, Any
import logging
from google.cloud import firestore
import config

logger = logging.getLogger(__name__)

class Datastore:
    """Firestore implementation for Security Controls"""
    
    def __init__(self):
        db_name = config.FIRESTORE_DB
        if db_name == '(default)':
            self.db = firestore.Client(project=config.GCP_PROJECT_ID)
        else:
            self.db = firestore.Client(project=config.GCP_PROJECT_ID, database=db_name)
        
        self.collection = config.FIRESTORE_COLLECTION_CONTROLS
        
        logger.info(f"Initialized Firestore datastore:")
        logger.info(f"  DB: {db_name}, Collection: {self.collection}")
    
    async def upsert_controls(self, controls: List[Dict[str, Any]]) -> int:
        """
        Insert controls using Firestore batch operations.
        Using 'id' as document ID.
        """
        if not controls:
            return 0
        
        total_upserted = 0
        batch_size = 500
        
        for i in range(0, len(controls), batch_size):
            batch_controls = controls[i:i + batch_size]
            batch = self.db.batch()
            
            for control in batch_controls:
                control_id = control.get('id')
                if not control_id:
                    logger.warning(f"Skipping control without id: {control}")
                    continue
                
                doc_ref = self.db.collection(self.collection).document(control_id)
                batch.set(doc_ref, control)
                total_upserted += 1
            
            try:
                batch.commit()
                logger.info(f"Committed batch of {len(batch_controls)} controls")
            except Exception as e:
                logger.error(f"Error committing batch: {e}")
                raise
        
        return total_upserted
    
    async def close(self):
        """Close Firestore connections"""
        # Firestore client doesn't require explicit closing usually, but good practice if needed
        pass
