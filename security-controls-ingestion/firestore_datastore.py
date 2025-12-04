"""Firestore datastore for Security Controls Ingestion"""

from typing import List, Dict, Any
import logging
from google.cloud import firestore
from config import get_settings

logger = logging.getLogger(__name__)

class Datastore:
    """Firestore implementation for Security Controls"""
    
    def __init__(self):
        self.settings = get_settings()
        db_name = self.settings.firestore_database
        project_id = self.settings.gcp_project_id
        
        if db_name == '(default)':
            self.db = firestore.Client(project=project_id)
        else:
            self.db = firestore.Client(project=project_id, database=db_name)
        
        # Default collections from settings
        self.org_preventive_collection = self.settings.firestore_collection_org_preventive
        self.project_preventive_collection = self.settings.firestore_collection_project_preventive
        self.org_detective_collection = self.settings.firestore_collection_org_detective
        self.project_detective_collection = self.settings.firestore_collection_project_detective
        self.firewall_collection = self.settings.firestore_collection_firewall
        
        logger.info(f"Initialized Firestore datastore:")
        logger.info(f"  Project: {project_id}")
        logger.info(f"  DB: {db_name}")
        logger.info(f"  Org Preventive: {self.org_preventive_collection}")
        logger.info(f"  Project Preventive: {self.project_preventive_collection}")
        logger.info(f"  Org Detective: {self.org_detective_collection}")
        logger.info(f"  Project Detective: {self.project_detective_collection}")
        logger.info(f"  Firewall: {self.firewall_collection}")
    
    async def upsert_controls(self, controls: List[Dict[str, Any]], collection_name: str) -> int:
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
                
                doc_ref = self.db.collection(collection_name).document(control_id)
                batch.set(doc_ref, control)
                total_upserted += 1
            
            try:
                batch.commit()
                logger.info(f"Committed batch of {len(batch_controls)} controls to {collection_name}")
            except Exception as e:
                logger.error(f"Error committing batch: {e}")
                raise
        
        return total_upserted
    
    async def close(self):
        """Close Firestore connections"""
        pass
