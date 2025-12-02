"""Main entry point for Security Controls Ingestion"""

import logging
import asyncio
import sys
from datetime import datetime
from firestore_datastore import Datastore
from ingestion_service import IngestionService
from cai_client import CAIClient
from scc_management_client import SCCManagementClient
from config import get_settings

# Initialize settings
settings = get_settings()

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f'ingestion_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    ]
)
logger = logging.getLogger(__name__)

async def main():
    """Main execution function"""
    start_time = datetime.now()
    logger.info("=" * 80)
    logger.info(f"{settings.app_name} Started")
    logger.info(f"Environment: {settings.app_env}")
    logger.info(f"Start Time: {start_time.isoformat()}")
    logger.info("=" * 80)
    
    datastore = None
    
    try:
        # Create datastore
        datastore = Datastore()
        
        # Create CAI client
        cai_client = CAIClient()
        
        # Create SCC Management client
        scc_client = SCCManagementClient()
        
        # Create ingestion service
        service = IngestionService(datastore, cai_client, scc_client)
        
        # Run ingestion
        stats = await service.ingest_controls()
        
        # Log results
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        logger.info("=" * 80)
        logger.info(f"{settings.app_name} Completed")
        logger.info(f"End Time: {end_time.isoformat()}")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info(f"Controls Loaded: {stats['total_loaded']}")
        logger.info(f"Controls Upserted: {stats['total_upserted']}")
        logger.info("=" * 80)
        
        return 0
        
    except Exception as e:
        logger.error(f"Fatal error during ingestion: {e}", exc_info=True)
        return 1
        
    finally:
        if datastore:
            await datastore.close()

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
