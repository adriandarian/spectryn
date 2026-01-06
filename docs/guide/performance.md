# Performance Tuning Guide

Optimize spectra for large-scale projects with thousands of stories.

## Performance Overview

spectra is designed to handle large workloads efficiently. This guide covers:
- Parallel processing configuration
- Caching strategies
- Network optimization
- Memory management
- Monitoring and profiling

---

## Quick Wins

### 1. Enable Parallel Processing

```yaml
# spectra.yaml
performance:
  parallel_sync: true
  max_workers: 4  # Adjust based on CPU cores
```

```bash
# Or via CLI
spectra sync --parallel --workers 4 --markdown EPIC.md
```

**Impact:** 3-4x faster for large epics with many stories.

---

### 2. Use Incremental Sync

Only sync changed items instead of everything:

```bash
# Sync only changed stories
spectra sync --incremental --markdown EPIC.md

# Check what would be synced
spectra diff --markdown EPIC.md --epic PROJ-123
```

**Impact:** 10-50x faster for subsequent syncs.

---

### 3. Enable Caching

```yaml
# spectra.yaml
cache:
  enabled: true
  ttl: 3600  # 1 hour
  backend: memory  # or "redis" for multi-process
```

**Cached data:**
- Project metadata (issue types, statuses, fields)
- User lists
- Recently accessed issues
- Schema validation results

**Impact:** Reduces API calls by 40-60%.

---

## Configuration Reference

### Full Performance Configuration

```yaml
# spectra.yaml
performance:
  # Parallel processing
  parallel_sync: true
  max_workers: 4

  # Batching
  batch_size: 50
  batch_delay_ms: 100

  # Rate limiting
  rate_limit: 100  # requests per second
  rate_limit_burst: 20

  # Timeouts
  request_timeout: 30
  connect_timeout: 10

  # Memory
  max_memory_mb: 512
  streaming_threshold_mb: 10

cache:
  enabled: true
  backend: memory  # memory, file, redis
  ttl: 3600
  max_size: 1000

  # Redis settings (if backend: redis)
  redis:
    url: redis://localhost:6379
    db: 0
    prefix: spectra:

network:
  # Connection pooling
  pool_size: 10
  pool_maxsize: 20
  pool_block: false

  # Retries
  max_retries: 3
  retry_backoff: exponential
  retry_backoff_factor: 0.5
```

---

## Parallel Processing

### How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                    Main Process                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                  Thread Pool                            │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │ │
│  │  │ Worker 1 │ │ Worker 2 │ │ Worker 3 │ │ Worker 4 │   │ │
│  │  │ Epic A   │ │ Epic B   │ │ Story 1  │ │ Story 2  │   │ │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Tuning Workers

| System | Recommended Workers |
|--------|---------------------|
| 2 cores | 2-3 |
| 4 cores | 4-6 |
| 8+ cores | 6-8 |

::: warning
More workers ≠ faster. Too many workers can cause:
- Rate limiting from APIs
- Memory exhaustion
- Context switching overhead
:::

### Per-Tracker Limits

Different trackers have different rate limits:

```yaml
# spectra.yaml
trackers:
  jira:
    rate_limit: 100  # Jira Cloud: ~100 req/s
    max_workers: 4

  github:
    rate_limit: 30   # GitHub: 5000/hour ≈ 83/min
    max_workers: 2

  linear:
    rate_limit: 60   # Linear: ~60 req/s
    max_workers: 3
```

---

## Caching Strategies

### Memory Cache (Default)

Best for single-process usage:

```yaml
cache:
  backend: memory
  ttl: 3600
  max_size: 1000
```

**Pros:** Fast, no setup
**Cons:** Lost on restart, not shared between processes

---

### File Cache

Persists between runs:

```yaml
cache:
  backend: file
  path: .spectra/cache
  ttl: 86400  # 24 hours
```

**Pros:** Survives restarts, simple
**Cons:** Slower than memory, single machine

---

### Redis Cache

Best for CI/CD and multi-instance:

```yaml
cache:
  backend: redis
  redis:
    url: redis://localhost:6379
    db: 0
    prefix: spectra:
    ttl: 3600
```

```bash
# Docker Redis for local development
docker run -d -p 6379:6379 redis:alpine
```

**Pros:** Shared across processes/machines, fast
**Cons:** Requires Redis setup

---

### Cache Invalidation

```bash
# Clear all caches
spectra cache clear

# Clear specific cache
spectra cache clear --type metadata

# Clear for specific project
spectra cache clear --project PROJ
```

---

## Network Optimization

### Connection Pooling

Reuse HTTP connections for better performance:

```yaml
network:
  pool_size: 10       # Initial connections
  pool_maxsize: 20    # Maximum connections
  pool_block: false   # Don't block when pool exhausted
```

### Timeout Configuration

```yaml
network:
  connect_timeout: 10  # Connection establishment
  request_timeout: 30  # Full request completion
  read_timeout: 60     # For large responses
```

### Retry Strategy

