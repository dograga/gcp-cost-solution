#!/usr/bin/env python3
"""
Cloud Run Job to collect Google Cloud cost recommendations from all projects
and store them in Firestore. Runs daily to collect active recommendations.
"""

import os
import logging
import json
from datetime import datetime
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from google.cloud import recommender_v1
from google.cloud import firestore
from google.cloud import resourcemanager_v3
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


class CostRecommendationCollector:
    """Collects cost recommendations from all GCP projects and stores in Firestore."""
    
    def __init__(self):
        """Initialize the recommender and Firestore clients."""
        self.recommender_client = recommender_v1.RecommenderClient()
        self.db = firestore.Client(project=settings.gcp_project_id, database=settings.firestore_database)
        self.projects_client = resourcemanager_v3.ProjectsClient()
        
        # Get configuration from settings
        self.project_id = settings.gcp_project_id
        self.collection_name = settings.firestore_collection
        self.recommender_types = settings.recommender_types
        self.state_filter = settings.recommendation_state_filter
        
        # Inventory configuration
        self.use_inventory = settings.use_inventory_collection
        self.inventory_db_name = settings.inventory_database
        self.inventory_collection_name = settings.inventory_collection
        self.inventory_project_id_field = settings.inventory_project_id_field
        
        # Performance configuration
        self.max_workers = settings.max_workers
        self.batch_size = settings.firestore_batch_size
        
        logger.info(f"Initialized CostRecommendationCollector for project: {self.project_id}")
        logger.info(f"Target Firestore collection: {self.collection_name}")
        logger.info(f"Use inventory collection: {self.use_inventory}")
        if self.use_inventory:
            logger.info(f"Inventory source: {self.inventory_db_name}/{self.inventory_collection_name}")
        logger.info(f"Recommender types: {len(self.recommender_types)} types configured")
        logger.info(f"Performance: {self.max_workers} workers, batch size {self.batch_size}")
    
    def get_projects_from_inventory(self) -> List[str]:
        """
        Retrieve project IDs from Firestore inventory collection.
        
        Returns:
            List of project IDs
        """
        logger.info(f"Reading projects from inventory: {self.inventory_db_name}/{self.inventory_collection_name}")
        projects = []
        
        try:
            # Connect to inventory database (may be different from recommendations DB)
            inventory_db = firestore.Client(project=settings.gcp_project_id, database=self.inventory_db_name)
            collection_ref = inventory_db.collection(self.inventory_collection_name)
            
            # Read all documents from the inventory collection
            docs = collection_ref.stream()
            
            for doc in docs:
                doc_data = doc.to_dict()
                if self.inventory_project_id_field in doc_data:
                    project_id = doc_data[self.inventory_project_id_field]
                    projects.append(project_id)
                    logger.debug(f"Found project from inventory: {project_id}")
                else:
                    logger.warning(f"Document {doc.id} missing field '{self.inventory_project_id_field}'")
            
            logger.info(f"Total projects loaded from inventory: {len(projects)}")
            return projects
            
        except Exception as e:
            logger.error(f"Error reading from inventory collection: {e}")
            raise
    
    def get_all_projects(self) -> List[str]:
        """
        Retrieve all accessible GCP projects based on scope configuration.
        Supports project, folder, organization level collection, or inventory collection.
        
        Returns:
            List of project IDs
        """
        # If using inventory collection, read from there
        if self.use_inventory:
            return self.get_projects_from_inventory()
        
        scope_type = settings.scope_type
        scope_id = settings.scope_id
        
        logger.info(f"Fetching projects for scope: {scope_type} = {scope_id}")
        projects = []
        
        try:
            if scope_type == 'project':
                # Single project mode
                logger.info(f"Running in project mode for: {scope_id}")
                return [scope_id]
            
            elif scope_type == 'folder':
                # Folder mode - get all projects under the folder
                logger.info(f"Running in folder mode for: {scope_id}")
                # Ensure folder ID is in correct format
                if not scope_id.startswith('folders/'):
                    scope_id = f"folders/{scope_id}"
                
                request = resourcemanager_v3.ListProjectsRequest(
                    parent=scope_id
                )
                page_result = self.projects_client.list_projects(request=request)
                
                for project in page_result:
                    if project.state == resourcemanager_v3.Project.State.ACTIVE:
                        project_id = project.name.split('/')[-1]
                        projects.append(project_id)
                        logger.info(f"Found project in folder: {project_id} ({project.display_name})")
                    else:
                        logger.debug(f"Skipping project {project.name.split('/')[-1]} with state: {project.state.name}")
                
            elif scope_type == 'organization':
                # Organization mode - get all projects under the organization
                logger.info(f"Running in organization mode for: {scope_id}")
                # Ensure org ID is in correct format
                if not scope_id.startswith('organizations/'):
                    scope_id = f"organizations/{scope_id}"
                
                # List ALL projects in the organization using a search query
                # This approach gets all projects regardless of folder structure
                logger.info(f"Searching for all projects in organization {scope_id}")
                
                # Use search query to find all projects in the organization
                search_query = f"parent:{scope_id}"
                
                request = resourcemanager_v3.SearchProjectsRequest(
                    query=search_query
                )
                
                logger.debug(f"Searching projects with query: {search_query}")
                page_result = self.projects_client.search_projects(request=request)
                
                total_found = 0
                for project in page_result:
                    total_found += 1
                    logger.debug(f"Found project: {project.name} (state: {project.state.name}, parent: {project.parent})")
                    if project.state == resourcemanager_v3.Project.State.ACTIVE:
                        project_id = project.name.split('/')[-1]
                        projects.append(project_id)
                        logger.info(f"Found project: {project_id} ({project.display_name}) - Parent: {project.parent}")
                    else:
                        logger.debug(f"Skipping project {project.name.split('/')[-1]} with state: {project.state.name}")
                
                logger.info(f"Total projects found in organization: {total_found}, Active projects: {len(projects)}")
            
            else:
                logger.error(f"Invalid scope type: {scope_type}. Must be 'project', 'folder', or 'organization'")
                logger.info(f"Falling back to configured project: {self.project_id}")
                return [self.project_id]
            
            logger.info(f"Total active projects found: {len(projects)}")
            return projects if projects else [self.project_id]
            
        except exceptions.GoogleAPIError as e:
            logger.error(f"Error fetching projects: {e}")
            # If we can't list projects, at least try the configured project
            logger.info(f"Falling back to configured project: {self.project_id}")
            return [self.project_id]
    
    def ensure_firestore_collection(self):
        """Ensure Firestore collection exists (Firestore creates collections automatically)."""
        # Firestore creates collections automatically when first document is added
        # We'll just verify we can access the collection
        try:
            collection_ref = self.db.collection(self.collection_name)
            logger.info(f"Firestore collection '{self.collection_name}' is ready")
        except Exception as e:
            logger.error(f"Error accessing Firestore collection: {e}")
            raise
    
    def discover_recommender_types(self, project_number: str, location: str = 'global') -> List[str]:
        """
        Discover all available recommender types for a project.
        
        Args:
            project_number: The GCP project number
            location: Location to check (default: global)
            
        Returns:
            List of available recommender types
        """
        recommender_types = []
        
        # If specific types are configured, use those
        if self.recommender_types and len(self.recommender_types) > 0 and self.recommender_types[0]:
            logger.info(f"Using configured recommender types: {self.recommender_types}")
            return self.recommender_types
        
        # Otherwise, try to discover all available recommender types
        # Note: The Recommender API doesn't have a direct "list recommenders" method,
        # so we'll use a comprehensive list of known recommender types
        logger.info("No specific recommender types configured, using comprehensive list of all known types")
        
        known_recommender_types = [
            # Compute Engine
            'google.compute.instance.MachineTypeRecommender',
            'google.compute.disk.IdleResourceRecommender',
            'google.compute.instance.IdleResourceRecommender',
            'google.compute.address.IdleResourceRecommender',
            'google.compute.image.IdleResourceRecommender',
            'google.compute.instanceGroupManager.MachineTypeRecommender',
            
            # Cloud SQL
            'google.cloudsql.instance.IdleRecommender',
            'google.cloudsql.instance.OverprovisionedRecommender',
            'google.cloudsql.instance.OutOfDiskRecommender',
            
            # Logging
            'google.logging.productSuggestion.ContainerRecommender',
            
            # BigQuery
            'google.bigquery.capacityCommitments.Recommender',
            'google.bigquery.table.PartitionClusterRecommender',
            
            # Cloud Storage
            'google.storage.bucket.LifecycleRecommender',
            
            # GKE
            'google.container.DiagnosisRecommender',
            
            # Monitoring
            'google.monitoring.productSuggestion.ComputeRecommender',
            
            # App Engine
            'google.appengine.applicationIdleRecommender',
            
            # Cloud Run
            'google.run.service.CostRecommender',
            'google.run.service.IdentityRecommender',
            
            # Cloud Functions
            'google.cloudfunctions.PerformanceRecommender',
            
            # Firestore
            'google.firestore.index.Recommender',
            
            # Spanner
            'google.spanner.instance.IdleRecommender',
            
            # Resource Manager
            'google.resourcemanager.project.IdleRecommender',
            
            # Committed Use Discounts
            'google.compute.commitment.UsageCommitmentRecommender',
            
            # GKE Workload Rightsizing
            'google.container.workload.RightSizingRecommender',
            
            # Cloud Storage
            'google.storage.bucket.SoftDeleteRecommender',
            
            # Reservations
            'google.compute.IdleResourceRecommender',
        ]
        
        logger.info(f"Discovered {len(known_recommender_types)} recommender types")
        return known_recommender_types
    
    def get_recommendations_for_project(
        self, 
        project_id: str,
        project_number: str = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch recommendations for a specific project across all recommender types.
        
        Args:
            project_id: The GCP project ID
            project_number: The GCP project number (optional)
            
        Returns:
            List of recommendation records
        """
        all_recommendations = []
        
        # Try to get project number if not provided
        if not project_number:
            try:
                project_resource = self.projects_client.get_project(
                    name=f"projects/{project_id}"
                )
                project_number = project_resource.name.split('/')[-1]
            except Exception as e:
                logger.warning(f"Could not get project number for {project_id}: {e}")
                project_number = project_id
        
        # Discover all available recommender types
        recommender_types = self.discover_recommender_types(project_number)
        logger.info(f"Checking {len(recommender_types)} recommender types for project {project_id}")
        logger.info(f"Using state filter: {self.state_filter if self.state_filter else 'None (all states)'}")
        
        # Get recommendations for specified locations
        # Use locations from configuration
        locations = settings.recommender_locations
        
        if not locations:
            logger.warning("No locations configured, defaulting to 'global'")
            locations = ['global']
            
        logger.info(f"Checking locations: {locations}")
        
        # Iterate through all recommender types
        for recommender_type in recommender_types:
            for location in locations:
                try:
                    parent = f"projects/{project_number}/locations/{location}/recommenders/{recommender_type}"
                    
                    request = recommender_v1.ListRecommendationsRequest(
                        parent=parent,
                        filter=f"stateInfo.state={self.state_filter}" if self.state_filter else None
                    )
                    
                    recommendations = self.recommender_client.list_recommendations(request=request)
                    
                    rec_count = 0
                    for recommendation in recommendations:
                        record = self._parse_recommendation(
                            recommendation, 
                            project_id, 
                            project_number,
                            location,
                            recommender_type
                        )
                        all_recommendations.append(record)
                        rec_count += 1
                    
                    if rec_count > 0:
                        logger.debug(f"Found {rec_count} recommendation(s) for {recommender_type} in {location}")
                        
                except exceptions.NotFound:
                    # This location doesn't have this recommender type - this is normal
                    continue
                except exceptions.PermissionDenied:
                    # Permission denied is expected for services not enabled or insufficient permissions
                    # Only log at debug level without the full error details to reduce noise
                    logger.debug(f"Permission denied for {recommender_type} in {location} (service may not be enabled or requires additional permissions)")
                    continue
                except exceptions.InvalidArgument:
                    # Invalid argument usually means the recommender doesn't support this location
                    # This is expected and normal - skip silently
                    continue
                except Exception as e:
                    logger.debug(f"Error fetching {recommender_type} for {location}: {type(e).__name__}")
                    continue
        
        logger.info(f"Collected {len(all_recommendations)} recommendations for project {project_id}")
        return all_recommendations
    
    def _parse_recommendation(
        self,
        recommendation: recommender_v1.Recommendation,
        project_id: str,
        project_number: str,
        location: str,
        recommender_type: str
    ) -> Dict[str, Any]:
        """
        Parse a recommendation object into a dictionary for BigQuery.
        
        Args:
            recommendation: The recommendation object
            project_id: The project ID
            project_number: The project number
            location: The location
            recommender_type: The recommender type
            
        Returns:
            Dictionary with recommendation data
        """
        # Extract primary impact (usually cost savings)
        primary_impact = None
        primary_impact_cost = None
        primary_impact_currency = None
        primary_impact_duration = None
        
        if recommendation.primary_impact:
            primary_impact = recommendation.primary_impact.category.name
            if recommendation.primary_impact.cost_projection:
                cost_proj = recommendation.primary_impact.cost_projection
                primary_impact_cost = cost_proj.cost.units + (cost_proj.cost.nanos / 1e9)
                primary_impact_currency = cost_proj.cost.currency_code
                if cost_proj.duration:
                    primary_impact_duration = f"{cost_proj.duration.seconds}s"
        
        # Extract target resources
        target_resources = []
        if recommendation.content and recommendation.content.overview:
            for key, value in recommendation.content.overview.items():
                if 'resource' in key.lower():
                    target_resources.append(str(value))
        
        # Extract operation groups
        operation_groups = []
        if recommendation.content and recommendation.content.operation_groups:
            for op_group in recommendation.content.operation_groups:
                operations = []
                for operation in op_group.operations:
                    operations.append({
                        'action': operation.action,
                        'resource_type': operation.resource_type,
                        'resource': operation.resource,
                        'path': operation.path,
                        'value': str(operation.value) if operation.value else None
                    })
                operation_groups.append({'operations': operations})
        
        # Extract associated insights
        associated_insights = []
        if recommendation.associated_insights:
            for insight in recommendation.associated_insights:
                associated_insights.append(insight.insight)
        
        # Get recommendation ID from name
        recommendation_id = recommendation.name.split('/')[-1]
        
        return {
            'recommendation_id': recommendation_id,
            'recommendation_name': recommendation.name,
            'project_id': project_id,
            'project_number': project_number,
            'location': location,
            'recommender_type': recommender_type,
            'recommender_subtype': recommendation.recommender_subtype,
            'description': recommendation.description,
            'state': recommendation.state_info.state.name if recommendation.state_info else None,
            'priority': recommendation.priority.name if recommendation.priority else None,
            'last_refresh_time': recommendation.last_refresh_time.isoformat() if recommendation.last_refresh_time else None,
            'primary_impact_category': primary_impact,
            'primary_impact_cost_projection': primary_impact_cost,
            'primary_impact_currency': primary_impact_currency,
            'primary_impact_duration': primary_impact_duration,
            'target_resources': json.dumps(target_resources) if target_resources else None,
            'operation_groups': json.dumps(operation_groups) if operation_groups else None,
            'associated_insights': json.dumps(associated_insights) if associated_insights else None,
            'etag': recommendation.etag,
            'xor_group_id': recommendation.xor_group_id,
            'content': str(recommendation.content) if recommendation.content else None,
            'collected_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat(),
        }

    def get_recommendations_for_billing_account(self, billing_account_id: str) -> List[Dict[str, Any]]:
        """
        Fetch recommendations for a billing account (specifically spend-based CUDs).
        
        Args:
            billing_account_id: The billing account ID
            
        Returns:
            List of recommendation records
        """
        logger.info(f"Fetching recommendations for billing account: {billing_account_id}")
        all_recommendations = []
        
        # Spend-based CUD recommender
        recommender_type = 'google.cloudbilling.commitment.SpendBasedCommitmentRecommender'
        
        # Use locations from configuration
        locations = settings.recommender_locations
        if not locations:
            locations = ['global']
            
        for location in locations:
            try:
                # Billing account parent format: billingAccounts/{billing_account_id}/locations/{location}/recommenders/{recommender_id}
                parent = f"billingAccounts/{billing_account_id}/locations/{location}/recommenders/{recommender_type}"
                
                request = recommender_v1.ListRecommendationsRequest(
                    parent=parent,
                    filter=f"stateInfo.state={self.state_filter}" if self.state_filter else None
                )
                
                recommendations = self.recommender_client.list_recommendations(request=request)
                
                rec_count = 0
                for recommendation in recommendations:
                    # Parse similar to project recommendations but with billing account context
                    record = self._parse_recommendation(
                        recommendation, 
                        project_id=f"billing-{billing_account_id}", # Use billing ID as pseudo-project ID
                        project_number=billing_account_id,
                        location=location,
                        recommender_type=recommender_type
                    )
                    all_recommendations.append(record)
                    rec_count += 1
                
                if rec_count > 0:
                    logger.debug(f"Found {rec_count} billing recommendation(s) in {location}")
                    
            except exceptions.NotFound:
                continue
            except exceptions.PermissionDenied:
                logger.debug(f"Permission denied for billing account {billing_account_id} in {location}")
                continue
            except Exception as e:
                logger.debug(f"Error fetching billing recommendations for {location}: {type(e).__name__}")
                continue
                
        logger.info(f"Collected {len(all_recommendations)} billing recommendations")
        return all_recommendations
    
    def save_recommendations_to_firestore(self, records: List[Dict[str, Any]], show_progress: bool = False):
        """
        Save recommendation records to Firestore in batches.
        
        Args:
            records: List of recommendation records to save
            show_progress: Whether to log progress for each batch
        """
        if not records:
            logger.debug("No records to save")
            return
        
        try:
            collection_ref = self.db.collection(self.collection_name)
            batch = self.db.batch()
            batch_count = 0
            total_saved = 0
            
            for record in records:
                # Use recommendation_id as document ID for idempotency
                doc_id = record['recommendation_id']
                doc_ref = collection_ref.document(doc_id)
                
                # Convert datetime objects to strings for Firestore
                firestore_record = record.copy()
                if 'last_refresh_time' in firestore_record and firestore_record['last_refresh_time']:
                    if isinstance(firestore_record['last_refresh_time'], str):
                        firestore_record['last_refresh_time'] = firestore_record['last_refresh_time']
                    else:
                        firestore_record['last_refresh_time'] = firestore_record['last_refresh_time'].isoformat()
                
                if 'collected_at' in firestore_record and firestore_record['collected_at']:
                    if isinstance(firestore_record['collected_at'], str):
                        firestore_record['collected_at'] = firestore_record['collected_at']
                    else:
                        firestore_record['collected_at'] = firestore_record['collected_at'].isoformat()
                
                if 'updated_at' in firestore_record and firestore_record['updated_at']:
                    if isinstance(firestore_record['updated_at'], str):
                        firestore_record['updated_at'] = firestore_record['updated_at']
                    else:
                        firestore_record['updated_at'] = firestore_record['updated_at'].isoformat()
                
                batch.set(doc_ref, firestore_record)
                batch_count += 1
                
                # Use configured batch size
                if batch_count >= self.batch_size:
                    batch.commit()
                    total_saved += batch_count
                    if show_progress:
                        logger.info(f"Committed batch of {batch_count} documents. Total: {total_saved}")
                    batch = self.db.batch()
                    batch_count = 0
            
            # Commit remaining records
            if batch_count > 0:
                batch.commit()
                total_saved += batch_count
            
            logger.info(f"Successfully saved {total_saved} recommendations to Firestore")
                
        except Exception as e:
            logger.error(f"Error saving to Firestore: {e}")
            raise
    
    def run(self, max_workers=None):
        """
        Main execution method to collect cost recommendations for all projects.
        Optimized for large-scale processing (100+ projects).
        
        Args:
            max_workers: Number of threads to use for parallel processing (defaults to config.MAX_WORKERS)
        """
        if max_workers is None:
            max_workers = self.max_workers
            
        logger.info("Starting cost recommendation collection")
        logger.info(f"Performance settings: {max_workers} workers, batch size {self.batch_size}")
        
        try:
            # Ensure Firestore collection is accessible
            self.ensure_firestore_collection()
            
            # 1. Process Billing Account Recommendations (if configured)
            if settings.billing_account_ids:
                logger.info(f"Processing {len(settings.billing_account_ids)} billing accounts")
                for billing_id in settings.billing_account_ids:
                    try:
                        logger.info(f"Processing billing account: {billing_id}")
                        billing_recs = self.get_recommendations_for_billing_account(billing_id)
                        if billing_recs:
                            self.save_recommendations_to_firestore(billing_recs, show_progress=False)
                            logger.info(f"Saved {len(billing_recs)} recommendations for billing account {billing_id}")
                    except Exception as e:
                        logger.error(f"Error processing billing account {billing_id}: {e}")
            else:
                logger.info("No billing accounts configured, skipping spend-based CUD recommendations")
            
            # 2. Process Project Recommendations
            # Get all projects
            projects = self.get_all_projects()
            
            if not projects:
                logger.warning("No projects found")
                return
            
            # For large-scale processing, save recommendations incrementally
            # instead of accumulating all in memory
            total_recommendations = 0
            lock = threading.Lock()
            project_batches = []
            
            def process_project(project_id):
                """Process a single project and save recommendations immediately."""
                logger.debug(f"Processing project: {project_id}")
                try:
                    recommendations = self.get_recommendations_for_project(project_id)
                    
                    # Save recommendations immediately if we have any
                    if recommendations:
                        with lock:
                            self.save_recommendations_to_firestore(recommendations, show_progress=False)
                            nonlocal total_recommendations
                            total_recommendations += len(recommendations)
                    
                    logger.info(f"Completed {project_id}: {len(recommendations)} recommendations")
                    return len(recommendations)
                except Exception as e:
                    logger.error(f"Error processing project {project_id}: {e}")
                    return 0
            
            # Process projects in parallel
            logger.info(f"Processing {len(projects)} projects with {max_workers} threads")
            start_time = datetime.utcnow()
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(process_project, project_id): project_id 
                          for project_id in projects}
                
                completed = 0
                for future in as_completed(futures):
                    completed += 1
                    project_id = futures[future]
                    try:
                        rec_count = future.result()
                        # Log progress every 10 projects for large batches
                        if completed % 10 == 0 or completed == len(projects):
                            elapsed = (datetime.utcnow() - start_time).total_seconds()
                            rate = completed / elapsed if elapsed > 0 else 0
                            eta = (len(projects) - completed) / rate if rate > 0 else 0
                            logger.info(
                                f"Progress: {completed}/{len(projects)} projects "
                                f"({completed*100//len(projects)}%) | "
                                f"Rate: {rate:.1f} projects/sec | "
                                f"ETA: {eta/60:.1f} min"
                            )
                    except Exception as e:
                        logger.error(f"Exception for project {project_id}: {e}")
            
            elapsed_time = (datetime.utcnow() - start_time).total_seconds()
            logger.info(
                f"Successfully collected and stored {total_recommendations} "
                f"cost recommendations from {len(projects)} projects "
                f"in {elapsed_time:.1f} seconds ({elapsed_time/60:.1f} minutes)"
            )
            
        except Exception as e:
            logger.error(f"Error in cost recommendation collection: {e}")
            raise


def main():
    """Main entry point for the Cloud Run job."""
    logger.info("=" * 80)
    logger.info("Starting GCP Cost Recommendation Collection Job")
    logger.info("=" * 80)
    
    try:
        collector = CostRecommendationCollector()
        collector.run()
        logger.info("Cost recommendation collection completed successfully")
        
    except Exception as e:
        logger.error(f"Job failed with error: {e}")
        raise


if __name__ == "__main__":
    main()
