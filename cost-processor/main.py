#!/usr/bin/env python3
"""
Cloud Run Job to process billing data from BigQuery and generate cost reports
by project ID and services. Creates aggregated views and summary tables.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from google.cloud import bigquery
from google.cloud import firestore
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


class CostProcessor:
    """Processes billing data and generates cost reports by project and service."""
    
    def __init__(self):
        """Initialize the BigQuery and Firestore clients and configuration."""
        self.bq_client = bigquery.Client()
        self.firestore_client = firestore.Client(
            project=config.FIRESTORE_PROJECT_ID,
            database=config.FIRESTORE_DATABASE
        )
        
        # Get configuration from config module
        self.project_id = config.GCP_PROJECT_ID
        self.source_dataset_id = config.SOURCE_DATASET_ID
        self.source_table_id = config.SOURCE_TABLE_ID
        self.output_dataset_id = config.OUTPUT_DATASET_ID
        self.bq_location = config.BQ_LOCATION
        self.firestore_collection_prefix = config.FIRESTORE_COLLECTION_PREFIX
        
        self.source_table_ref = f"{self.project_id}.{self.source_dataset_id}.{self.source_table_id}"
        logger.info(f"Initialized CostProcessor for project: {self.project_id}")
        logger.info(f"Source table: {self.source_table_ref}")
        logger.info(f"Output dataset: {self.project_id}.{self.output_dataset_id}")
        logger.info(f"Firestore: {config.FIRESTORE_PROJECT_ID}/{config.FIRESTORE_DATABASE}")
    
    def ensure_output_dataset(self):
        """Ensure the output dataset exists."""
        dataset_ref = f"{self.project_id}.{self.output_dataset_id}"
        try:
            self.bq_client.get_dataset(dataset_ref)
            logger.info(f"Output dataset {dataset_ref} already exists")
        except exceptions.NotFound:
            logger.info(f"Creating output dataset {dataset_ref}")
            dataset = bigquery.Dataset(dataset_ref)
            dataset.location = self.bq_location
            dataset.description = "Processed billing reports and cost summaries"
            self.bq_client.create_dataset(dataset, timeout=30)
            logger.info(f"Output dataset {dataset_ref} created successfully")
    
    def create_project_service_daily_report(self, days_back: int = 30):
        """
        Create a report of daily costs by project and service.
        
        Args:
            days_back: Number of days to include in the report
        """
        table_ref = f"{self.project_id}.{self.output_dataset_id}.project_service_daily_costs"
        logger.info(f"Creating project-service daily cost report: {table_ref}")
        
        query = f"""
        CREATE OR REPLACE TABLE `{table_ref}` AS
        SELECT
            date,
            billing_account_id,
            billing_account_name,
            project_id,
            project_name,
            service_description,
            SUM(cost) as total_cost,
            SUM(credits) as total_credits,
            SUM(cost) + SUM(credits) as net_cost,
            currency,
            SUM(usage_amount) as total_usage_amount,
            usage_unit,
            COUNT(*) as line_item_count,
            MAX(collected_at) as last_updated
        FROM
            `{self.source_table_ref}`
        WHERE
            date >= DATE_SUB(CURRENT_DATE(), INTERVAL {days_back} DAY)
            AND cost IS NOT NULL
        GROUP BY
            date,
            billing_account_id,
            billing_account_name,
            project_id,
            project_name,
            service_description,
            currency,
            usage_unit
        ORDER BY
            date DESC,
            total_cost DESC
        """
        
        try:
            query_job = self.bq_client.query(query)
            query_job.result()
            logger.info(f"Successfully created project-service daily cost report")
            
            # Add table description
            table = self.bq_client.get_table(table_ref)
            table.description = f"Daily costs aggregated by project and service (last {days_back} days)"
            self.bq_client.update_table(table, ["description"])
            
        except exceptions.GoogleAPIError as e:
            logger.error(f"Error creating project-service daily report: {e}")
            raise
    
    def create_project_summary_report(self, days_back: int = 30):
        """
        Create a summary report of total costs by project.
        
        Args:
            days_back: Number of days to include in the report
        """
        table_ref = f"{self.project_id}.{self.output_dataset_id}.project_cost_summary"
        logger.info(f"Creating project cost summary report: {table_ref}")
        
        query = f"""
        CREATE OR REPLACE TABLE `{table_ref}` AS
        SELECT
            project_id,
            project_name,
            billing_account_id,
            billing_account_name,
            MIN(date) as first_cost_date,
            MAX(date) as last_cost_date,
            COUNT(DISTINCT date) as days_with_costs,
            SUM(cost) as total_cost,
            SUM(credits) as total_credits,
            SUM(cost) + SUM(credits) as net_cost,
            AVG(cost) as avg_daily_cost,
            currency,
            COUNT(DISTINCT service_description) as service_count,
            ARRAY_AGG(DISTINCT service_description IGNORE NULLS ORDER BY service_description) as services_used,
            MAX(collected_at) as last_updated
        FROM
            `{self.source_table_ref}`
        WHERE
            date >= DATE_SUB(CURRENT_DATE(), INTERVAL {days_back} DAY)
            AND cost IS NOT NULL
            AND project_id IS NOT NULL
        GROUP BY
            project_id,
            project_name,
            billing_account_id,
            billing_account_name,
            currency
        ORDER BY
            total_cost DESC
        """
        
        try:
            query_job = self.bq_client.query(query)
            query_job.result()
            logger.info(f"Successfully created project cost summary report")
            
            # Add table description
            table = self.bq_client.get_table(table_ref)
            table.description = f"Total costs by project (last {days_back} days)"
            self.bq_client.update_table(table, ["description"])
            
        except exceptions.GoogleAPIError as e:
            logger.error(f"Error creating project summary report: {e}")
            raise
    
    def create_service_summary_report(self, days_back: int = 30):
        """
        Create a summary report of costs by service across all projects.
        
        Args:
            days_back: Number of days to include in the report
        """
        table_ref = f"{self.project_id}.{self.output_dataset_id}.service_cost_summary"
        logger.info(f"Creating service cost summary report: {table_ref}")
        
        query = f"""
        CREATE OR REPLACE TABLE `{table_ref}` AS
        SELECT
            service_description,
            COUNT(DISTINCT project_id) as project_count,
            COUNT(DISTINCT billing_account_id) as billing_account_count,
            MIN(date) as first_cost_date,
            MAX(date) as last_cost_date,
            SUM(cost) as total_cost,
            SUM(credits) as total_credits,
            SUM(cost) + SUM(credits) as net_cost,
            AVG(cost) as avg_daily_cost,
            currency,
            SUM(usage_amount) as total_usage_amount,
            usage_unit,
            MAX(collected_at) as last_updated
        FROM
            `{self.source_table_ref}`
        WHERE
            date >= DATE_SUB(CURRENT_DATE(), INTERVAL {days_back} DAY)
            AND cost IS NOT NULL
            AND service_description IS NOT NULL
        GROUP BY
            service_description,
            currency,
            usage_unit
        ORDER BY
            total_cost DESC
        """
        
        try:
            query_job = self.bq_client.query(query)
            query_job.result()
            logger.info(f"Successfully created service cost summary report")
            
            # Add table description
            table = self.bq_client.get_table(table_ref)
            table.description = f"Total costs by service across all projects (last {days_back} days)"
            self.bq_client.update_table(table, ["description"])
            
        except exceptions.GoogleAPIError as e:
            logger.error(f"Error creating service summary report: {e}")
            raise
    
    def create_project_service_summary_report(self, days_back: int = 30):
        """
        Create a detailed summary of costs by project and service.
        
        Args:
            days_back: Number of days to include in the report
        """
        table_ref = f"{self.project_id}.{self.output_dataset_id}.project_service_cost_summary"
        logger.info(f"Creating project-service cost summary report: {table_ref}")
        
        query = f"""
        CREATE OR REPLACE TABLE `{table_ref}` AS
        SELECT
            project_id,
            project_name,
            service_description,
            billing_account_id,
            billing_account_name,
            MIN(date) as first_cost_date,
            MAX(date) as last_cost_date,
            COUNT(DISTINCT date) as days_with_costs,
            SUM(cost) as total_cost,
            SUM(credits) as total_credits,
            SUM(cost) + SUM(credits) as net_cost,
            AVG(cost) as avg_daily_cost,
            currency,
            SUM(usage_amount) as total_usage_amount,
            usage_unit,
            COUNT(DISTINCT sku_description) as sku_count,
            MAX(collected_at) as last_updated,
            -- Calculate percentage of project's total cost
            SUM(cost) / SUM(SUM(cost)) OVER (PARTITION BY project_id) * 100 as pct_of_project_cost
        FROM
            `{self.source_table_ref}`
        WHERE
            date >= DATE_SUB(CURRENT_DATE(), INTERVAL {days_back} DAY)
            AND cost IS NOT NULL
            AND project_id IS NOT NULL
            AND service_description IS NOT NULL
        GROUP BY
            project_id,
            project_name,
            service_description,
            billing_account_id,
            billing_account_name,
            currency,
            usage_unit
        ORDER BY
            project_id,
            total_cost DESC
        """
        
        try:
            query_job = self.bq_client.query(query)
            query_job.result()
            logger.info(f"Successfully created project-service cost summary report")
            
            # Add table description
            table = self.bq_client.get_table(table_ref)
            table.description = f"Costs by project and service with percentage breakdown (last {days_back} days)"
            self.bq_client.update_table(table, ["description"])
            
        except exceptions.GoogleAPIError as e:
            logger.error(f"Error creating project-service summary report: {e}")
            raise
    
    def create_daily_trend_report(self, days_back: int = 30):
        """
        Create a daily cost trend report for monitoring.
        
        Args:
            days_back: Number of days to include in the report
        """
        table_ref = f"{self.project_id}.{self.output_dataset_id}.daily_cost_trends"
        logger.info(f"Creating daily cost trend report: {table_ref}")
        
        query = f"""
        CREATE OR REPLACE TABLE `{table_ref}` AS
        SELECT
            date,
            COUNT(DISTINCT project_id) as active_projects,
            COUNT(DISTINCT service_description) as services_used,
            COUNT(DISTINCT billing_account_id) as billing_accounts,
            SUM(cost) as total_cost,
            SUM(credits) as total_credits,
            SUM(cost) + SUM(credits) as net_cost,
            currency,
            COUNT(*) as line_items,
            MAX(collected_at) as last_updated,
            -- 7-day moving average
            AVG(SUM(cost)) OVER (
                ORDER BY date
                ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
            ) as cost_7day_avg,
            -- Day-over-day change
            SUM(cost) - LAG(SUM(cost)) OVER (ORDER BY date) as cost_change_from_prev_day,
            -- Percentage change
            SAFE_DIVIDE(
                SUM(cost) - LAG(SUM(cost)) OVER (ORDER BY date),
                LAG(SUM(cost)) OVER (ORDER BY date)
            ) * 100 as cost_pct_change_from_prev_day
        FROM
            `{self.source_table_ref}`
        WHERE
            date >= DATE_SUB(CURRENT_DATE(), INTERVAL {days_back} DAY)
            AND cost IS NOT NULL
        GROUP BY
            date,
            currency
        ORDER BY
            date DESC
        """
        
        try:
            query_job = self.bq_client.query(query)
            query_job.result()
            logger.info(f"Successfully created daily cost trend report")
            
            # Add table description
            table = self.bq_client.get_table(table_ref)
            table.description = f"Daily cost trends with moving averages and day-over-day changes (last {days_back} days)"
            self.bq_client.update_table(table, ["description"])
            
        except exceptions.GoogleAPIError as e:
            logger.error(f"Error creating daily trend report: {e}")
            raise
    
    def create_top_cost_drivers_report(self, days_back: int = 7, top_n: int = 20):
        """
        Create a report of top cost drivers (SKUs) across all projects.
        
        Args:
            days_back: Number of days to include in the report
            top_n: Number of top items to include
        """
        table_ref = f"{self.project_id}.{self.output_dataset_id}.top_cost_drivers"
        logger.info(f"Creating top cost drivers report: {table_ref}")
        
        query = f"""
        CREATE OR REPLACE TABLE `{table_ref}` AS
        SELECT
            service_description,
            sku_description,
            COUNT(DISTINCT project_id) as project_count,
            SUM(cost) as total_cost,
            SUM(credits) as total_credits,
            SUM(cost) + SUM(credits) as net_cost,
            AVG(cost) as avg_cost,
            currency,
            SUM(usage_amount) as total_usage,
            usage_unit,
            ARRAY_AGG(DISTINCT project_id IGNORE NULLS LIMIT 10) as top_projects,
            MAX(collected_at) as last_updated
        FROM
            `{self.source_table_ref}`
        WHERE
            date >= DATE_SUB(CURRENT_DATE(), INTERVAL {days_back} DAY)
            AND cost IS NOT NULL
            AND sku_description IS NOT NULL
        GROUP BY
            service_description,
            sku_description,
            currency,
            usage_unit
        ORDER BY
            total_cost DESC
        LIMIT {top_n}
        """
        
        try:
            query_job = self.bq_client.query(query)
            query_job.result()
            logger.info(f"Successfully created top cost drivers report")
            
            # Add table description
            table = self.bq_client.get_table(table_ref)
            table.description = f"Top {top_n} cost drivers by SKU (last {days_back} days)"
            self.bq_client.update_table(table, ["description"])
            
        except exceptions.GoogleAPIError as e:
            logger.error(f"Error creating top cost drivers report: {e}")
            raise
    
    def create_location_cost_report(self, days_back: int = 30):
        """
        Create a report of costs by location (region/zone).
        
        Args:
            days_back: Number of days to include in the report
        """
        table_ref = f"{self.project_id}.{self.output_dataset_id}.location_cost_summary"
        logger.info(f"Creating location cost summary report: {table_ref}")
        
        query = f"""
        CREATE OR REPLACE TABLE `{table_ref}` AS
        SELECT
            COALESCE(location_region, 'global') as region,
            location_zone,
            COUNT(DISTINCT project_id) as project_count,
            COUNT(DISTINCT service_description) as service_count,
            SUM(cost) as total_cost,
            SUM(credits) as total_credits,
            SUM(cost) + SUM(credits) as net_cost,
            currency,
            MAX(collected_at) as last_updated
        FROM
            `{self.source_table_ref}`
        WHERE
            date >= DATE_SUB(CURRENT_DATE(), INTERVAL {days_back} DAY)
            AND cost IS NOT NULL
        GROUP BY
            location_region,
            location_zone,
            currency
        ORDER BY
            total_cost DESC
        """
        
        try:
            query_job = self.bq_client.query(query)
            query_job.result()
            logger.info(f"Successfully created location cost summary report")
            
            # Add table description
            table = self.bq_client.get_table(table_ref)
            table.description = f"Costs by geographic location (last {days_back} days)"
            self.bq_client.update_table(table, ["description"])
            
        except exceptions.GoogleAPIError as e:
            logger.error(f"Error creating location cost report: {e}")
            raise
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the processed data.
        
        Returns:
            Dictionary with processing statistics
        """
        query = f"""
        SELECT
            COUNT(*) as total_records,
            COUNT(DISTINCT date) as unique_dates,
            COUNT(DISTINCT project_id) as unique_projects,
            COUNT(DISTINCT billing_account_id) as unique_billing_accounts,
            COUNT(DISTINCT service_description) as unique_services,
            MIN(date) as earliest_date,
            MAX(date) as latest_date,
            SUM(cost) as total_cost,
            MAX(collected_at) as last_collection_time
        FROM
            `{self.source_table_ref}`
        WHERE
            cost IS NOT NULL
        """
        
        try:
            query_job = self.bq_client.query(query)
            results = query_job.result()
            
            for row in results:
                stats = dict(row)
                logger.info("Processing Statistics:")
                logger.info(f"  Total records: {stats.get('total_records', 0):,}")
                logger.info(f"  Date range: {stats.get('earliest_date')} to {stats.get('latest_date')}")
                logger.info(f"  Unique projects: {stats.get('unique_projects', 0)}")
                logger.info(f"  Unique services: {stats.get('unique_services', 0)}")
                logger.info(f"  Total cost: ${stats.get('total_cost', 0):,.2f}")
                return stats
            
        except exceptions.GoogleAPIError as e:
            logger.error(f"Error getting processing stats: {e}")
            return {}
    
    def save_report_to_firestore(self, report_name: str, query: str) -> Dict[str, Any]:
        """
        Execute a query and save results to Firestore.
        
        Args:
            report_name: Name of the report (used as collection name)
            query: BigQuery SQL query to execute
            
        Returns:
            Dictionary with save statistics
        """
        collection_name = f"{self.firestore_collection_prefix}_{report_name}"
        logger.info(f"Saving {report_name} to Firestore collection: {collection_name}")
        
        try:
            # Execute query
            query_job = self.bq_client.query(query)
            results = query_job.result()
            
            # Get collection reference
            collection_ref = self.firestore_client.collection(collection_name)
            
            # Batch write to Firestore
            batch = self.firestore_client.batch()
            batch_count = 0
            total_count = 0
            
            for row in results:
                # Convert row to dictionary
                doc_data = dict(row)
                
                # Convert datetime/date objects to strings for Firestore
                for key, value in doc_data.items():
                    if isinstance(value, (datetime, )):
                        doc_data[key] = value.isoformat()
                    elif hasattr(value, 'isoformat'):  # date objects
                        doc_data[key] = value.isoformat()
                    elif value is None:
                        doc_data[key] = None
                
                # Create document ID based on report type
                doc_id = self._generate_document_id(report_name, doc_data)
                
                # Add to batch
                doc_ref = collection_ref.document(doc_id)
                batch.set(doc_ref, doc_data)
                batch_count += 1
                total_count += 1
                
                # Commit batch every 500 documents (Firestore limit)
                if batch_count >= 500:
                    batch.commit()
                    logger.debug(f"Committed batch of {batch_count} documents")
                    batch = self.firestore_client.batch()
                    batch_count = 0
            
            # Commit remaining documents
            if batch_count > 0:
                batch.commit()
                logger.debug(f"Committed final batch of {batch_count} documents")
            
            logger.info(f"Saved {total_count} documents to {collection_name}")
            
            # Save metadata
            metadata = {
                'report_name': report_name,
                'collection_name': collection_name,
                'document_count': total_count,
                'last_updated': datetime.utcnow().isoformat(),
                'environment': config.ENVIRONMENT,
            }
            
            metadata_ref = self.firestore_client.collection('cost_reports_metadata').document(report_name)
            metadata_ref.set(metadata)
            
            return metadata
            
        except exceptions.GoogleAPIError as e:
            logger.error(f"Error saving {report_name} to Firestore: {e}")
            raise
    
    def _generate_document_id(self, report_name: str, doc_data: Dict[str, Any]) -> str:
        """
        Generate a unique document ID based on report type and data.
        
        Args:
            report_name: Name of the report
            doc_data: Document data
            
        Returns:
            Document ID string
        """
        if report_name == 'project_cost_summary':
            return f"{doc_data.get('project_id', 'unknown')}"
        elif report_name == 'service_cost_summary':
            service = doc_data.get('service_description', 'unknown').replace('/', '_')
            return f"{service}"
        elif report_name == 'project_service_cost_summary':
            project = doc_data.get('project_id', 'unknown')
            service = doc_data.get('service_description', 'unknown').replace('/', '_')
            return f"{project}_{service}"
        elif report_name == 'daily_cost_trends':
            date = doc_data.get('date', 'unknown')
            return f"{date}"
        elif report_name == 'top_cost_drivers':
            service = doc_data.get('service_description', 'unknown').replace('/', '_')
            sku = doc_data.get('sku_description', 'unknown').replace('/', '_')[:50]
            return f"{service}_{sku}"
        elif report_name == 'location_cost_summary':
            region = doc_data.get('region', 'unknown')
            zone = doc_data.get('location_zone', 'none')
            return f"{region}_{zone}"
        else:
            # Default: use timestamp-based ID
            return f"{datetime.utcnow().timestamp()}"
    
    def get_report_query(self, report_name: str, days_back: int) -> str:
        """
        Get the query for a specific report.
        
        Args:
            report_name: Name of the report
            days_back: Number of days to include
            
        Returns:
            SQL query string
        """
        if report_name == 'project_cost_summary':
            return f"""
            SELECT
                project_id,
                project_name,
                billing_account_id,
                billing_account_name,
                MIN(date) as first_cost_date,
                MAX(date) as last_cost_date,
                COUNT(DISTINCT date) as days_with_costs,
                SUM(cost) as total_cost,
                SUM(credits) as total_credits,
                SUM(cost) + SUM(credits) as net_cost,
                AVG(cost) as avg_daily_cost,
                currency,
                COUNT(DISTINCT service_description) as service_count,
                MAX(collected_at) as last_updated
            FROM `{self.source_table_ref}`
            WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL {days_back} DAY)
                AND cost IS NOT NULL
                AND project_id IS NOT NULL
            GROUP BY project_id, project_name, billing_account_id, billing_account_name, currency
            ORDER BY total_cost DESC
            """
        elif report_name == 'service_cost_summary':
            return f"""
            SELECT
                service_description,
                COUNT(DISTINCT project_id) as project_count,
                SUM(cost) as total_cost,
                SUM(credits) as total_credits,
                SUM(cost) + SUM(credits) as net_cost,
                currency,
                MAX(collected_at) as last_updated
            FROM `{self.source_table_ref}`
            WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL {days_back} DAY)
                AND cost IS NOT NULL
                AND service_description IS NOT NULL
            GROUP BY service_description, currency
            ORDER BY total_cost DESC
            """
        elif report_name == 'project_service_cost_summary':
            return f"""
            SELECT
                project_id,
                project_name,
                service_description,
                SUM(cost) as total_cost,
                SUM(credits) as total_credits,
                SUM(cost) + SUM(credits) as net_cost,
                currency,
                MAX(collected_at) as last_updated,
                SUM(cost) / SUM(SUM(cost)) OVER (PARTITION BY project_id) * 100 as pct_of_project_cost
            FROM `{self.source_table_ref}`
            WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL {days_back} DAY)
                AND cost IS NOT NULL
                AND project_id IS NOT NULL
                AND service_description IS NOT NULL
            GROUP BY project_id, project_name, service_description, currency
            ORDER BY project_id, total_cost DESC
            """
        elif report_name == 'daily_cost_trends':
            return f"""
            SELECT
                date,
                COUNT(DISTINCT project_id) as active_projects,
                SUM(cost) as total_cost,
                SUM(credits) as total_credits,
                SUM(cost) + SUM(credits) as net_cost,
                currency,
                MAX(collected_at) as last_updated
            FROM `{self.source_table_ref}`
            WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL {days_back} DAY)
                AND cost IS NOT NULL
            GROUP BY date, currency
            ORDER BY date DESC
            """
        elif report_name == 'top_cost_drivers':
            return f"""
            SELECT
                service_description,
                sku_description,
                COUNT(DISTINCT project_id) as project_count,
                SUM(cost) as total_cost,
                SUM(credits) as total_credits,
                currency,
                MAX(collected_at) as last_updated
            FROM `{self.source_table_ref}`
            WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL {config.TOP_COST_DRIVERS_DAYS} DAY)
                AND cost IS NOT NULL
                AND sku_description IS NOT NULL
            GROUP BY service_description, sku_description, currency
            ORDER BY total_cost DESC
            LIMIT {config.TOP_COST_DRIVERS_COUNT}
            """
        elif report_name == 'location_cost_summary':
            return f"""
            SELECT
                COALESCE(location_region, 'global') as region,
                location_zone,
                COUNT(DISTINCT project_id) as project_count,
                SUM(cost) as total_cost,
                SUM(credits) as total_credits,
                currency,
                MAX(collected_at) as last_updated
            FROM `{self.source_table_ref}`
            WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL {days_back} DAY)
                AND cost IS NOT NULL
            GROUP BY location_region, location_zone, currency
            ORDER BY total_cost DESC
            """
        else:
            raise ValueError(f"Unknown report name: {report_name}")
    
    def run(self, days_back: int = 30):
        """
        Main execution method to process billing data and create reports.
        
        Args:
            days_back: Number of days to include in reports (default: 30)
        """
        logger.info(f"Starting cost data processing for last {days_back} days")
        
        try:
            # Ensure output dataset exists
            self.ensure_output_dataset()
            
            # Get and log processing statistics
            stats = self.get_processing_stats()
            
            if not stats or stats.get('total_records', 0) == 0:
                logger.warning("No billing data found to process")
                return
            
            # Create all BigQuery reports
            logger.info("Creating BigQuery cost reports...")
            
            self.create_project_service_daily_report(days_back)
            self.create_project_summary_report(days_back)
            self.create_service_summary_report(days_back)
            self.create_project_service_summary_report(days_back)
            self.create_daily_trend_report(days_back)
            self.create_top_cost_drivers_report(days_back=config.TOP_COST_DRIVERS_DAYS, top_n=config.TOP_COST_DRIVERS_COUNT)
            self.create_location_cost_report(days_back)
            
            logger.info("BigQuery reports created successfully")
            
            # Save key reports to Firestore
            logger.info("=" * 80)
            logger.info("Saving reports to Firestore...")
            logger.info("=" * 80)
            
            reports_to_save = [
                'project_cost_summary',
                'service_cost_summary',
                'project_service_cost_summary',
                'daily_cost_trends',
                'top_cost_drivers',
                'location_cost_summary',
            ]
            
            firestore_stats = []
            for report_name in reports_to_save:
                try:
                    query = self.get_report_query(report_name, days_back)
                    metadata = self.save_report_to_firestore(report_name, query)
                    firestore_stats.append(metadata)
                except Exception as e:
                    logger.error(f"Failed to save {report_name} to Firestore: {e}")
            
            logger.info("=" * 80)
            logger.info("Cost processing completed successfully!")
            logger.info("=" * 80)
            logger.info("Generated BigQuery Reports:")
            logger.info(f"  1. project_service_daily_costs - Daily costs by project and service")
            logger.info(f"  2. project_cost_summary - Total costs by project")
            logger.info(f"  3. service_cost_summary - Total costs by service")
            logger.info(f"  4. project_service_cost_summary - Detailed project-service breakdown")
            logger.info(f"  5. daily_cost_trends - Daily trends with moving averages")
            logger.info(f"  6. top_cost_drivers - Top {config.TOP_COST_DRIVERS_COUNT} cost drivers by SKU")
            logger.info(f"  7. location_cost_summary - Costs by geographic location")
            logger.info("")
            logger.info("Firestore Collections:")
            for stat in firestore_stats:
                logger.info(f"  - {stat['collection_name']}: {stat['document_count']} documents")
            logger.info("=" * 80)
            
        except Exception as e:
            logger.error(f"Error in cost data processing: {e}")
            raise


def main():
    """Main entry point for the Cloud Run job."""
    logger.info("=" * 80)
    logger.info("Starting GCP Cost Data Processing Job")
    logger.info("=" * 80)
    
    try:
        # Get days_back from config
        days_back = config.DAYS_BACK
        
        processor = CostProcessor()
        processor.run(days_back=days_back)
        logger.info("Cost processing job completed successfully")
        
    except Exception as e:
        logger.error(f"Job failed with error: {e}")
        raise


if __name__ == "__main__":
    main()
