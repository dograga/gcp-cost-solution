#!/usr/bin/env python3
"""
Cloud Run Job to fetch GCP monthly invoices and store them in Firestore.
Retrieves invoices from Cloud Billing API and enriches line items with project metadata.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from collections import defaultdict
from dateutil.relativedelta import relativedelta

from google.cloud import billing_v1
from google.cloud import firestore
from google.api_core import exceptions, retry

# Import configuration
import config

# Import BigQuery client
from bigquery_client import BillingLineItemsClient

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Log configuration on startup
logger.info(f"Starting with environment: {config.ENVIRONMENT}")
logger.debug(f"Configuration: {config.CONFIG}")


class InvoiceCollector:
    """Collects GCP monthly invoices and enriches them with project metadata."""
    
    def __init__(self):
        """Initialize the Billing, BigQuery, and Firestore clients."""
        self.cloud_billing_client = billing_v1.CloudBillingClient()
        self.bq_line_items_client = BillingLineItemsClient()
        
        # Firestore clients for different databases
        self.firestore_client = firestore.Client(
            project=config.GCP_PROJECT_ID,
            database=config.FIRESTORE_DATABASE
        )
        
        self.enrichment_client = firestore.Client(
            project=config.GCP_PROJECT_ID,
            database=config.ENRICHMENT_DATABASE
        )
        
        self.billing_account_ids = config.BILLING_ACCOUNT_LIST
        
        logger.info(f"Initialized InvoiceCollector for project: {config.GCP_PROJECT_ID}")
        logger.info(f"Firestore database: {config.FIRESTORE_DATABASE}")
        logger.info(f"Enrichment database: {config.ENRICHMENT_DATABASE}")
        logger.info(f"BigQuery dataset: {config.BILLING_DATASET}")
    
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
            page_result = self.cloud_billing_client.list_billing_accounts(request=request)
            
            accounts = []
            for account in page_result:
                if account.open:  # Only include open accounts
                    account_id = account.name.split('/')[-1]
                    accounts.append(account_id)
                    logger.info(f"Found billing account: {account_id} ({account.display_name})")
            
            if not accounts:
                logger.warning("No open billing accounts found")
            
            return accounts
            
        except exceptions.GoogleAPIError as e:
            logger.error(f"Error listing billing accounts: {e}")
            raise
    
    def get_invoice_months(self) -> List[str]:
        """
        Generate list of invoice months to fetch (YYYY-MM format).
        """
        months = []
        current_date = datetime.now()
        
        for i in range(config.MONTHS_BACK):
            month_date = current_date - relativedelta(months=i)
            month_str = month_date.strftime('%Y-%m')
            months.append(month_str)
        
        logger.info(f"Fetching invoices for {len(months)} months: {months[0]} to {months[-1]}")
        return months
    
    def fetch_invoices(self, billing_account_id: str, months: List[str]) -> List[Dict[str, Any]]:
        """
        Fetch invoices for a billing account using Cloud Billing API.
        Returns:
            List of invoice dictionaries
        """
        logger.info(f"Fetching invoices for billing account: {billing_account_id}")
        
        invoices = []
        
        try:
            # Build the parent resource name
            parent = f"billingAccounts/{billing_account_id}"
            
            # Create request to list invoices
            request = billing_v1.ListInvoicesRequest(
                parent=parent
            )
            
            # Call the API
            page_result = self.cloud_billing_client.list_invoices(request=request)
            
            # Process each invoice
            for invoice_proto in page_result:
                # Extract invoice month from invoice name or date
                invoice_month = self._extract_invoice_month(invoice_proto)
                
                # Skip if not in our target months
                if invoice_month not in months:
                    continue
                
                # Parse invoice data
                invoice = self._parse_invoice(invoice_proto)
                
                # Fetch line items if configured
                if config.INCLUDE_LINE_ITEMS:
                    line_items = self.fetch_line_items(billing_account_id, invoice_month)
                    invoice['line_items'] = line_items
                
                invoices.append(invoice)
                logger.debug(f"Fetched invoice: {invoice['invoice_id']}")
            
            logger.info(f"Fetched {len(invoices)} invoices for account {billing_account_id}")
            return invoices
            
        except exceptions.GoogleAPIError as e:
            logger.error(f"Error fetching invoices for {billing_account_id}: {e}")
            raise
    
    def _extract_invoice_month(self, invoice) -> str:
        """
        Extract invoice month from invoice object.
        """
        # Try to get month from invoice_month field if available
        if hasattr(invoice, 'invoice_month') and invoice.invoice_month:
            return f"{invoice.invoice_month.year:04d}-{invoice.invoice_month.month:02d}"
        
        # Fallback to parsing from name or using current month
        # Invoice name format: billingAccounts/{account}/invoices/{invoice_id}
        # For now, use current month as fallback
        return datetime.now().strftime('%Y-%m')
    
    def _parse_invoice(self, invoice_proto) -> Dict[str, Any]:
        """
        Parse invoice protobuf object into dictionary.
        """
        # Extract invoice ID from name (e.g., "billingAccounts/123/invoices/456")
        invoice_id = invoice_proto.name.split('/')[-1] if hasattr(invoice_proto, 'name') else 'unknown'
        
        # Extract billing account ID
        billing_account_id = invoice_proto.name.split('/')[1] if hasattr(invoice_proto, 'name') else 'unknown'
        
        # Extract month
        invoice_month = self._extract_invoice_month(invoice_proto)
        
        # Build invoice dictionary
        invoice = {
            'invoice_id': invoice_id,
            'billing_account_id': billing_account_id,
            'invoice_month': invoice_month,
            'invoice_name': invoice_proto.name if hasattr(invoice_proto, 'name') else '',
            'currency': invoice_proto.currency_code if hasattr(invoice_proto, 'currency_code') else 'USD',
            'total_amount': 0.0,
            'subtotal': 0.0,
            'tax': 0.0,
            'credits': 0.0,
            'status': 'finalized',
            'fetched_at': datetime.utcnow().isoformat(),
            'line_items': []
        }
        
        # Extract amounts if available
        if hasattr(invoice_proto, 'amount_due') and invoice_proto.amount_due:
            invoice['total_amount'] = float(invoice_proto.amount_due.units + invoice_proto.amount_due.nanos / 1e9)
        
        if hasattr(invoice_proto, 'subtotal') and invoice_proto.subtotal:
            invoice['subtotal'] = float(invoice_proto.subtotal.units + invoice_proto.subtotal.nanos / 1e9)
        
        if hasattr(invoice_proto, 'tax_amount') and invoice_proto.tax_amount:
            invoice['tax'] = float(invoice_proto.tax_amount.units + invoice_proto.tax_amount.nanos / 1e9)
        
        if hasattr(invoice_proto, 'credits_amount') and invoice_proto.credits_amount:
            invoice['credits'] = float(invoice_proto.credits_amount.units + invoice_proto.credits_amount.nanos / 1e9)
        
        # Extract dates - prefer API values over calculated fallbacks
        if hasattr(invoice_proto, 'issue_date') and invoice_proto.issue_date:
            invoice['issue_date'] = f"{invoice_proto.issue_date.year:04d}-{invoice_proto.issue_date.month:02d}-{invoice_proto.issue_date.day:02d}"
        else:
            # Fallback: use first day of invoice month
            invoice['issue_date'] = f"{invoice_month}-01"
        
        if hasattr(invoice_proto, 'due_date') and invoice_proto.due_date:
            # Use actual due date from Google's billing system
            invoice['due_date'] = f"{invoice_proto.due_date.year:04d}-{invoice_proto.due_date.month:02d}-{invoice_proto.due_date.day:02d}"
        else:
            # Fallback: estimate due date (only used if API doesn't provide it)
            invoice['due_date'] = self._calculate_due_date(invoice_month)
            logger.debug(f"Using calculated due date for invoice {invoice_id} (API value not available)")
        
        return invoice
    
    def fetch_line_items(self, billing_account_id: str, month: str) -> List[Dict[str, Any]]:
        """
        Fetch invoice line items for a specific month from BigQuery.
        
        Args:
            billing_account_id: Billing account ID
            month: Month in YYYY-MM format
            
        Returns:
            List of line item dictionaries
        """
        return self.bq_line_items_client.fetch_line_items(billing_account_id, month)
    
    def _is_past_month(self, month: str) -> bool:
        """Check if month is in the past."""
        month_date = datetime.strptime(month, '%Y-%m')
        current_month = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return month_date < current_month
    
    def _calculate_due_date(self, month: str) -> str:
        """
        Calculate estimated invoice due date as fallback.
        
        Note: This is only used when the API doesn't provide a due_date.
        Google's actual invoice due dates may vary based on billing terms.
        This estimates 30 days after month end as a reasonable default.
        
        Args:
            month: Invoice month in YYYY-MM format
            
        Returns:
            Estimated due date in YYYY-MM-DD format
        """
        month_date = datetime.strptime(month, '%Y-%m')
        # Last day of month + 30 days
        next_month = month_date + relativedelta(months=1)
        last_day = next_month - timedelta(days=1)
        due_date = last_day + timedelta(days=30)
        return due_date.strftime('%Y-%m-%d')
    
    def load_enrichment_data(self) -> Dict[str, Dict[str, Any]]:
        """
        Load project enrichment data from Firestore.
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
                    # Extract only the fields we need
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
    
    def enrich_line_items(
        self, 
        line_items: List[Dict[str, Any]], 
        enrichment_data: Dict[str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Enrich invoice line items with project metadata.
        """
        if not line_items:
            return line_items
        
        logger.info(f"Enriching {len(line_items)} line items with project metadata...")
        
        enriched_count = 0
        for item in line_items:
            project_id = item.get('project_id')
            
            if project_id and project_id in enrichment_data:
                # Add enrichment fields
                for field, value in enrichment_data[project_id].items():
                    item[field] = value
                enriched_count += 1
            else:
                # Add null values for missing enrichment fields
                for field in config.ENRICHMENT_FIELD_LIST:
                    if field not in item:
                        item[field] = None
        
        logger.info(f"Enriched {enriched_count} out of {len(line_items)} line items")
        return line_items
    
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
                logger.debug(f"Committed batch of {batch_count} invoices (attempt {attempt + 1})")
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
                    
            except Exception as e:
                # Other errors - don't retry
                logger.error(f"Unexpected error committing batch: {e}")
                return False
        
        return False
    
    def save_invoices_to_firestore(self, invoices: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Save invoices to Firestore with retry logic for transient failures.
        
        Args:
            invoices: List of invoice dictionaries
            
        Returns:
            Dictionary with save statistics
        """
        if not invoices:
            logger.info("No invoices to save")
            return {'saved': 0, 'updated': 0, 'errors': 0}
        
        try:
            collection_ref = self.firestore_client.collection(config.FIRESTORE_COLLECTION)
            batch = self.firestore_client.batch()
            batch_count = 0
            stats = {'saved': 0, 'updated': 0, 'errors': 0}
            batch_invoices = []  # Track invoices in current batch
            
            for invoice in invoices:
                try:
                    # Use invoice_id as document ID for idempotency
                    doc_id = invoice['invoice_id']
                    doc_ref = collection_ref.document(doc_id)
                    
                    # Use merge=True to update existing invoices
                    batch.set(doc_ref, invoice, merge=True)
                    batch_count += 1
                    batch_invoices.append(invoice['invoice_id'])
                    
                    # Firestore batch limit is 500 operations
                    if batch_count >= 500:
                        # Commit with retry logic
                        if self._commit_batch_with_retry(batch, batch_count):
                            stats['saved'] += batch_count
                            logger.info(f"Successfully committed batch of {batch_count} invoices")
                        else:
                            stats['errors'] += batch_count
                            logger.error(f"Failed to commit batch of {batch_count} invoices: {batch_invoices}")
                        
                        # Reset for next batch
                        batch = self.firestore_client.batch()
                        batch_count = 0
                        batch_invoices = []
                
                except Exception as e:
                    logger.error(f"Error preparing invoice {invoice.get('invoice_id')}: {e}")
                    stats['errors'] += 1
            
            # Commit remaining records
            if batch_count > 0:
                if self._commit_batch_with_retry(batch, batch_count):
                    stats['saved'] += batch_count
                    logger.info(f"Successfully committed final batch of {batch_count} invoices")
                else:
                    stats['errors'] += batch_count
                    logger.error(f"Failed to commit final batch of {batch_count} invoices: {batch_invoices}")
            
            logger.info(f"Save complete: {stats['saved']} saved, {stats['errors']} errors")
            return stats
                
        except Exception as e:
            logger.error(f"Error saving invoices to Firestore: {e}")
            raise
    
    def generate_statistics(self, invoices: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate statistics about collected invoices.
        
        Args:
            invoices: List of invoice dictionaries
            
        Returns:
            Dictionary with statistics
        """
        if not invoices:
            return {}
        
        stats = {
            'total_invoices': len(invoices),
            'total_amount': sum(inv.get('total_amount', 0) for inv in invoices),
            'currency': invoices[0].get('currency', 'USD'),
            'months_covered': len(set(inv.get('invoice_month') for inv in invoices)),
            'billing_accounts': len(set(inv.get('billing_account_id') for inv in invoices)),
            'finalized_invoices': sum(1 for inv in invoices if inv.get('status') == 'finalized'),
            'pending_invoices': sum(1 for inv in invoices if inv.get('status') == 'pending'),
        }
        
        # Calculate monthly breakdown
        monthly_totals = defaultdict(float)
        for invoice in invoices:
            month = invoice.get('invoice_month')
            amount = invoice.get('total_amount', 0)
            monthly_totals[month] += amount
        
        stats['monthly_breakdown'] = dict(monthly_totals)
        
        return stats
    
    def run(self):
        """Main execution method."""
        logger.info("=" * 60)
        logger.info("Starting Invoice Ingestion Job")
        logger.info("=" * 60)
        
        try:
            # Get billing accounts
            billing_accounts = self.get_billing_accounts()
            if not billing_accounts:
                logger.warning("No billing accounts to process")
                return
            
            # Get months to fetch
            months = self.get_invoice_months()
            
            # Load enrichment data
            enrichment_data = self.load_enrichment_data()
            
            # Collect invoices from all billing accounts
            all_invoices = []
            for account_id in billing_accounts:
                logger.info(f"Processing billing account: {account_id}")
                invoices = self.fetch_invoices(account_id, months)
                
                # Enrich line items
                for invoice in invoices:
                    if invoice.get('line_items'):
                        invoice['line_items'] = self.enrich_line_items(
                            invoice['line_items'],
                            enrichment_data
                        )
                
                all_invoices.extend(invoices)
            
            # Generate statistics
            stats = self.generate_statistics(all_invoices)
            logger.info(f"Invoice Statistics: {stats}")
            
            # Save to Firestore
            save_stats = self.save_invoices_to_firestore(all_invoices)
            logger.info(f"Save Statistics: {save_stats}")
            
            logger.info("=" * 60)
            logger.info("Invoice Ingestion Job Completed Successfully")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"Error in invoice ingestion job: {e}", exc_info=True)
            raise


if __name__ == "__main__":
    collector = InvoiceCollector()
    collector.run()
