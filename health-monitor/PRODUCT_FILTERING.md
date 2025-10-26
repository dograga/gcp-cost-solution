# Product/Service Filtering Feature

## Overview

The health monitor now supports filtering events by GCP products/services in addition to region filtering. This allows you to monitor only the services that are relevant to your infrastructure.

## Configuration

### Environment Variables

Add these variables to your `.env.dev` or `.env.prod` file:

```bash
# Enable/disable product filtering
FILTER_BY_PRODUCT=True

# List of products to monitor (only used when FILTER_BY_PRODUCT=True)
PRODUCTS=Google Compute Engine,Google Kubernetes Engine,Cloud Storage,Cloud SQL,Cloud Networking,Cloud Security,Cloud Logging,Cloud DNS,Vertex AI,Cloud Identity,Cloud Billing,Cloud Pub/Sub,Cloud Memorystore,BigQuery,Cloud Dataproc
```

### FILTER_BY_PRODUCT Flag

- **`True`**: Enable product filtering - only monitor events for products listed in `PRODUCTS`
- **`False`**: Disable product filtering - monitor all products regardless of `PRODUCTS` list

### Monitored Services

The following services are configured by default:

1. **Google Compute Engine** - Compute VMs and instances
2. **Google Kubernetes Engine** - GKE clusters
3. **Cloud Storage** - Object storage buckets
4. **Cloud SQL** - Managed database instances
5. **Cloud Networking** - VPC, Load Balancers, networking services
6. **Cloud Security** - Security and compliance services
7. **Cloud Logging** - Logging and monitoring
8. **Cloud DNS** - DNS management
9. **Vertex AI** - AI/ML platform
10. **Cloud Identity** - Identity and access management
11. **Cloud Billing** - Billing services
12. **Cloud Pub/Sub** - Messaging and event streaming
13. **Cloud Memorystore** - Redis managed service
14. **BigQuery** - Data warehouse and analytics
15. **Cloud Dataproc** - Spark and Hadoop clusters

## How It Works

### Filtering Logic

1. **Region Filter**: Events must affect one of the monitored regions
2. **Product Filter**: If `FILTER_BY_PRODUCT=True`, events must affect at least one monitored product
3. **Flexible Matching**: Product names are matched case-insensitively with partial matching
   - Example: "Cloud Storage" will match "Google Cloud Storage" or "Cloud Storage API"

### Filter Behavior

- **`FILTER_BY_PRODUCT=False`**: All products are monitored (no filtering), `PRODUCTS` list is ignored
- **`FILTER_BY_PRODUCT=True`**: Only events affecting products in the `PRODUCTS` list are collected
- **Combined Filters**: Events must pass BOTH region AND product filters (when enabled) to be included
- **Partial Matches**: The system uses flexible matching to handle variations in product names

## Code Changes

### Files Modified

1. **`.env.dev`** - Added `PRODUCTS` configuration
2. **`config.py`** - Added `PRODUCTS` loading and parsing
3. **`main.py`** - Added product filtering logic:
   - `_should_include_event()` - Updated to check both region and product filters
   - `_matches_region_filter()` - Extracted region filtering logic
   - `_matches_product_filter()` - New method for product filtering
4. **`README.md`** - Updated documentation with product filtering details

### Key Methods

#### `_matches_product_filter(event_record)`

Checks if an event matches the product filter by:
1. Extracting products from event impacts
2. Comparing against monitored products list
3. Using case-insensitive partial matching

```python
def _matches_product_filter(self, event_record: Dict[str, Any]) -> bool:
    event_impacts = event_record.get('impacts', [])
    
    if not event_impacts:
        return False
    
    for impact in event_impacts:
        product = impact.get('product')
        if not product:
            continue
        
        product_lower = product.lower()
        for monitored_product in self.products:
            monitored_lower = monitored_product.lower()
            if monitored_lower in product_lower or product_lower in monitored_lower:
                return True
    
    return False
```

