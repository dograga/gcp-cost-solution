#!/usr/bin/env python3
"""
Cloud Run Job to fetch GCP cost anomalies and enrich them with project metadata.
Retrieves anomalies from GCP Billing API and enriches with appcode and lob from Firestore.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from collections import defaultdict

from google.cloud import billing_v1
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


class CostAnomalyCollector:
    """Collects GCP cost anomalies and enriches them with project metadata."""
    
    def __init__(self):
        """Initialize the Billing and Firestore clients."""
        self.anomaly_service_client = billing_v1.AnomalyServiceClient()
        self.cloud_billing_client = billing_v1.CloudBillingClient()
        
        # Firestore clients for different databases
        self.firestore_client = firestore.Client(
            project=config.GCP_PROJECT_ID,
            database=config.FIRESTORE_DATABASE
        )
        
        self.enrichment_client = firestore.Client(
            project=config.GCP_PROJECT_ID,
            database=config.ENRICHMENT_DATABASE
        )
        
        self.organization_id = config.ORGANIZATION_ID
        self.billing_account_ids = config.BILLING_ACCOUNT_LIST
        
        logger.info(f"Initialized CostAnomalyCollector for organization: {self.organization_id}")
        logger.info(f"Firestore database: {config.FIRESTORE_DATABASE}")
        logger.info(f"Enrichment database: {config.ENRICHMENT_DATABASE}")
    
    def get_billing_accounts(self) -> List[str]:
        """
        Get list of billing accounts to process.
        
        Returns:
            List of billing account IDs
        """
        if self.billing_account_ids:
            logger.info(f"Using configured billing accounts: {self.billing_account_ids}")
            return self.billing_account_ids
        
        # Discover all accessible billing accounts
        logger.info("Discovering all accessible billing accounts...")
        try:
            billing_accounts = []
            request = billing_v1.ListBillingAccountsRequest()
            page_result = self.cloud_billing_client.list_billing_accounts(request=request)
            
            for account in page_result:
                if account.open:
                    account_id = account.name.split('/')[-1]
                    billing_accounts.append(account_id)
                    logger.info(f"Found billing account: {account_id} ({account.display_name})")
            
            logger.info(f"Discovered {len(billing_accounts)} billing accounts")
            return billing_accounts
            
        except exceptions.GoogleAPIError as e:
            logger.error(f"Error listing billing accounts: {e}")
            return []
    
    def load_project_enrichment_data(self) -> Dict[str, Dict[str, Any]]:
        """
        Load project enrichment data from Firestore.
        
        Returns:
            Dictionary mapping project_id to enrichment data
        """
        logger.info(f"Loading project enrichment data from {config.ENRICHMENT_COLLECTION}...")
        enrichment_data = {}
        
        try:
            collection_ref = self.enrichment_client.collection(config.ENRICHMENT_COLLECTION)
            docs = collection_ref.stream()
            
            for doc in docs:
                doc_data = doc.to_dict()
                project_id = doc_data.get(config.ENRICHMENT_PROJECT_ID_FIELD)
                
                if project_id:
                    # Extract only the fields we need
                    enrichment_info = {}
                    for field in config.ENRICHMENT_FIELD_LIST:
                        if field in doc_data:
                            enrichment_info[field] = doc_data[field]
                    
                    enrichment_data[project_id] = enrichment_info
            
            logger.info(f"Loaded enrichment data for {len(enrichment_data)} projects")
            logger.debug(f"Enrichment fields: {config.ENRICHMENT_FIELD_LIST}")
            
            return enrichment_data
            
        except exceptions.GoogleAPIError as e:
            logger.error(f"Error loading enrichment data: {e}")
            return {}
    
    def fetch_anomalies_for_billing_account(
        self, 
        billing_account_id: str,
        days_back: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Fetch cost anomalies for a specific billing account.
        
        Args:
            billing_account_id: Billing account ID
            days_back: Number of days back to fetch anomalies
            
        Returns:
            List of anomaly dictionaries
        """
        logger.info(f"Fetching anomalies for billing account: {billing_account_id}")
        
        parent = f"billingAccounts/{billing_account_id}"
        anomalies = []
        
        try:
            # Create request
            request = billing_v1.ListAnomaliesRequest(
                parent=parent,
            )
            
            # Fetch anomalies
            page_result = self.anomaly_service_client.list_anomalies(request=request)
            
            for anomaly in page_result:
                # Convert to dictionary
                anomaly_dict = self._anomaly_to_dict(anomaly, billing_account_id)
                
                # Apply filters
                if self._should_include_anomaly(anomaly_dict):
                    anomalies.append(anomaly_dict)
            
            logger.info(f"Found {len(anomalies)} anomalies for billing account {billing_account_id}")
            return anomalies
            
        except exceptions.GoogleAPIError as e:
            logger.error(f"Error fetching anomalies for {billing_account_id}: {e}")
            return []
    
    def _anomaly_to_dict(self, anomaly: Any, billing_account_id: str) -> Dict[str, Any]:
        """
        Convert anomaly object to dictionary.
        
        Args:
            anomaly: Anomaly object from API
            billing_account_id: Billing account ID
            
        Returns:
            Dictionary representation of anomaly
        """
        anomaly_dict = {
            'anomaly_id': anomaly.name.split('/')[-1] if hasattr(anomaly, 'name') else None,
            'billing_account_id': billing_account_id,
            'detection_time': anomaly.detection_time.isoformat() if hasattr(anomaly, 'detection_time') and anomaly.detection_time else None,
            'update_time': anomaly.update_time.isoformat() if hasattr(anomaly, 'update_time') and anomaly.update_time else None,
            'collected_at': datetime.utcnow().isoformat(),
        }
        
        # Extract scope (project, service, etc.)
        if hasattr(anomaly, 'scope') and anomaly.scope:
            scope = anomaly.scope
            if hasattr(scope, 'project_id'):
                anomaly_dict['project_id'] = scope.project_id
            if hasattr(scope, 'service'):
                anomaly_dict['service'] = scope.service
            if hasattr(scope, 'location'):
                anomaly_dict['location'] = scope.location
        
        # Extract cost impact
        if hasattr(anomaly, 'cost_impact') and anomaly.cost_impact:
            cost_impact = anomaly.cost_impact
            if hasattr(cost_impact, 'cost_change'):
                anomaly_dict['cost_change'] = float(cost_impact.cost_change)
            if hasattr(cost_impact, 'percentage_change'):
                anomaly_dict['percentage_change'] = float(cost_impact.percentage_change)
            if hasattr(cost_impact, 'currency_code'):
                anomaly_dict['currency_code'] = cost_impact.currency_code
        
        # Extract time period
        if hasattr(anomaly, 'time_period') and anomaly.time_period:
            time_period = anomaly.time_period
            if hasattr(time_period, 'start_time') and time_period.start_time:
                anomaly_dict['period_start'] = time_period.start_time.isoformat()
            if hasattr(time_period, 'end_time') and time_period.end_time:
                anomaly_dict['period_end'] = time_period.end_time.isoformat()
        
        # Extract anomaly type/severity
        if hasattr(anomaly, 'severity'):
            anomaly_dict['severity'] = str(anomaly.severity)
        
        if hasattr(anomaly, 'type'):
            anomaly_dict['type'] = str(anomaly.type)
        
        # Extract description
        if hasattr(anomaly, 'description'):
            anomaly_dict['description'] = anomaly.description
        
        return anomaly_dict
    
    def _convert_to_usd(self, amount: float, currency: str) -> float:
        """
        Convert amount to USD using approximate exchange rates.
        
        Args:
            amount: Amount in original currency
            currency: Currency code (e.g., 'USD', 'EUR', 'JPY')
            
        Returns:
            Amount in USD
        """
        # Approximate exchange rates (as of common baseline)
        # In production, consider using a real-time exchange rate API
        exchange_rates = {
            'USD': 1.0,
            'EUR': 1.08,      # 1 EUR ≈ 1.08 USD
            'GBP': 1.27,      # 1 GBP ≈ 1.27 USD
            'JPY': 0.0067,    # 1 JPY ≈ 0.0067 USD
            'SGD': 0.74,      # 1 SGD ≈ 0.74 USD
            'AUD': 0.65,      # 1 AUD ≈ 0.65 USD
            'CAD': 0.72,      # 1 CAD ≈ 0.72 USD
            'INR': 0.012,     # 1 INR ≈ 0.012 USD
            'CNY': 0.14,      # 1 CNY ≈ 0.14 USD
            'HKD': 0.13,      # 1 HKD ≈ 0.13 USD
            'NZD': 0.60,      # 1 NZD ≈ 0.60 USD
            'CHF': 1.13,      # 1 CHF ≈ 1.13 USD
            'SEK': 0.096,     # 1 SEK ≈ 0.096 USD
            'NOK': 0.093,     # 1 NOK ≈ 0.093 USD
            'DKK': 0.145,     # 1 DKK ≈ 0.145 USD
            'BRL': 0.20,      # 1 BRL ≈ 0.20 USD
            'MXN': 0.058,     # 1 MXN ≈ 0.058 USD
            'ZAR': 0.055,     # 1 ZAR ≈ 0.055 USD
            'KRW': 0.00075,   # 1 KRW ≈ 0.00075 USD
            'TWD': 0.031,     # 1 TWD ≈ 0.031 USD
        }
        
        rate = exchange_rates.get(currency.upper(), 1.0)
        usd_amount = amount * rate
        
        if currency.upper() not in exchange_rates and currency.upper() != 'USD':
            logger.warning(f"Unknown currency '{currency}', treating as USD")
        
        return usd_amount
    
    def _should_include_anomaly(self, anomaly: Dict[str, Any]) -> bool:
        """
        Check if anomaly should be included based on filters.
        Converts cost to USD for consistent filtering across currencies.
        
        Args:
            anomaly: Anomaly dictionary
            
        Returns:
            True if anomaly should be included
        """
        # Filter by minimum impact amount (convert to USD first)
        cost_change = abs(anomaly.get('cost_change', 0))
        currency = anomaly.get('currency_code', 'USD')
        
        # Convert to USD for consistent comparison
        cost_change_usd = self._convert_to_usd(cost_change, currency)
        
        if cost_change_usd < config.MIN_IMPACT_AMOUNT:
            logger.debug(f"Skipping anomaly with cost change {cost_change} {currency} (${cost_change_usd:.2f} USD, below minimum ${config.MIN_IMPACT_AMOUNT})")
            return False
        
        # Filter by anomaly type if specified
        if config.ANOMALY_TYPE_LIST:
            anomaly_type = anomaly.get('type', '')
            if anomaly_type not in config.ANOMALY_TYPE_LIST:
                logger.debug(f"Skipping anomaly with type {anomaly_type} (not in filter list)")
                return False
        
        return True
    
    def enrich_anomalies(
        self, 
        anomalies: List[Dict[str, Any]], 
        enrichment_data: Dict[str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Enrich anomalies with project metadata.
        
        Args:
            anomalies: List of anomaly dictionaries
            enrichment_data: Dictionary mapping project_id to enrichment data
            
        Returns:
            List of enriched anomaly dictionaries
        """
        logger.info(f"Enriching {len(anomalies)} anomalies with project metadata...")
        
        enriched_count = 0
        for anomaly in anomalies:
            project_id = anomaly.get('project_id')
            
            if project_id and project_id in enrichment_data:
                # Add enrichment fields
                for field, value in enrichment_data[project_id].items():
                    anomaly[field] = value
                enriched_count += 1
            else:
                # Add null values for missing enrichment fields
                for field in config.ENRICHMENT_FIELD_LIST:
                    if field not in anomaly:
                        anomaly[field] = None
        
        logger.info(f"Enriched {enriched_count} out of {len(anomalies)} anomalies")
        return anomalies
    
    def save_anomalies_to_firestore(self, anomalies: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Save anomalies to Firestore.
        
        Args:
            anomalies: List of anomaly dictionaries
            
        Returns:
            Dictionary with save statistics
        """
        logger.info(f"Saving {len(anomalies)} anomalies to Firestore collection: {config.FIRESTORE_COLLECTION}")
        
        if not anomalies:
            logger.warning("No anomalies to save")
            return {'saved_count': 0, 'error_count': 0}
        
        try:
            collection_ref = self.firestore_client.collection(config.FIRESTORE_COLLECTION)
            
            # Batch write to Firestore
            batch = self.firestore_client.batch()
            batch_count = 0
            total_count = 0
            error_count = 0
            
            for anomaly in anomalies:
                try:
                    # Generate document ID from anomaly_id
                    doc_id = anomaly.get('anomaly_id', f"anomaly_{datetime.utcnow().timestamp()}")
                    
                    # Add to batch
                    doc_ref = collection_ref.document(doc_id)
                    batch.set(doc_ref, anomaly, merge=True)
                    batch_count += 1
                    total_count += 1
                    
                    # Commit batch every 500 documents (Firestore limit)
                    if batch_count >= 500:
                        batch.commit()
                        logger.debug(f"Committed batch of {batch_count} documents")
                        batch = self.firestore_client.batch()
                        batch_count = 0
                        
                except Exception as e:
                    logger.error(f"Error preparing anomaly for Firestore: {e}")
                    error_count += 1
            
            # Commit remaining documents
            if batch_count > 0:
                batch.commit()
                logger.debug(f"Committed final batch of {batch_count} documents")
            
            logger.info(f"Saved {total_count} anomalies to Firestore")
            
            # Save metadata
            metadata = {
                'collection_name': config.FIRESTORE_COLLECTION,
                'anomaly_count': total_count,
                'last_updated': datetime.utcnow().isoformat(),
                'environment': config.ENVIRONMENT,
                'enrichment_fields': config.ENRICHMENT_FIELD_LIST,
            }
            
            metadata_ref = self.firestore_client.collection('cost_anomalies_metadata').document('latest')
            metadata_ref.set(metadata)
            
            return {
                'saved_count': total_count,
                'error_count': error_count,
                'metadata': metadata
            }
            
        except exceptions.GoogleAPIError as e:
            logger.error(f"Error saving anomalies to Firestore: {e}")
            raise
    
    def get_anomaly_statistics(self, anomalies: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate statistics about collected anomalies.
        
        Args:
            anomalies: List of anomaly dictionaries
            
        Returns:
            Dictionary with statistics
        """
        if not anomalies:
            return {
                'total_count': 0,
                'by_project': {},
                'by_service': {},
                'by_type': {},
                'total_cost_impact': 0,
            }
        
        stats = {
            'total_count': len(anomalies),
            'by_project': defaultdict(int),
            'by_service': defaultdict(int),
            'by_type': defaultdict(int),
            'by_severity': defaultdict(int),
            'total_cost_impact': 0,
            'enriched_count': 0,
        }
        
        for anomaly in anomalies:
            # Count by project
            project_id = anomaly.get('project_id', 'unknown')
            stats['by_project'][project_id] += 1
            
            # Count by service
            service = anomaly.get('service', 'unknown')
            stats['by_service'][service] += 1
            
            # Count by type
            anomaly_type = anomaly.get('type', 'unknown')
            stats['by_type'][anomaly_type] += 1
            
            # Count by severity
            severity = anomaly.get('severity', 'unknown')
            stats['by_severity'][severity] += 1
            
            # Sum cost impact
            cost_change = anomaly.get('cost_change', 0)
            stats['total_cost_impact'] += abs(cost_change)
            
            # Count enriched anomalies
            if any(anomaly.get(field) for field in config.ENRICHMENT_FIELD_LIST):
                stats['enriched_count'] += 1
        
        # Convert defaultdicts to regular dicts
        stats['by_project'] = dict(stats['by_project'])
        stats['by_service'] = dict(stats['by_service'])
        stats['by_type'] = dict(stats['by_type'])
        stats['by_severity'] = dict(stats['by_severity'])
        
        return stats
    
    def run(self):
        """Main execution method to collect and process cost anomalies."""
        logger.info("=" * 80)
        logger.info("Starting GCP Cost Anomaly Collection")
        logger.info("=" * 80)
        
        try:
            # Get billing accounts
            billing_accounts = self.get_billing_accounts()
            
            if not billing_accounts:
                logger.warning("No billing accounts found to process")
                return
            
            # Load enrichment data
            enrichment_data = self.load_project_enrichment_data()
            
            # Collect anomalies from all billing accounts
            all_anomalies = []
            for billing_account_id in billing_accounts:
                anomalies = self.fetch_anomalies_for_billing_account(
                    billing_account_id,
                    days_back=config.DAYS_BACK
                )
                all_anomalies.extend(anomalies)
            
            logger.info(f"Collected {len(all_anomalies)} total anomalies")
            
            if not all_anomalies:
                logger.info("No anomalies found")
                return
            
            # Enrich anomalies with project metadata
            enriched_anomalies = self.enrich_anomalies(all_anomalies, enrichment_data)
            
            # Generate statistics
            stats = self.get_anomaly_statistics(enriched_anomalies)
            
            logger.info("=" * 80)
            logger.info("Anomaly Statistics:")
            logger.info(f"  Total anomalies: {stats['total_count']}")
            logger.info(f"  Enriched anomalies: {stats['enriched_count']}")
            logger.info(f"  Total cost impact: ${stats['total_cost_impact']:,.2f}")
            logger.info(f"  Unique projects: {len(stats['by_project'])}")
            logger.info(f"  Unique services: {len(stats['by_service'])}")
            logger.info("=" * 80)
            
            # Save to Firestore
            save_result = self.save_anomalies_to_firestore(enriched_anomalies)
            
            logger.info("=" * 80)
            logger.info("Cost Anomaly Collection Completed Successfully!")
            logger.info(f"  Saved: {save_result['saved_count']} anomalies")
            logger.info(f"  Errors: {save_result['error_count']}")
            logger.info("=" * 80)
            
        except Exception as e:
            logger.error(f"Error in anomaly collection: {e}", exc_info=True)
            raise


def main():
    """Entry point for the Cloud Run job."""
    try:
        collector = CostAnomalyCollector()
        collector.run()
        logger.info("Job completed successfully")
        
    except Exception as e:
        logger.error(f"Job failed: {e}", exc_info=True)
        raise


if __name__ == '__main__':
    main()
