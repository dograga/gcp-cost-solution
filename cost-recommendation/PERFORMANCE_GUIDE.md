# Performance Optimization Guide

## Overview

This guide explains how to optimize the cost recommendation collector for large-scale deployments (100+ projects).

## Key Optimizations Implemented

### 1. **Parallel Processing**
- Uses `ThreadPoolExecutor` to process multiple projects concurrently
- Configurable worker threads via `MAX_WORKERS` environment variable
- **Recommended**: 10-20 workers for 100+ projects

### 2. **Streaming Writes**
- Saves recommendations to Firestore **immediately** after each project completes
- Avoids accumulating all data in memory
- Reduces memory footprint from ~100MB+ to ~10MB for 100 projects

### 3. **Batch Writes**
- Uses Firestore batch writes (configurable via `FIRESTORE_BATCH_SIZE`)
- Default: 500 operations per batch (Firestore maximum)
- Reduces write operations and improves throughput

### 4. **Reduced Logging**
- Changed verbose logs to DEBUG level
- Progress updates every 10 projects instead of every project
- Includes ETA and processing rate metrics

### 5. **Inventory-Based Discovery**
- Reads project list from Firestore instead of API calls
- Eliminates Resource Manager API latency
- Faster startup time

## Configuration

### Environment Variables

```bash
# Performance Configuration
MAX_WORKERS=15                    # Number of parallel threads
FIRESTORE_BATCH_SIZE=500          # Batch size for Firestore writes
LOG_LEVEL=INFO                    # Use INFO for production

# Inventory (faster than API)
USE_INVENTORY_COLLECTION=true
INVENTORY_DATABASE=dashboard
INVENTORY_COLLECTION=projects
```

## Performance Benchmarks

### Expected Performance (approximate)

| Projects | Workers | Time (minutes) | Notes |
|----------|---------|----------------|-------|
| 10       | 5       | 2-3            | Small batch |
| 50       | 10      | 8-12           | Medium batch |
| 100      | 15      | 15-20          | Large batch |
| 200      | 20      | 30-40          | Very large |

**Factors affecting performance:**
- Number of recommender types enabled
- Number of locations checked (regions + zones)
- API rate limits
- Network latency
- Number of recommendations per project

## Tuning Guidelines

### For 100+ Projects

1. **Set MAX_WORKERS to 15-20**
   ```bash
   MAX_WORKERS=15
   ```

2. **Use INFO logging**
   ```bash
   LOG_LEVEL=INFO
   ```

3. **Enable inventory collection**
   ```bash
   USE_INVENTORY_COLLECTION=true
   ```

4. **Optimize locations** (if you know your resources are in specific regions)
   - Edit `main.py` line ~240 to include only relevant regions/zones
   - Fewer locations = faster processing

### For 200+ Projects

1. **Increase workers**
   ```bash
   MAX_WORKERS=20
   ```

2. **Consider splitting into multiple jobs**
   - Split projects into batches
   - Run multiple Cloud Run jobs in parallel
   - Each job processes a subset of projects

### Cloud Run Configuration

For optimal performance, configure your Cloud Run job:

```yaml
# Cloud Run Job Configuration
resources:
  limits:
    cpu: "4"           # 4 vCPUs for parallel processing
    memory: "2Gi"      # 2GB RAM (sufficient for streaming writes)
timeout: 3600s         # 60 minutes timeout for 100+ projects
```

## Monitoring

The collector logs provide real-time metrics:

```
Progress: 50/100 projects (50%) | Rate: 2.5 projects/sec | ETA: 3.3 min
```

**Metrics:**
- **Progress**: Projects completed / total
- **Rate**: Projects processed per second
- **ETA**: Estimated time to completion

## Memory Optimization

### Before Optimization
- Accumulated all recommendations in memory
- Memory usage: ~1MB per project × 100 = 100MB+
- Risk of OOM for large batches

### After Optimization
- Streams recommendations to Firestore immediately
- Memory usage: ~10MB constant (regardless of project count)
- Can handle 500+ projects without memory issues

## API Rate Limits

### Recommender API Limits
- **Default**: 600 requests per minute per project
- **With 15 workers**: ~150 requests/min (well within limits)
- **Recommendation**: Stay under 20 workers to avoid rate limiting

### Firestore Limits
- **Writes**: 10,000 per second (far exceeds our needs)
- **Batch writes**: 500 operations per batch
- **No rate limit concerns** for this use case

## Troubleshooting

### Slow Performance

1. **Check worker count**
   - Too few workers = slow processing
   - Too many workers = API rate limiting

2. **Check network latency**
   - Run from Cloud Run (same region as Firestore)
   - Avoid running from local machine

3. **Check recommender types**
   - More types = more API calls
   - Consider filtering to cost-related types only

### Memory Issues

1. **Verify streaming writes are working**
   - Check logs for "Successfully saved X recommendations"
   - Should appear after each project, not at the end

2. **Reduce worker count**
   - Each worker holds some data in memory
   - Reduce if seeing OOM errors

### API Rate Limiting

If you see rate limit errors:

1. **Reduce MAX_WORKERS**
   ```bash
   MAX_WORKERS=10
   ```

2. **Add retry logic** (already implemented via Google client libraries)

## Best Practices

1. ✅ **Use inventory collection** for project discovery
2. ✅ **Set LOG_LEVEL=INFO** for production
3. ✅ **Use 15 workers** for 100 projects
4. ✅ **Run as Cloud Run job** (not local)
5. ✅ **Monitor progress logs** for ETA
6. ✅ **Set appropriate timeout** (60 min for 100+ projects)

## Cost Optimization

### API Costs
- Recommender API: **Free** (no charges)
- Resource Manager API: **Free** (minimal usage)
- Firestore: ~$0.18 per 100K writes

### Compute Costs
- Cloud Run: ~$0.10 per hour (4 vCPU)
- For 100 projects @ 20 min: ~$0.03 per run
- Daily runs: ~$1/month

**Total estimated cost for 100 projects with daily runs: ~$1-2/month**