## Testing

To test the product filtering:

1. **Monitor specific products**:
   ```bash
   PRODUCTS=Google Compute Engine,Cloud Storage
   python main.py
   ```

2. **Monitor all products** (no filtering):
   ```bash
   PRODUCTS=
   python main.py
   ```

3. **Check logs** for filtering information:
   ```
   INFO - Monitoring products: ['Google Compute Engine', 'Cloud Storage', ...]
   DEBUG - Collected event: abc123 - Service Disruption in asia-southeast1
   ```

## Examples

### Example 1: Monitor Only Compute and Storage

```bash
FILTER_BY_PRODUCT=True
PRODUCTS=Google Compute Engine,Cloud Storage
REGIONS=asia-southeast1,global
```

This will only collect events that:
- Affect Compute Engine OR Cloud Storage
- AND affect asia-southeast1 OR global regions

### Example 2: Monitor All Services in Specific Regions

```bash
FILTER_BY_PRODUCT=False
PRODUCTS=Google Compute Engine,Cloud Storage
REGIONS=asia-southeast1,asia-southeast2
```

This will collect all events affecting Singapore and Jakarta regions, regardless of product (PRODUCTS list is ignored).

### Example 3: Monitor Specific Services Globally

```bash
FILTER_BY_PRODUCT=True
PRODUCTS=Cloud SQL,BigQuery,Cloud Dataproc
REGIONS=global
```

This will only collect global events affecting databases and data processing services.

### Example 4: Temporarily Disable Product Filtering

```bash
FILTER_BY_PRODUCT=False
PRODUCTS=Google Compute Engine,Cloud Storage,Cloud SQL
REGIONS=asia-southeast1,global
```

This keeps your product list configured but disables filtering, monitoring all products.

## Troubleshooting

### No Events Collected

1. **Check product names**: Ensure product names match GCP's naming conventions
2. **Check logs**: Look for "Monitoring products: ..." in startup logs
3. **Verify impacts**: Events must have product information in their impacts

### Too Many/Few Events

1. **Check filter status**: Verify `FILTER_BY_PRODUCT` is set correctly (True/False)
2. **Adjust product list**: Add or remove products from `PRODUCTS`
3. **Check partial matching**: Remember that "Cloud" will match many services
4. **Use specific names**: Use full product names for precise filtering
5. **Temporarily disable**: Set `FILTER_BY_PRODUCT=False` to see all events

### Product Name Variations

GCP may use different names for the same service. Common variations:
- "Google Compute Engine" vs "Compute Engine"
- "Cloud Storage" vs "Google Cloud Storage"
- "BigQuery" vs "Google BigQuery"

The flexible matching handles most variations automatically.

## Best Practices

1. ✅ **Start disabled**: Begin with `FILTER_BY_PRODUCT=False` to see all events
2. ✅ **Identify critical services**: Review events to identify which services matter most
3. ✅ **Enable gradually**: Set `FILTER_BY_PRODUCT=True` and add critical services to `PRODUCTS`
4. ✅ **Monitor critical services**: Focus on services critical to your infrastructure
5. ✅ **Review regularly**: Periodically review collected events and adjust filters
6. ✅ **Use specific names**: Use official GCP product names for better matching
7. ✅ **Test in dev**: Test product filtering in development before deploying to production
8. ✅ **Easy toggle**: Keep your `PRODUCTS` list configured so you can easily toggle filtering on/off

## Migration

If you're upgrading from a version without product filtering:

1. **No action required**: Product filtering is disabled by default (`FILTER_BY_PRODUCT=False`)
2. **Backward compatible**: Existing behavior is maintained unless you enable filtering
3. **Add configuration**: Add `FILTER_BY_PRODUCT=False` to maintain current behavior explicitly
4. **Enable when ready**: Set `FILTER_BY_PRODUCT=True` and configure `PRODUCTS` when ready to filter events
