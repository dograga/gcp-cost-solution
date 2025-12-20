#!/usr/bin/env python3
"""
Cloud Run Job to collect Google Cloud health events from Service Health API
and store them in Firestore. Monitors specified regions and maintains regional status.
"""

import os
import logging
import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Set

from google.cloud import servicehealth_v1
from google.cloud import firestore
from google.api_core import exceptions

# Import configuration
from config import get_settings

# Initialize settings
settings = get_settings()

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Log configuration on startup
logger.info(f"Starting with environment: {settings.environment}")
logger.debug(f"Configuration: {settings.model_dump()}")


class HealthEventMonitor:
    """Collects Google Cloud health events and stores in Firestore."""
    
    def __init__(self):
        """Initialize the Service Health and Firestore clients."""
        self.health_client = servicehealth_v1.ServiceHealthClient()
        self.db = firestore.Client(project=settings.gcp_project_id, database=settings.firestore_database)
        
        # Get configuration
        self.organization_id = settings.organization_id
        self.regions = settings.regions
        self.event_categories = settings.event_categories
        self.filter_by_product = settings.filter_by_product
        self.products = settings.products
        self.region_status_collection = settings.region_status_collection
        self.events_collection = settings.events_collection
        
        logger.info(f"Initialized HealthEventMonitor for organization: {self.organization_id}")
        logger.info(f"Monitoring regions: {self.regions}")
        if self.filter_by_product:
            logger.info(f"Product filtering: ENABLED - Monitoring {len(self.products)} products")
            logger.debug(f"Products: {self.products}")
        else:
            logger.info(f"Product filtering: DISABLED - Monitoring all products")
        logger.info(f"Target collections: {self.region_status_collection}, {self.events_collection}")
    
    def get_organization_events(self) -> List[Dict[str, Any]]:
        """
        Fetch all active events for the organization.
        
        Returns:
            List of event records
        """
        logger.info("Fetching organization events from Service Health API")
        all_events = []
        
        try:
            # Construct parent path for organization
            parent = f"organizations/{self.organization_id}/locations/global"
            
            # Build filter string
            filter_parts = ["state=ACTIVE"]
            if self.event_categories:
                categories_filter = " OR ".join([f"category={cat}" for cat in self.event_categories])
                filter_parts.append(f"({categories_filter})")
            
            filter_str = " AND ".join(filter_parts)
            logger.debug(f"Using API filter: {filter_str}")
            
            # Create request
            request = servicehealth_v1.ListOrganizationEventsRequest(
                parent=parent,
                filter=filter_str
            )
            
            # List events
            page_result = self.health_client.list_organization_events(request=request)
            
            for event in page_result:
                # Parse event into our format
                event_record = self._parse_event(event)
                
                # Skip CLOSED and RESOLVED events (additional safety check)
                if event_record.get('state') in ['CLOSED', 'RESOLVED']:
                    logger.debug(f"Skipping {event_record.get('state')} event: {event_record['event_id']}")
                    continue
                
                # Filter by regions and products if specified
                if self._should_include_event(event_record):
                    all_events.append(event_record)
                    logger.debug(f"Collected event: {event_record['event_id']} - {event_record['title']}")
            
            logger.info(f"Collected {len(all_events)} events from Service Health API")
            return all_events
            
        except exceptions.GoogleAPIError as e:
            logger.error(f"Error fetching organization events: {e}")
            raise
    
    def _should_include_event(self, event_record: Dict[str, Any]) -> bool:
        """
        Check if event should be included based on region and product filters.
        
        Args:
            event_record: Event record dictionary
            
        Returns:
            True if event should be included
        """
        # Check region filter
        region_match = self._matches_region_filter(event_record)
        if not region_match:
            return False
        
        # Check product filter (only if filtering is enabled)
        if self.filter_by_product and self.products:
            product_match = self._matches_product_filter(event_record)
            if not product_match:
                return False
        
        return True
    
    def _matches_region_filter(self, event_record: Dict[str, Any]) -> bool:
        """
        Check if event matches region filter.
        
        Args:
            event_record: Event record dictionary
            
        Returns:
            True if event matches region filter
        """
        event_locations = event_record.get('locations', [])
        
        # If no locations specified, it's a global event
        if not event_locations:
            return 'global' in self.regions
        
        # Check if any event location matches our monitored regions
        for location in event_locations:
            # Extract region from location (e.g., "us-central1-a" -> "us-central1")
            region = location.split('-')[0:2]
            region = '-'.join(region) if len(region) >= 2 else location
            
            if region in self.regions or location in self.regions:
                return True
        
        # Check for global in locations
        if 'global' in [loc.lower() for loc in event_locations]:
            return 'global' in self.regions
        
        return False
    
    def _matches_product_filter(self, event_record: Dict[str, Any]) -> bool:
        """
        Check if event matches product filter.
        
        Args:
            event_record: Event record dictionary
            
        Returns:
            True if event matches product filter
        """
        event_impacts = event_record.get('impacts', [])
        
        # If no impacts, we can't determine product
        if not event_impacts:
            return False
        
        # Check if any impact product matches our monitored products
        for impact in event_impacts:
            product = impact.get('product')
            if not product:
                continue
            
            product_lower = product.lower()
            for monitored_product in self.products:
                monitored_lower = monitored_product.lower()
                # Match if exact or if monitored product is a substring (e.g., "SQL" matches "Cloud SQL")
                # but avoid too broad matches if possible.
                if monitored_lower == product_lower or monitored_lower in product_lower:
                    return True
        
        return False
    
    def _parse_event(self, event: servicehealth_v1.OrganizationEvent) -> Dict[str, Any]:
        """
        Parse an event object into a dictionary.
        
        Args:
            event: The OrganizationEvent object
            
        Returns:
            Dictionary with event data
        """
        # Extract event ID from name
        event_id = event.name.split('/')[-1]
        
        # Parse impacts and locations
        impacts, locations = self._parse_impacts(event.event_impacts)
        
        # Determine affected regions
        affected_regions = self._extract_regions_from_locations(locations)
        
        # Current time for tracking
        now_iso = datetime.now(timezone.utc).isoformat()
        
        return {
            'event_id': event_id,
            'event_name': event.name,
            'title': event.title,
            'description': getattr(event, 'description', None),
            'category': event.category.name if event.category else None,
            'state': event.state.name if event.state else None,
            'detailed_category': getattr(event.detailed_category, 'name', None) if hasattr(event, 'detailed_category') else None,
            'detailed_state': getattr(event.detailed_state, 'name', None) if hasattr(event, 'detailed_state') else None,
            'start_time': event.start_time.isoformat() if event.start_time else None,
            'end_time': event.end_time.isoformat() if event.end_time else None,
            'update_time': event.update_time.isoformat() if event.update_time else None,
            'impacts': impacts,
            'locations': locations,
            'affected_regions': affected_regions,
            'collected_at': now_iso,
            'last_seen_at': now_iso,
        }

    def _parse_impacts(self, event_impacts) -> tuple[List[Dict[str, Any]], List[str]]:
        """Helper to parse event impacts and extract locations."""
        impacts = []
        locations = set()
        
        for impact in event_impacts:
            location_str = None
            if hasattr(impact, 'location') and impact.location:
                location_str = getattr(impact.location, 'location_name', str(impact.location))
            
            product_str = None
            if hasattr(impact, 'product') and impact.product:
                product_str = getattr(impact.product, 'product_name', str(impact.product))
            
            impacts.append({
                'product': product_str,
                'location': location_str,
            })
            
            if location_str:
                locations.add(location_str)
                
        return impacts, list(locations)
    
    def _extract_regions_from_locations(self, locations: List[str]) -> List[str]:
        """
        Extract region names from location strings.
        
        Args:
            locations: List of location strings
            
        Returns:
            List of region names
        """
        regions = set()
        
        for location in locations:
            if not location:
                continue
            
            location_lower = location.lower()
            
            # Check for global
            if location_lower == 'global':
                regions.add('global')
                continue
            
            # Extract region from zone (e.g., "asia-southeast1-a" -> "asia-southeast1")
            parts = location.split('-')
            if len(parts) >= 2:
                region = '-'.join(parts[0:2])
                regions.add(region)
            else:
                regions.add(location)
        
        return list(regions)
    
    def save_events_to_firestore(self, events: List[Dict[str, Any]]) -> Set[str]:
        """
        Save events to Firestore events collection.
        Preserves 'ignore' and 'comment' fields if they already exist.
        
        Args:
            events: List of event records
            
        Returns:
            Set of event IDs that were saved
        """
        if not events:
            logger.info("No events to save")
            return set()
        
        try:
            collection_ref = self.db.collection(self.events_collection)
            batch = self.db.batch()
            batch_count = 0
            saved_event_ids = set()
            
            for event in events:
                # Use event_id as document ID for idempotency
                doc_id = event['event_id']
                doc_ref = collection_ref.document(doc_id)
                
                # Add default values for portal-managed fields if not present
                if 'ignore' not in event:
                    event['ignore'] = False
                if 'comment' not in event:
                    event['comment'] = ''
                
                # Use merge=True to preserve existing 'ignore' and 'comment' fields
                # This prevents overwriting values set by the cloud platform team
                batch.set(doc_ref, event, merge=True)
                batch_count += 1
                saved_event_ids.add(doc_id)
                
                # Firestore batch limit is 500 operations
                if batch_count >= 500:
                    batch.commit()
                    logger.debug(f"Committed batch of {batch_count} events")
                    batch = self.db.batch()
                    batch_count = 0
            
            # Commit remaining records
            if batch_count > 0:
                batch.commit()
            
            logger.info(f"Successfully saved {len(saved_event_ids)} events to Firestore")
            return saved_event_ids
                
        except Exception as e:
            logger.error(f"Error saving events to Firestore: {e}")
            raise
    
    def cleanup_old_events(self, current_event_ids: Set[str]):
        """
        Remove events from Firestore that are no longer in the current ingestion.
        
        Args:
            current_event_ids: Set of event IDs from current ingestion
        """
        try:
            collection_ref = self.db.collection(self.events_collection)
            
            # Get all existing event IDs
            existing_docs = collection_ref.stream()
            existing_event_ids = set()
            docs_to_delete = []
            
            for doc in existing_docs:
                existing_event_ids.add(doc.id)
                if doc.id not in current_event_ids:
                    docs_to_delete.append(doc.id)
            
            # Delete old events
            if docs_to_delete:
                batch = self.db.batch()
                batch_count = 0
                
                for doc_id in docs_to_delete:
                    doc_ref = collection_ref.document(doc_id)
                    batch.delete(doc_ref)
                    batch_count += 1
                    
                    if batch_count >= 500:
                        batch.commit()
                        batch = self.db.batch()
                        batch_count = 0
                
                if batch_count > 0:
                    batch.commit()
                
                logger.info(f"Removed {len(docs_to_delete)} old events from Firestore")
            else:
                logger.info("No old events to remove")
                
        except Exception as e:
            logger.error(f"Error cleaning up old events: {e}")
            raise
    
    def cleanup_old_regions(self):
        """
        Remove region status documents for regions that are no longer monitored.
        """
        try:
            collection_ref = self.db.collection(self.region_status_collection)
            
            # Get all existing region documents
            existing_docs = collection_ref.stream()
            docs_to_delete = []
            
            for doc in existing_docs:
                if doc.id not in self.regions:
                    docs_to_delete.append(doc.id)
            
            # Delete old regions
            if docs_to_delete:
                batch = self.db.batch()
                batch_count = 0
                
                for doc_id in docs_to_delete:
                    doc_ref = collection_ref.document(doc_id)
                    batch.delete(doc_ref)
                    batch_count += 1
                    logger.info(f"Removing old region: {doc_id}")
                    
                    if batch_count >= 500:
                        batch.commit()
                        batch = self.db.batch()
                        batch_count = 0
                
                if batch_count > 0:
                    batch.commit()
                
                logger.info(f"Removed {len(docs_to_delete)} old regions from Firestore")
            else:
                logger.debug("No old regions to remove")
                
        except Exception as e:
            logger.error(f"Error cleaning up old regions: {e}")
            raise
    
    def update_region_status(self, events: List[Dict[str, Any]]):
        """
        Update region status collection based on current events.
        
        Args:
            events: List of event records
        """
        try:
            # Count events per region
            region_event_counts = {}
            
            # Initialize all monitored regions with 0 events
            for region in self.regions:
                region_event_counts[region] = 0
            
            # Count events per region
            for event in events:
                affected_regions = event.get('affected_regions', [])
                
                # If no specific regions, count as global
                if not affected_regions:
                    affected_regions = ['global']
                
                for region in affected_regions:
                    if region in region_event_counts:
                        region_event_counts[region] += 1
                    else:
                        # Region not in monitored list but has events
                        logger.warning(f"Event affects unmonitored region: {region}")
                        region_event_counts[region] = 1
            
            # Update Firestore
            collection_ref = self.db.collection(self.region_status_collection)
            batch = self.db.batch()
            batch_count = 0
            
            for region, event_count in region_event_counts.items():
                doc_ref = collection_ref.document(region)
                
                status_data = {
                    'region': region,
                    'status': 'unhealthy' if event_count > 0 else 'healthy',
                    'event_count': event_count,
                    'last_updated': datetime.now(timezone.utc).isoformat(),
                }
                
                batch.set(doc_ref, status_data)
                batch_count += 1
                
                if batch_count >= 500:
                    batch.commit()
                    batch = self.db.batch()
                    batch_count = 0
            
            if batch_count > 0:
                batch.commit()
            
            logger.info(f"Updated status for {len(region_event_counts)} regions")
            
            # Log detailed summary
            for region, count in region_event_counts.items():
                status = 'unhealthy' if count > 0 else 'healthy'
                logger.info(f"  {region}: {status} ({count} events)")
            
            # Log summary
            unhealthy_regions = [r for r, c in region_event_counts.items() if c > 0]
            if unhealthy_regions:
                logger.warning(f"Unhealthy regions: {unhealthy_regions}")
            else:
                logger.info("✅ All monitored regions are healthy")
                
        except Exception as e:
            logger.error(f"Error updating region status: {e}")
            raise
    
    def run(self):
        """
        Main execution method to collect health events and update status.
        """
        logger.info("Starting health event collection")
        
        try:
            # Fetch events from Service Health API
            events = self.get_organization_events()
            
            # Save events to Firestore
            current_event_ids = self.save_events_to_firestore(events)
            
            # Clean up old events that are no longer active
            self.cleanup_old_events(current_event_ids)
            
            # Clean up old regions that are no longer monitored
            self.cleanup_old_regions()
            
            # Update region status
            self.update_region_status(events)
            
            logger.info("Health event collection completed successfully")
            
        except Exception as e:
            logger.error(f"Job failed with error: {e}")
            raise


def main():
    """Main entry point for the Cloud Run job."""
    logger.info("=" * 80)
    logger.info("Starting GCP Health Event Monitor Job")
    logger.info("=" * 80)
    
    try:
        monitor = HealthEventMonitor()
        monitor.run()
        logger.info("Health event monitoring completed successfully")
        
    except Exception as e:
        logger.error(f"Job failed with error: {e}")
        raise


if __name__ == "__main__":
    main()
