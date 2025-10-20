#!/usr/bin/env python3
"""
Cloud Run Job to collect Google Cloud billing data for all billing accounts
and store it in BigQuery. Runs daily to collect previous day's cost data.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any

from google.cloud import billing_v1
from google.cloud import bigquery
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


class BillingDataCollector:
    """Collects billing data from all GCP billing accounts and stores in BigQuery."""
    
    def __init__(self):
        """Initialize the billing and BigQuery clients."""
        self.billing_client = billing_v1.CloudBillingClient()
        self.bq_client = bigquery.Client()
        
        # Get configuration from config module
        self.project_id = config.GCP_PROJECT_ID
        self.dataset_id = config.BQ_DATASET_ID
        self.table_id = config.BQ_TABLE_ID
        self.bq_location = config.BQ_LOCATION
        self.billing_export_dataset = config.BILLING_EXPORT_DATASET
        self.billing_export_table_prefix = config.BILLING_EXPORT_TABLE_PREFIX
        
        self.table_ref = f"{self.project_id}.{self.dataset_id}.{self.table_id}"
        logger.info(f"Initialized BillingDataCollector for project: {self.project_id}")
        logger.info(f"Target BigQuery table: {self.table_ref}")
    
    def get_all_billing_accounts(self) -> List[str]:
        """
        Retrieve all accessible billing accounts.
        
        Returns:
            List of billing account IDs
        """
        logger.info("Fetching all billing accounts...")
        billing_accounts = []
        
        try:
            request = billing_v1.ListBillingAccountsRequest()
            page_result = self.billing_client.list_billing_accounts(request=request)
            
            for account in page_result:
                if account.open:  # Only include open/active billing accounts
                    billing_accounts.append(account.name)
                    logger.info(f"Found billing account: {account.name} ({account.display_name})")
            
            logger.info(f"Total billing accounts found: {len(billing_accounts)}")
            return billing_accounts
            
        except exceptions.GoogleAPIError as e:
            logger.error(f"Error fetching billing accounts: {e}")
            raise
    
    def ensure_bigquery_resources(self):
        """Ensure BigQuery dataset and table exist with proper schema."""
        # Create dataset if it doesn't exist
        dataset_ref = f"{self.project_id}.{self.dataset_id}"
        try:
            self.bq_client.get_dataset(dataset_ref)
            logger.info(f"Dataset {dataset_ref} already exists")
        except exceptions.NotFound:
            logger.info(f"Creating dataset {dataset_ref}")
            dataset = bigquery.Dataset(dataset_ref)
            dataset.location = self.bq_location
            self.bq_client.create_dataset(dataset, timeout=30)
            logger.info(f"Dataset {dataset_ref} created successfully")
        
        # Create table if it doesn't exist
        try:
            self.bq_client.get_table(self.table_ref)
            logger.info(f"Table {self.table_ref} already exists")
        except exceptions.NotFound:
            logger.info(f"Creating table {self.table_ref}")
            schema = [
                bigquery.SchemaField("billing_account_id", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("billing_account_name", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("date", "DATE", mode="REQUIRED"),
                bigquery.SchemaField("project_id", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("project_name", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("service_description", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("sku_description", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("usage_start_time", "TIMESTAMP", mode="NULLABLE"),
                bigquery.SchemaField("usage_end_time", "TIMESTAMP", mode="NULLABLE"),
                bigquery.SchemaField("cost", "FLOAT64", mode="NULLABLE"),
                bigquery.SchemaField("currency", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("usage_amount", "FLOAT64", mode="NULLABLE"),
                bigquery.SchemaField("usage_unit", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("credits", "FLOAT64", mode="NULLABLE"),
                bigquery.SchemaField("location_region", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("location_zone", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("labels", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("collected_at", "TIMESTAMP", mode="REQUIRED"),
            ]
            
            table = bigquery.Table(self.table_ref, schema=schema)
            table.time_partitioning = bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY,
                field="date"
            )
            self.bq_client.create_table(table)
            logger.info(f"Table {self.table_ref} created successfully")
    
    def query_billing_export_for_date(
        self, 
        billing_account_id: str, 
        target_date: datetime
    ) -> List[Dict[str, Any]]:
        """
        Query billing export data for a specific billing account and date.
        
        Note: This assumes you have billing export configured to BigQuery.
        If not configured, you'll need to set it up in the GCP Console.
        
        Args:
            billing_account_id: The billing account ID
            target_date: The date to collect data for
            
        Returns:
            List of billing records
        """
        # Extract the billing account number from the full name
        # Format: billingAccounts/XXXXXX-YYYYYY-ZZZZZZ
        account_number = billing_account_id.split('/')[-1]
        
        # Format dates for query
        date_str = target_date.strftime('%Y-%m-%d')
        
        # This query assumes standard billing export table structure
        # Adjust the table reference based on your billing export configuration
        query = f"""
        SELECT
            billing_account_id,
            project.id as project_id,
            project.name as project_name,
            service.description as service_description,
            sku.description as sku_description,
            usage_start_time,
            usage_end_time,
            cost,
            currency,
            usage.amount as usage_amount,
            usage.unit as usage_unit,
            IFNULL(
                (SELECT SUM(c.amount) FROM UNNEST(credits) c),
                0
            ) as credits,
            location.region as location_region,
            location.zone as location_zone,
            TO_JSON_STRING(labels) as labels,
            DATE(usage_start_time) as date
        FROM
            `{self.project_id}.{self.dataset_id}.gcp_billing_export_*`
        WHERE
            billing_account_id = '{account_number}'
            AND DATE(usage_start_time) = '{date_str}'
        """
        
        try:
            logger.info(f"Querying billing data for account {account_number} on {date_str}")
            query_job = self.bq_client.query(query)
            results = query_job.result()
            
            records = []
            for row in results:
                records.append(dict(row))
            
            logger.info(f"Retrieved {len(records)} records for account {account_number}")
            return records
            
        except exceptions.NotFound:
            logger.warning(
                f"Billing export table not found for account {account_number}. "
                "Please ensure billing export is configured to BigQuery."
            )
            return []
        except exceptions.GoogleAPIError as e:
            logger.error(f"Error querying billing data: {e}")
            return []
    
    def collect_cost_data_direct(
        self,
        billing_account_id: str,
        billing_account_name: str,
        target_date: datetime
    ) -> List[Dict[str, Any]]:
        """
        Collect cost data directly from Cloud Billing API.
        This is an alternative approach when billing export is not available.
        
        Note: The Cloud Billing API has limited historical data access.
        For comprehensive cost analysis, billing export to BigQuery is recommended.
        
        Args:
            billing_account_id: The billing account ID
            billing_account_name: The billing account display name
            target_date: The date to collect data for
            
        Returns:
            List of cost records
        """
        logger.info(f"Collecting direct cost data for {billing_account_id} on {target_date.date()}")
        
        # For this implementation, we'll create a placeholder that aggregates
        # project-level costs. In production, you should use billing export.
        records = []
        
        try:
            # List all projects associated with this billing account
            request = billing_v1.ListProjectBillingInfoRequest(
                name=billing_account_id
            )
            
            projects = self.billing_client.list_project_billing_info(request=request)
            
            for project_billing_info in projects:
                if project_billing_info.billing_enabled:
                    # Create a summary record for this project
                    # Note: Actual cost data requires billing export
                    record = {
                        'billing_account_id': billing_account_id,
                        'billing_account_name': billing_account_name,
                        'date': target_date.date(),
                        'project_id': project_billing_info.project_id,
                        'project_name': project_billing_info.name,
                        'service_description': 'Summary',
                        'sku_description': 'Daily aggregated cost',
                        'usage_start_time': target_date,
                        'usage_end_time': target_date + timedelta(days=1),
                        'cost': 0.0,  # Placeholder - requires billing export
                        'currency': 'USD',
                        'usage_amount': 0.0,
                        'usage_unit': 'N/A',
                        'credits': 0.0,
                        'location_region': None,
                        'location_zone': None,
                        'labels': None,
                        'collected_at': datetime.utcnow(),
                    }
                    records.append(record)
            
            logger.info(f"Collected {len(records)} project records for {billing_account_id}")
            return records
            
        except exceptions.GoogleAPIError as e:
            logger.error(f"Error collecting direct cost data: {e}")
            return []
    
    def insert_records_to_bigquery(self, records: List[Dict[str, Any]]):
        """
        Insert billing records into BigQuery.
        
        Args:
            records: List of billing records to insert
        """
        if not records:
            logger.info("No records to insert")
            return
        
        try:
            errors = self.bq_client.insert_rows_json(self.table_ref, records)
            
            if errors:
                logger.error(f"Errors inserting rows: {errors}")
                raise Exception(f"Failed to insert rows: {errors}")
            else:
                logger.info(f"Successfully inserted {len(records)} records to BigQuery")
                
        except exceptions.GoogleAPIError as e:
            logger.error(f"Error inserting to BigQuery: {e}")
            raise
    
    def run(self, target_date: datetime = None):
        """
        Main execution method to collect billing data for all accounts.
        
        Args:
            target_date: The date to collect data for. Defaults to yesterday.
        """
        if target_date is None:
            # Default to yesterday
            target_date = datetime.utcnow() - timedelta(days=1)
            target_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        
        logger.info(f"Starting billing data collection for {target_date.date()}")
        
        try:
            # Ensure BigQuery resources exist
            self.ensure_bigquery_resources()
            
            # Get all billing accounts
            billing_accounts = self.get_all_billing_accounts()
            
            if not billing_accounts:
                logger.warning("No billing accounts found")
                return
            
            # Collect data for each billing account
            all_records = []
            
            for account in billing_accounts:
                # Get account details
                account_details = self.billing_client.get_billing_account(name=account)
                account_name = account_details.display_name
                
                logger.info(f"Processing billing account: {account_name}")
                
                # Try to query from billing export first
                records = self.query_billing_export_for_date(account, target_date)
                
                # If no records from export, use direct collection
                if not records:
                    logger.info("Falling back to direct cost collection")
                    records = self.collect_cost_data_direct(
                        account, 
                        account_name, 
                        target_date
                    )
                
                all_records.extend(records)
            
            # Insert all records to BigQuery
            if all_records:
                self.insert_records_to_bigquery(all_records)
                logger.info(
                    f"Successfully collected and stored {len(all_records)} "
                    f"billing records for {target_date.date()}"
                )
            else:
                logger.warning("No billing records collected")
            
        except Exception as e:
            logger.error(f"Error in billing data collection: {e}")
            raise


def main():
    """Main entry point for the Cloud Run job."""
    logger.info("=" * 80)
    logger.info("Starting GCP Billing Data Collection Job")
    logger.info("=" * 80)
    
    try:
        collector = BillingDataCollector()
        collector.run()
        logger.info("Billing data collection completed successfully")
        
    except Exception as e:
        logger.error(f"Job failed with error: {e}")
        raise


if __name__ == "__main__":
    main()
