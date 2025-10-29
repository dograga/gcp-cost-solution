"""
BigQuery client for fetching billing line items from GCP billing export.
"""

import logging
from typing import List, Dict, Any
from datetime import datetime

from google.cloud import bigquery
from google.api_core import exceptions

# Import configuration
import config

logger = logging.getLogger(__name__)


class BillingLineItemsClient:
    """Client for fetching billing line items from BigQuery."""
    
    def __init__(self):
        """Initialize BigQuery client."""
        self.bq_client = bigquery.Client(project=config.GCP_PROJECT_ID)
        self.billing_dataset = config.BILLING_DATASET
        self.billing_table_prefix = config.BILLING_TABLE_PREFIX
        logger.info(f"Initialized BigQuery client for project: {config.GCP_PROJECT_ID}")
    
    def fetch_line_items(
        self, 
        billing_account_id: str, 
        month: str
    ) -> List[Dict[str, Any]]:
        """
        Fetch invoice line items for a specific billing account and month.
        
        Args:
            billing_account_id: Billing account ID (e.g., "012345-ABCDEF-GHIJKL")
            month: Month in YYYY-MM format (e.g., "2025-10")
            
        Returns:
            List of line item dictionaries with project, service, SKU, and cost
        """
        logger.info(f"Fetching line items for {billing_account_id} - {month}")
        
        try:
            # Build table name
            # Format: gcp_billing_export_v1_BILLING_ACCOUNT_ID (dashes replaced with underscores)
            table_suffix = billing_account_id.replace('-', '_')
            table_name = f"{self.billing_table_prefix}_{table_suffix}"
            full_table_name = f"{config.GCP_PROJECT_ID}.{self.billing_dataset}.{table_name}"
            
            # Build query
            query = self._build_line_items_query(full_table_name, month)
            
            # Execute query
            logger.debug(f"Executing query on table: {full_table_name}")
            query_job = self.bq_client.query(query)
            results = query_job.result()
            
            # Parse results
            line_items = []
            for row in results:
                line_item = {
                    'project_id': row.project_id,
                    'project_name': row.project_name,
                    'service': row.service,
                    'sku': row.sku,
                    'cost': float(row.cost),
                    'currency': row.currency,
                    'usage_amount': float(row.usage_amount) if row.usage_amount else 0.0,
                    'usage_unit': row.usage_unit,
                }
                line_items.append(line_item)
            
            logger.info(f"Fetched {len(line_items)} line items for {month}")
            return line_items
            
        except exceptions.NotFound:
            logger.warning(f"BigQuery table not found: {full_table_name}")
            logger.warning("Make sure billing export is enabled for this billing account")
            return []
        
        except Exception as e:
            logger.error(f"Error fetching line items from BigQuery: {e}")
            # Return empty list instead of raising to allow invoice processing to continue
            return []
    
    def _build_line_items_query(self, table_name: str, month: str) -> str:
        """
        Build SQL query to fetch line items for a specific month.
        
        Args:
            table_name: Full BigQuery table name
            month: Month in YYYY-MM format
            
        Returns:
            SQL query string
        """
        # Parse month to get first day
        month_start = f"{month}-01"
        
        query = f"""
        SELECT
            project.id as project_id,
            project.name as project_name,
            service.description as service,
            sku.description as sku,
            SUM(cost) as cost,
            currency,
            SUM(usage.amount) as usage_amount,
            usage.unit as usage_unit
        FROM `{table_name}`
        WHERE DATE_TRUNC(usage_start_time, MONTH) = '{month_start}'
            AND cost IS NOT NULL
        GROUP BY 
            project_id,
            project_name,
            service,
            sku,
            currency,
            usage_unit
        HAVING cost != 0
        ORDER BY cost DESC
        """
        
        return query
    
    def fetch_monthly_summary(
        self, 
        billing_account_id: str, 
        month: str
    ) -> Dict[str, Any]:
        """
        Fetch monthly cost summary for a billing account.
        
        Args:
            billing_account_id: Billing account ID
            month: Month in YYYY-MM format
            
        Returns:
            Dictionary with total cost, currency, and breakdown by service
        """
        logger.info(f"Fetching monthly summary for {billing_account_id} - {month}")
        
        try:
            # Build table name
            table_suffix = billing_account_id.replace('-', '_')
            table_name = f"{self.billing_table_prefix}_{table_suffix}"
            full_table_name = f"{config.GCP_PROJECT_ID}.{self.billing_dataset}.{table_name}"
            
            # Build query
            query = self._build_summary_query(full_table_name, month)
            
            # Execute query
            query_job = self.bq_client.query(query)
            results = query_job.result()
            
            # Parse results
            summary = {
                'total_cost': 0.0,
                'currency': 'USD',
                'service_breakdown': {},
                'project_breakdown': {}
            }
            
            for row in results:
                summary['total_cost'] = float(row.total_cost)
                summary['currency'] = row.currency
                break  # Only one row expected
            
            logger.info(f"Monthly summary: {summary['total_cost']} {summary['currency']}")
            return summary
            
        except exceptions.NotFound:
            logger.warning(f"BigQuery table not found for summary query")
            return {'total_cost': 0.0, 'currency': 'USD', 'service_breakdown': {}, 'project_breakdown': {}}
        
        except Exception as e:
            logger.error(f"Error fetching monthly summary: {e}")
            return {'total_cost': 0.0, 'currency': 'USD', 'service_breakdown': {}, 'project_breakdown': {}}
    
    def _build_summary_query(self, table_name: str, month: str) -> str:
        """
        Build SQL query to fetch monthly cost summary.
        
        Args:
            table_name: Full BigQuery table name
            month: Month in YYYY-MM format
            
        Returns:
            SQL query string
        """
        month_start = f"{month}-01"
        
        query = f"""
        SELECT
            SUM(cost) as total_cost,
            currency
        FROM `{table_name}`
        WHERE DATE_TRUNC(usage_start_time, MONTH) = '{month_start}'
            AND cost IS NOT NULL
        GROUP BY currency
        ORDER BY total_cost DESC
        LIMIT 1
        """
        
        return query
    
    def test_connection(self, billing_account_id: str) -> bool:
        """
        Test if BigQuery billing export table exists and is accessible.
        
        Args:
            billing_account_id: Billing account ID
            
        Returns:
            True if table exists and is accessible, False otherwise
        """
        try:
            table_suffix = billing_account_id.replace('-', '_')
            table_name = f"{self.billing_table_prefix}_{table_suffix}"
            full_table_name = f"{config.GCP_PROJECT_ID}.{self.billing_dataset}.{table_name}"
            
            # Try to get table metadata
            table_ref = self.bq_client.get_table(full_table_name)
            logger.info(f"BigQuery table found: {full_table_name} ({table_ref.num_rows} rows)")
            return True
            
        except exceptions.NotFound:
            logger.warning(f"BigQuery table not found: {full_table_name}")
            logger.warning("Enable billing export: https://cloud.google.com/billing/docs/how-to/export-data-bigquery")
            return False
        
        except Exception as e:
            logger.error(f"Error testing BigQuery connection: {e}")
            return False
