#!/usr/bin/env python3
"""
Cost BigQuery Processor
Fetches cost data from BigQuery billing export and stores in Firestore with enrichment.
"""

import logging
import sys
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from collections import defaultdict

from google.cloud import bigquery
from google.cloud import firestore
from google.cloud import billing_v1
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


class CostBigQueryProcessor:
    """Processes cost data from BigQuery and stores in Firestore."""
    
    def __init__(self):
        """Initialize BigQuery, Firestore, and Billing clients."""
        self.bq_client = bigquery.Client(project=config.GCP_PROJECT_ID)
        self.billing_client = billing_v1.CloudBillingClient()
        
        # Firestore clients
        self.firestore_client = firestore.Client(
            project=config.GCP_PROJECT_ID,
            database=config.FIRESTORE_DATABASE
        )
        
        self.enrichment_client = firestore.Client(
            project=config.GCP_PROJECT_ID,
            database=config.ENRICHMENT_DATABASE
        )
        
        self.billing_account_ids = config.BILLING_ACCOUNT_LIST
        
        logger.info(f"Initialized CostBigQueryProcessor for project: {config.GCP_PROJECT_ID}")
        logger.info(f"BigQuery dataset: {config.BILLING_DATASET}")
        logger.info(f"Firestore database: {config.FIRESTORE_DATABASE}")
        logger.info(f"Days back: {config.DAYS_BACK}")
    
    def get_billing_accounts(self) -> List[str]:
        """
        Get list of billing accounts to process.
        
        Returns:
            List of billing account IDs
        """
        if self.billing_account_ids:
            logger.info(f"Using configured billing accounts: {self.billing_account_ids}")
            return self.billing_account_ids
        
        logger.info("Discovering billing accounts...")
        try:
            request = billing_v1.ListBillingAccountsRequest()
            page_result = self.billing_client.list_billing_accounts(request=request)
            
            accounts = []
            for account in page_result:
                if account.open:
                    account_id = account.name.split('/')[-1]
                    accounts.append(account_id)
                    logger.info(f"Found billing account: {account_id} ({account.display_name})")
            
            if not accounts:
                logger.warning("No open billing accounts found")
            
            return accounts
            
        except exceptions.GoogleAPIError as e:
            logger.error(f"Error listing billing accounts: {e}")
            raise
    
    def get_date_range(self) -> tuple[str, str]:
        """
        Get date range for cost data query.
        
        Returns:
            Tuple of (start_date, end_date) in YYYY-MM-DD format
        """
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=config.DAYS_BACK)
        
        logger.info(f"Date range: {start_date} to {end_date} ({config.DAYS_BACK} days)")
        return str(start_date), str(end_date)
    
    def fetch_daily_costs(
        self, 
        billing_account_id: str, 
        start_date: str, 
        end_date: str
    ) -> List[Dict[str, Any]]:
        """
        Fetch daily cost data from BigQuery.
        
        Args:
            billing_account_id: Billing account ID
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            
        Returns:
            List of daily cost records
        """
        logger.info(f"Fetching costs for {billing_account_id} from {start_date} to {end_date}")
        
        try:
            # Build table name
            table_suffix = billing_account_id.replace('-', '_')
            table_name = f"{config.BILLING_TABLE_PREFIX}_{table_suffix}"
            full_table_name = f"{config.GCP_PROJECT_ID}.{config.BILLING_DATASET}.{table_name}"
            
            # Build query based on aggregation level
            query = self._build_cost_query(full_table_name, start_date, end_date)
            
            # Execute query
            logger.debug(f"Executing query on: {full_table_name}")
            query_job = self.bq_client.query(query)
            results = query_job.result()
            
            # Parse results
            cost_records = []
            for row in results:
                record = {
                    'billing_account_id': billing_account_id,
                    'date': row.date.isoformat() if hasattr(row.date, 'isoformat') else str(row.date),
                    'project_id': row.project_id,
                    'project_name': row.project_name,
                    'service': row.service,
                    'sku': row.sku if hasattr(row, 'sku') else None,
                    'cost': float(row.cost),
                    'currency': row.currency,
                    'usage_amount': float(row.usage_amount) if hasattr(row, 'usage_amount') and row.usage_amount else 0.0,
                    'usage_unit': row.usage_unit if hasattr(row, 'usage_unit') else None,
                }
                cost_records.append(record)
            
            logger.info(f"Fetched {len(cost_records)} cost records")
            return cost_records
            
        except exceptions.NotFound:
            logger.warning(f"BigQuery table not found: {full_table_name}")
            logger.warning("Make sure billing export is enabled for this billing account")
            return []
        
        except Exception as e:
            logger.error(f"Error fetching costs from BigQuery: {e}")
            return []
    
    def _build_cost_query(self, table_name: str, start_date: str, end_date: str) -> str:
        """
        Build SQL query for cost data.
        
        Args:
            table_name: Full BigQuery table name
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            
        Returns:
            SQL query string
        """
        if config.AGGREGATION_LEVEL == 'daily' and config.INCLUDE_DETAILS:
            # Daily with service/SKU details
            query = f"""
            SELECT
                DATE(usage_start_time) as date,
                project.id as project_id,
                project.name as project_name,
                service.description as service,
                sku.description as sku,
                SUM(cost) as cost,
                currency,
                SUM(usage.amount) as usage_amount,
                usage.unit as usage_unit
            FROM `{table_name}`
            WHERE DATE(usage_start_time) >= '{start_date}'
                AND DATE(usage_start_time) <= '{end_date}'
                AND cost IS NOT NULL
                AND cost > 0
            GROUP BY 
                date,
                project_id,
                project_name,
                service,
                sku,
                currency,
                usage_unit
            ORDER BY date DESC, cost DESC
            """
        elif config.AGGREGATION_LEVEL == 'daily':
            # Daily aggregated by project
            query = f"""
            SELECT
                DATE(usage_start_time) as date,
                project.id as project_id,
                project.name as project_name,
                'All Services' as service,
                SUM(cost) as cost,
                currency,
                SUM(usage.amount) as usage_amount,
                'mixed' as usage_unit
            FROM `{table_name}`
            WHERE DATE(usage_start_time) >= '{start_date}'
                AND DATE(usage_start_time) <= '{end_date}'
                AND cost IS NOT NULL
                AND cost > 0
            GROUP BY 
                date,
                project_id,
                project_name,
                currency
            ORDER BY date DESC, cost DESC
            """
        elif config.AGGREGATION_LEVEL == 'project':
            # Aggregated by project (total for date range)
            query = f"""
            SELECT
                '{start_date}' as date,
                project.id as project_id,
                project.name as project_name,
                'All Services' as service,
                SUM(cost) as cost,
                currency,
                SUM(usage.amount) as usage_amount,
                'mixed' as usage_unit
            FROM `{table_name}`
            WHERE DATE(usage_start_time) >= '{start_date}'
                AND DATE(usage_start_time) <= '{end_date}'
                AND cost IS NOT NULL
                AND cost > 0
            GROUP BY 
                project_id,
                project_name,
                currency
            ORDER BY cost DESC
            """
        else:  # service
            # Aggregated by service
            query = f"""
            SELECT
                DATE(usage_start_time) as date,
                project.id as project_id,
                project.name as project_name,
                service.description as service,
                SUM(cost) as cost,
                currency,
                SUM(usage.amount) as usage_amount,
                'mixed' as usage_unit
            FROM `{table_name}`
            WHERE DATE(usage_start_time) >= '{start_date}'
                AND DATE(usage_start_time) <= '{end_date}'
                AND cost IS NOT NULL
                AND cost > 0
            GROUP BY 
                date,
                project_id,
                project_name,
                service,
                currency
            ORDER BY date DESC, cost DESC
            """
        
        return query
    
    def load_enrichment_data(self) -> Dict[str, Dict[str, Any]]:
        """
        Load project enrichment data from Firestore.
        
        Returns:
            Dictionary mapping project_id to enrichment data
        """
        logger.info("Loading project enrichment data from Firestore...")
        
        try:
            collection_ref = self.enrichment_client.collection(config.ENRICHMENT_COLLECTION)
            docs = collection_ref.stream()
            
            enrichment_data = {}
            for doc in docs:
                doc_dict = doc.to_dict()
                project_id = doc_dict.get(config.ENRICHMENT_PROJECT_ID_FIELD)
                
                if project_id:
                    enrichment_fields = {}
                    for field in config.ENRICHMENT_FIELD_LIST:
                        if field in doc_dict:
                            enrichment_fields[field] = doc_dict[field]
                    
                    if enrichment_fields:
                        enrichment_data[project_id] = enrichment_fields
            
            logger.info(f"Loaded enrichment data for {len(enrichment_data)} projects")
            return enrichment_data
            
        except Exception as e:
            logger.error(f"Error loading enrichment data: {e}")
            return {}
    
    def enrich_cost_records(
        self, 
        cost_records: List[Dict[str, Any]], 
        enrichment_data: Dict[str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Enrich cost records with project metadata.
        
        Args:
            cost_records: List of cost record dictionaries
            enrichment_data: Dictionary mapping project_id to enrichment data
            
        Returns:
            List of enriched cost records
        """
        if not cost_records:
            return cost_records
        
        logger.info(f"Enriching {len(cost_records)} cost records with project metadata...")
        
        enriched_count = 0
        for record in cost_records:
            project_id = record.get('project_id')
            
            if project_id and project_id in enrichment_data:
                for field, value in enrichment_data[project_id].items():
                    record[field] = value
                enriched_count += 1
            else:
                for field in config.ENRICHMENT_FIELD_LIST:
                    if field not in record:
                        record[field] = None
        
        logger.info(f"Enriched {enriched_count} out of {len(cost_records)} records")
        return cost_records
    
    def _commit_batch_with_retry(
        self, 
        batch: firestore.WriteBatch, 
        batch_count: int,
        max_retries: int = 3
    ) -> bool:
        """
        Commit Firestore batch with exponential backoff retry logic.
        
        Args:
            batch: Firestore WriteBatch to commit
            batch_count: Number of operations in the batch
            max_retries: Maximum number of retry attempts
            
        Returns:
            True if commit succeeded, False otherwise
        """
        for attempt in range(max_retries):
            try:
                batch.commit()
                logger.debug(f"Committed batch of {batch_count} records (attempt {attempt + 1})")
                return True
                
            except exceptions.ResourceExhausted as e:
                # Quota exceeded - use exponential backoff
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + (time.time() % 1)  # Exponential backoff with jitter
                    logger.warning(f"Quota exceeded, retrying in {wait_time:.2f}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed to commit batch after {max_retries} attempts: {e}")
                    return False
                    
            except exceptions.DeadlineExceeded as e:
                # Deadline exceeded - retry with backoff
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + (time.time() % 1)
                    logger.warning(f"Deadline exceeded, retrying in {wait_time:.2f}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed to commit batch after {max_retries} attempts: {e}")
                    return False
                    
            except exceptions.ServiceUnavailable as e:
                # Service temporarily unavailable - retry
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + (time.time() % 1)
                    logger.warning(f"Service unavailable, retrying in {wait_time:.2f}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed to commit batch after {max_retries} attempts: {e}")
                    return False
                    
            except exceptions.Aborted as e:
                # Transaction aborted - retry
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + (time.time() % 1)
                    logger.warning(f"Transaction aborted, retrying in {wait_time:.2f}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed to commit batch after {max_retries} attempts: {e}")
                    return False
                    
            except Exception as e:
                # Other errors - don't retry
                logger.error(f"Unexpected error committing batch: {e}")
                return False
        
        return False
    
    def save_to_firestore(self, cost_records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Save cost records to Firestore with retry logic for transient failures.
        
        Args:
            cost_records: List of cost record dictionaries
            
        Returns:
            Dictionary with save statistics
        """
        if not cost_records:
            logger.info("No cost records to save")
            return {'saved': 0, 'errors': 0}
        
        try:
            collection_ref = self.firestore_client.collection(config.FIRESTORE_COLLECTION)
            batch = self.firestore_client.batch()
            batch_count = 0
            stats = {'saved': 0, 'errors': 0}
            batch_doc_ids = []  # Track document IDs in current batch
            
            for record in cost_records:
                try:
                    # Generate document ID: {billing_account}_{date}_{project}_{service}
                    doc_id = f"{record['billing_account_id']}_{record['date']}_{record['project_id']}_{record['service']}"
                    # Replace invalid characters
                    doc_id = doc_id.replace('/', '_').replace(' ', '_')[:1500]  # Firestore limit
                    
                    doc_ref = collection_ref.document(doc_id)
                    
                    # Add metadata
                    record['processed_at'] = datetime.utcnow().isoformat()
                    record['aggregation_level'] = config.AGGREGATION_LEVEL
                    
                    # Use merge=True for idempotency
                    batch.set(doc_ref, record, merge=True)
                    batch_count += 1
                    batch_doc_ids.append(doc_id)
                    
                    # Firestore batch limit is 500 operations
                    if batch_count >= 500:
                        # Commit with retry logic
                        if self._commit_batch_with_retry(batch, batch_count):
                            stats['saved'] += batch_count
                            logger.info(f"Successfully committed batch of {batch_count} records")
                        else:
                            stats['errors'] += batch_count
                            logger.error(f"Failed to commit batch of {batch_count} records")
                            logger.error(f"Failed document IDs (first 10): {batch_doc_ids[:10]}")
                        
                        # Reset for next batch
                        batch = self.firestore_client.batch()
                        batch_count = 0
                        batch_doc_ids = []
                
                except Exception as e:
                    logger.error(f"Error preparing record: {e}")
                    stats['errors'] += 1
            
            # Commit remaining records
            if batch_count > 0:
                if self._commit_batch_with_retry(batch, batch_count):
                    stats['saved'] += batch_count
                    logger.info(f"Successfully committed final batch of {batch_count} records")
                else:
                    stats['errors'] += batch_count
                    logger.error(f"Failed to commit final batch of {batch_count} records")
                    logger.error(f"Failed document IDs (first 10): {batch_doc_ids[:10]}")
            
            logger.info(f"Save complete: {stats['saved']} saved, {stats['errors']} errors")
            return stats
                
        except Exception as e:
            logger.error(f"Error saving to Firestore: {e}")
            raise
    
    def generate_statistics(self, cost_records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate statistics about processed cost data.
        
        Args:
            cost_records: List of cost records
            
        Returns:
            Dictionary with statistics
        """
        if not cost_records:
            return {}
        
        total_cost = sum(r.get('cost', 0) for r in cost_records)
        currency = cost_records[0].get('currency', 'USD') if cost_records else 'USD'
        
        # Group by date
        daily_totals = defaultdict(float)
        for record in cost_records:
            date = record.get('date')
            cost = record.get('cost', 0)
            daily_totals[date] += cost
        
        # Group by project
        project_totals = defaultdict(float)
        for record in cost_records:
            project = record.get('project_id')
            cost = record.get('cost', 0)
            project_totals[project] += cost
        
        # Group by service
        service_totals = defaultdict(float)
        for record in cost_records:
            service = record.get('service')
            cost = record.get('cost', 0)
            service_totals[service] += cost
        
        stats = {
            'total_records': len(cost_records),
            'total_cost': total_cost,
            'currency': currency,
            'unique_dates': len(daily_totals),
            'unique_projects': len(project_totals),
            'unique_services': len(service_totals),
            'daily_breakdown': dict(sorted(daily_totals.items(), reverse=True)),
            'top_projects': dict(sorted(project_totals.items(), key=lambda x: x[1], reverse=True)[:10]),
            'top_services': dict(sorted(service_totals.items(), key=lambda x: x[1], reverse=True)[:10]),
        }
        
        return stats
    
    def run(self):
        """Main execution method."""
        logger.info("=" * 60)
        logger.info("Starting Cost BigQuery Processor")
        logger.info("=" * 60)
        
        try:
            # Get billing accounts
            billing_accounts = self.get_billing_accounts()
            if not billing_accounts:
                logger.warning("No billing accounts to process")
                return 1
            
            # Get date range
            start_date, end_date = self.get_date_range()
            
            # Load enrichment data
            enrichment_data = self.load_enrichment_data()
            
            # Process each billing account
            all_cost_records = []
            for account_id in billing_accounts:
                logger.info(f"Processing billing account: {account_id}")
                
                # Fetch costs
                cost_records = self.fetch_daily_costs(account_id, start_date, end_date)
                
                # Enrich records
                if cost_records:
                    cost_records = self.enrich_cost_records(cost_records, enrichment_data)
                    all_cost_records.extend(cost_records)
            
            # Generate statistics
            stats = self.generate_statistics(all_cost_records)
            logger.info(f"Cost Statistics:")
            logger.info(f"  Total Records: {stats.get('total_records', 0)}")
            logger.info(f"  Total Cost: {stats.get('currency', 'USD')} {stats.get('total_cost', 0):.2f}")
            logger.info(f"  Unique Projects: {stats.get('unique_projects', 0)}")
            logger.info(f"  Unique Services: {stats.get('unique_services', 0)}")
            
            # Save to Firestore
            save_stats = self.save_to_firestore(all_cost_records)
            logger.info(f"Save Statistics: {save_stats}")
            
            logger.info("=" * 60)
            logger.info("Cost BigQuery Processor Completed Successfully")
            logger.info("=" * 60)
            
            return 0
            
        except Exception as e:
            logger.error(f"Error in cost processor: {e}", exc_info=True)
            return 1


if __name__ == "__main__":
    processor = CostBigQueryProcessor()
    exit_code = processor.run()
    sys.exit(exit_code)