```yaml
network:
  max_retries: 3
  retry_backoff: exponential  # exponential, linear, constant
  retry_backoff_factor: 0.5
  retry_on:
    - 429  # Rate limited
    - 500  # Server error
    - 502  # Bad gateway
    - 503  # Service unavailable
```

---

## Memory Management

### Streaming Parser

For very large markdown files (>10MB):

```yaml
performance:
  streaming_threshold_mb: 10
  chunk_size_kb: 64
```

```bash
# Force streaming mode
spectra sync --streaming --markdown huge-epic.md
```

### Memory Limits

```yaml
performance:
  max_memory_mb: 512
```

When limit is approached:
1. Caches are cleared
2. Processing switches to streaming mode
3. Batch sizes are reduced

---

## Batching Operations

### Batch Sync

Process stories in batches to optimize API calls:

```yaml
performance:
  batch_size: 50
  batch_delay_ms: 100  # Pause between batches
```

```bash
# Explicit batch mode
spectra sync --batch --batch-size 100 --markdown EPIC.md
```

### GraphQL Batching

For GitHub and Linear, batch multiple queries:

```yaml
github:
  graphql_batch: true
  graphql_batch_size: 20

linear:
  graphql_batch: true
  graphql_batch_size: 50
```

---

## Monitoring & Profiling

### Built-in Stats

```bash
# Show sync statistics
spectra stats --markdown EPIC.md

# Output:
# Stories: 150
# Subtasks: 423
# API calls: 45
# Cache hits: 312 (87%)
# Duration: 12.3s
# Throughput: 12.2 stories/s
```

### Detailed Timing

```bash
# Enable timing breakdown
spectra sync --verbose --timing --markdown EPIC.md

# Output:
# Parse markdown: 0.2s
# Fetch tracker state: 2.1s
# Diff calculation: 0.1s
# Create stories: 4.5s
# Update subtasks: 3.2s
# Total: 10.1s
```

### Profiling

```bash
# Profile CPU usage
python -m cProfile -o profile.out -m spectra sync --markdown EPIC.md
python -m pstats profile.out

# Profile memory
python -m memory_profiler -m spectra sync --markdown EPIC.md
```

---

## Benchmarks

### Test Your Setup

```bash
# Run benchmark suite
spectra benchmark --stories 100 --subtasks 500

# Output:
# Benchmark Results
# ─────────────────
# Parse (100 stories): 45ms
# Diff (100 stories): 12ms
# Serialize (100 stories): 8ms
# Full sync (dry-run): 1.2s
# Estimated real sync: 8.5s
```

### Reference Benchmarks

| Operation | 100 stories | 1000 stories | 5000 stories |
|-----------|-------------|--------------|--------------|
| Parse | 45ms | 350ms | 1.8s |
| Diff | 12ms | 95ms | 450ms |
| Sync (parallel) | 8s | 45s | 3.5min |
| Sync (sequential) | 25s | 4min | 20min |

*Tested on M1 MacBook Pro, Jira Cloud, 50ms latency*

---

## Environment-Specific Tuning

### CI/CD Pipelines

```yaml
# spectra.yaml for CI
performance:
  parallel_sync: true
  max_workers: 2  # CI runners often have 2 cores

cache:
  backend: file
  path: /tmp/spectra-cache
  ttl: 300  # 5 minutes (single pipeline)
```

### Local Development

```yaml
# spectra.yaml for development
performance:
  parallel_sync: true
  max_workers: 4

cache:
  backend: memory
  ttl: 3600
```

### Production Server

```yaml
# spectra.yaml for server deployment
performance:
  parallel_sync: true
  max_workers: 8
  max_memory_mb: 2048

cache:
  backend: redis
  redis:
    url: ${REDIS_URL}
    prefix: spectra:prod:
```

---

## Troubleshooting Performance

### Identifying Bottlenecks

```bash
# Detailed diagnostics
spectra doctor --performance

# Output:
# Performance Diagnostics
# ─────────────────────────
# ✓ Python version: 3.11.5 (optimal)
# ✓ Available memory: 8GB
# ✓ CPU cores: 4
# ✓ Network latency to Jira: 45ms
# ⚠ Cache backend: memory (consider redis for CI)
# ✓ Connection pool: healthy
```

### Common Issues

| Symptom | Cause | Solution |
|---------|-------|----------|
| Sync takes >1min for 50 stories | Sequential processing | Enable `parallel_sync` |
| High API call count | No caching | Enable cache |
| Memory spikes | Large files | Enable streaming |
| Rate limit errors | Too many workers | Reduce workers |
| Timeouts | Network issues | Increase timeouts |

---

## Best Practices

::: tip Recommended Setup
1. **Enable parallel processing** with 4 workers
2. **Enable caching** (memory for local, Redis for CI)
3. **Use incremental sync** after initial sync
4. **Set appropriate rate limits** per tracker
5. **Monitor with `--timing`** flag periodically
:::

::: warning Avoid
- Running >8 workers (diminishing returns)
- Disabling retries (transient failures happen)
- Very large batch sizes (>200)
- Ignoring rate limit warnings
:::
