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

from google.cloud import recommender_v1
from google.cloud import firestore
from google.cloud import resourcemanager_v3
from google.api_core import exceptions

# Import configuration
import config

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Log configuration on startup
logger.info(f"Starting with environment: {config.ENVIRONMENT}")
logger.debug(f"Configuration: {config.CONFIG}")


class CostRecommendationCollector:
    """Collects cost recommendations from all GCP projects and stores in Firestore."""
    
    def __init__(self):
        """Initialize the recommender and Firestore clients."""
        self.recommender_client = recommender_v1.RecommenderClient()
        self.db = firestore.Client(project=config.GCP_PROJECT_ID, database=config.FIRESTORE_DATABASE)
        self.projects_client = resourcemanager_v3.ProjectsClient()
        
        # Get configuration from config module
        self.project_id = config.GCP_PROJECT_ID
        self.collection_name = config.FIRESTORE_COLLECTION
        self.recommender_types = [r.strip() for r in config.RECOMMENDER_TYPES]
        self.state_filter = config.RECOMMENDATION_STATE_FILTER
        
        logger.info(f"Initialized CostRecommendationCollector for project: {self.project_id}")
        logger.info(f"Target Firestore collection: {self.collection_name}")
        logger.info(f"Recommender types: {self.recommender_types}")
    
    def get_all_projects(self) -> List[str]:
        """
        Retrieve all accessible GCP projects based on scope configuration.
        Supports project, folder, and organization level collection.
        
        Returns:
            List of project IDs
        """
        scope_type = config.SCOPE_TYPE
        scope_id = config.SCOPE_ID
        
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
                
            elif scope_type == 'organization':
                # Organization mode - get all projects under the organization
                logger.info(f"Running in organization mode for: {scope_id}")
                # Ensure org ID is in correct format
                if not scope_id.startswith('organizations/'):
                    scope_id = f"organizations/{scope_id}"
                
                request = resourcemanager_v3.ListProjectsRequest(
                    parent=scope_id
                )
                page_result = self.projects_client.list_projects(request=request)
                
                for project in page_result:
                    if project.state == resourcemanager_v3.Project.State.ACTIVE:
                        project_id = project.name.split('/')[-1]
                        projects.append(project_id)
                        logger.info(f"Found project in organization: {project_id} ({project.display_name})")
            
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
            'google.compute.commitment.UsageCommitmentRecommender',
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
        ]
        
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
        
        # Get recommendations for specified locations
        # Focus on Singapore, India, and Indonesia regions
        locations = [
            'global',  # Global recommendations apply to all regions
            # Singapore
            'asia-southeast1',  # Singapore
        ]
        
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
                    
                    for recommendation in recommendations:
                        record = self._parse_recommendation(
                            recommendation, 
                            project_id, 
                            project_number,
                            location,
                            recommender_type
                        )
                        all_recommendations.append(record)
                        
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
    
    def save_recommendations_to_firestore(self, records: List[Dict[str, Any]]):
        """
        Save recommendation records to Firestore.
        
        Args:
            records: List of recommendation records to save
        """
        if not records:
            logger.info("No records to save")
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
                
                # Firestore batch limit is 500 operations
                if batch_count >= 500:
                    batch.commit()
                    total_saved += batch_count
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
    
    def run(self):
        """
        Main execution method to collect cost recommendations for all projects.
        """
        logger.info("Starting cost recommendation collection")
        
        try:
            # Ensure Firestore collection is accessible
            self.ensure_firestore_collection()
            
            # Get all projects
            projects = self.get_all_projects()
            
            if not projects:
                logger.warning("No projects found")
                return
            
            # Collect recommendations for each project
            all_recommendations = []
            
            for project_id in projects:
                logger.info(f"Processing project: {project_id}")
                
                try:
                    recommendations = self.get_recommendations_for_project(project_id)
                    all_recommendations.extend(recommendations)
                except Exception as e:
                    logger.error(f"Error processing project {project_id}: {e}")
                    continue
            
            # Save all recommendations to Firestore
            if all_recommendations:
                self.save_recommendations_to_firestore(all_recommendations)
                logger.info(
                    f"Successfully collected and stored {len(all_recommendations)} "
                    f"cost recommendations"
                )
            else:
                logger.warning("No cost recommendations collected")
            
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
