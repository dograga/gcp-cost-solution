"""Client for Security Center Management API"""

import logging
from typing import List, Dict, Any, AsyncIterator
from google.cloud import securitycentermanagement_v1
from config import get_settings

logger = logging.getLogger(__name__)

class SCCManagementClient:
    """Client for interacting with Security Center Management API"""
    
    def __init__(self):
        self.settings = get_settings()
        self.client = securitycentermanagement_v1.SecurityCenterManagementClient()
        
        # Construct parent dynamically based on settings
        scope_type = self.settings.ingestion_scope_type.lower()
        scope_id = self.settings.ingestion_scope_id
        
        # Ensure scope type is pluralized correctly
        if not scope_type.endswith('s'):
            scope_type += 's'
            
        self.parent = f"{scope_type}/{scope_id}/locations/global"
        logger.info(f"Initialized SCC Management client for parent: {self.parent}")
    
    async def list_effective_sha_custom_modules(self) -> AsyncIterator[Dict[str, Any]]:
        """
        List effective Security Health Analytics custom modules.
        
        Yields:
            Dictionary containing module data
        """
        request = securitycentermanagement_v1.ListEffectiveSecurityHealthAnalyticsCustomModulesRequest(
            parent=self.parent,
            page_size=500
        )
        
        logger.info(f"Listing effective SHA custom modules from: {self.parent}")
        
        try:
            # Client is synchronous
            response = self.client.list_effective_security_health_analytics_custom_modules(request=request)
            
            count = 0
            for module in response:
                count += 1
                
                # Extract relevant data
                # CustomConfig is a protobuf message, need to access attributes directly
                custom_config_data = {}
                if module.custom_config:
                    custom_config_data = {
                        "severity": module.custom_config.severity.name if hasattr(module.custom_config.severity, 'name') else str(module.custom_config.severity),
                        "description": module.custom_config.description,
                        "recommendation": module.custom_config.recommendation,
                        "predicate": str(module.custom_config.predicate)
                    }

                module_data = {
                    "name": module.name,
                    "display_name": module.display_name,
                    "custom_config": custom_config_data,
                    "enablement_state": module.enablement_state.name,
                    "type": "sha_custom_module"
                }
                
                yield module_data
                
            logger.info(f"Found {count} effective SHA custom modules")
            
        except Exception as e:
            logger.error(f"Error listing SHA custom modules: {e}")
            # Don't raise, just log, as this might fail if API is not enabled or no modules exist
            # raise e 
