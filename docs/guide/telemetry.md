# Telemetry & Observability

spectra includes optional OpenTelemetry and Prometheus support for monitoring sync operations, API calls, and errors in production environments.

## Overview

The telemetry system provides:

- **Distributed tracing** via OpenTelemetry for debugging sync operations
- **Metrics collection** for monitoring sync health and performance
- **Prometheus integration** for scraping metrics into your monitoring stack

::: tip Optional Dependencies
Telemetry requires additional packages. Install with:

```bash
pip install spectra[telemetry]
```

Or install packages individually:

```bash
pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp prometheus-client
```
:::

## Quick Start

### OpenTelemetry

Enable tracing and metrics export to an OTLP collector (Jaeger, Zipkin, etc.):

```bash
# Via CLI flags
spectra --otel-enable --otel-endpoint http://localhost:4317 --markdown EPIC.md --epic PROJ-123

# Via environment variables
export OTEL_ENABLED=true
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
spectra --markdown EPIC.md --epic PROJ-123
```

### Prometheus

Start a Prometheus metrics server:

```bash
# Via CLI flags
spectra --prometheus-enable --prometheus-port 9090 --markdown EPIC.md --epic PROJ-123

# Via environment variables
export PROMETHEUS_ENABLED=true
export PROMETHEUS_PORT=9090
spectra --markdown EPIC.md --epic PROJ-123
```

Then scrape metrics at `http://localhost:9090/metrics`.

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OTEL_ENABLED` | Enable OpenTelemetry | `false` |
| `OTEL_SERVICE_NAME` | Service name for traces/metrics | `spectra` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP collector endpoint | None |
| `OTEL_EXPORTER_OTLP_INSECURE` | Use insecure connection | `true` |
| `OTEL_CONSOLE_EXPORT` | Export to console (debugging) | `false` |
| `OTEL_METRICS_ENABLED` | Enable metrics collection | `true` |
| `PROMETHEUS_ENABLED` | Enable Prometheus server | `false` |
| `PROMETHEUS_PORT` | Prometheus metrics port | `9090` |
| `PROMETHEUS_HOST` | Prometheus bind address | `0.0.0.0` |

### Programmatic Configuration

```python
from spectra.cli.telemetry import (
    TelemetryConfig,
    TelemetryProvider,
    configure_telemetry,
    configure_prometheus,
)

# Configure OpenTelemetry
config = TelemetryConfig(
    enabled=True,
    service_name="spectra",
    service_version="2.0.0",
    otlp_endpoint="http://localhost:4317",
    otlp_insecure=True,
    metrics_enabled=True,
)
provider = TelemetryProvider.configure(config)
provider.initialize()

# Or use convenience functions
configure_telemetry(
    enabled=True,
    endpoint="http://localhost:4317",
    service_name="spectra",
)

# Configure Prometheus
configure_prometheus(
    enabled=True,
    port=9090,
    host="0.0.0.0",
    service_name="spectra",
)
```

## Available Metrics

### OpenTelemetry Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `spectra.sync.total` | Counter | Total sync operations |
| `spectra.sync.duration` | Histogram | Sync duration in seconds |
| `spectra.stories.processed` | Counter | Stories processed |
| `spectra.api.calls` | Counter | API calls made |
| `spectra.api.duration` | Histogram | API call duration in ms |
| `spectra.errors.total` | Counter | Total errors |

### Prometheus Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `spectra_sync_total` | Counter | `epic_key`, `success` | Total sync operations |
| `spectra_sync_duration_seconds` | Histogram | `epic_key` | Sync duration |
| `spectra_stories_processed_total` | Counter | `epic_key`, `operation` | Stories processed |
| `spectra_api_calls_total` | Counter | `operation`, `success` | API calls |
| `spectra_api_duration_milliseconds` | Histogram | `operation` | API duration |
| `spectra_errors_total` | Counter | `error_type`, `operation` | Errors |
| `spectra_active_syncs` | Gauge | - | Currently active syncs |
| `spectra_info` | Gauge | `version`, `service_name` | Service info |

## Tracing

### Using the `@traced` Decorator

Add tracing to your custom functions:

```python
from spectra.cli.telemetry import traced

@traced("custom.operation")
def my_custom_function():
    # Your code here
    pass

@traced("sync.process_story", attributes={"custom": "value"})
def process_story(story_id: str):
    # Traced with custom attributes
    pass
```

### Using the Context Manager

For more control over spans:

```python
from spectra.cli.telemetry import get_telemetry

telemetry = get_telemetry()

with telemetry.span("my.operation", attributes={"story_id": "US-001"}) as span:
    # Your code here
    if span:
        span.set_attribute("result", "success")
```

### Timed API Calls

Automatically time and record API call metrics:

```python
from spectra.cli.telemetry import timed_api_call

@timed_api_call("get_issue")
def get_issue(key: str):
    # API call is timed and recorded
    return api.get_issue(key)
```

## Recording Custom Metrics

```python
from spectra.cli.telemetry import get_telemetry

telemetry = get_telemetry()

# Record a sync operation
telemetry.record_sync(
    success=True,
    duration_seconds=5.2,
    stories_count=10,
    epic_key="PROJ-123",
)

# Record an API call
telemetry.record_api_call(
    operation="create_subtask",
    success=True,
    duration_ms=150.5,
    endpoint="/rest/api/3/issue",
)

# Record an error
telemetry.record_error(
    error_type="AuthenticationError",
    operation="sync",
)
```

## Deployment Examples

### Docker Compose with Jaeger

```yaml
version: '3.8'

services:
  spectra:
    image: adriandarian/spectra:latest
    environment:
      OTEL_ENABLED: "true"
      OTEL_EXPORTER_OTLP_ENDPOINT: "http://jaeger:4317"
      JIRA_URL: ${JIRA_URL}
      JIRA_EMAIL: ${JIRA_EMAIL}
      JIRA_API_TOKEN: ${JIRA_API_TOKEN}
    depends_on:
      - jaeger

  jaeger:
    image: jaegertracing/all-in-one:latest
    ports:
      - "16686:16686"  # Jaeger UI
      - "4317:4317"    # OTLP gRPC
```

### Docker Compose with Prometheus + Grafana

```yaml
version: '3.8'

services:
  spectra:
    image: adriandarian/spectra:latest
    environment:
      PROMETHEUS_ENABLED: "true"
      PROMETHEUS_PORT: "9090"
      JIRA_URL: ${JIRA_URL}
      JIRA_EMAIL: ${JIRA_EMAIL}
      JIRA_API_TOKEN: ${JIRA_API_TOKEN}
    ports:
      - "9090:9090"

  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9091:9090"

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    depends_on:
      - prometheus
```

**prometheus.yml:**

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'spectra'
    static_configs:
      - targets: ['spectra:9090']
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: spectra
spec:
  template:
    spec:
      containers:
        - name: spectra
          image: adriandarian/spectra:latest
          env:
            - name: OTEL_ENABLED
              value: "true"
            - name: OTEL_EXPORTER_OTLP_ENDPOINT
              value: "http://otel-collector.monitoring:4317"
            - name: PROMETHEUS_ENABLED
              value: "true"
            - name: PROMETHEUS_PORT
              value: "9090"
          ports:
            - containerPort: 9090
              name: metrics
---
apiVersion: v1
kind: Service
metadata:
  name: spectra
  labels:
    app: spectra
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/port: "9090"
spec:
  ports:
    - port: 9090
      name: metrics
  selector:
    app: spectra
```

## Grafana Dashboard

Here's a sample Grafana dashboard configuration for monitoring spectra:

```json
{
  "title": "spectra Sync Metrics",
  "panels": [
    {
      "title": "Sync Operations",
      "type": "stat",
      "targets": [
        {
          "expr": "sum(spectra_sync_total)",
          "legendFormat": "Total Syncs"
        }
      ]
    },
    {
      "title": "Sync Success Rate",
      "type": "gauge",
      "targets": [
        {
          "expr": "sum(spectra_sync_total{success=\"true\"}) / sum(spectra_sync_total) * 100"
        }
      ]
    },
    {
      "title": "Sync Duration (p95)",
      "type": "timeseries",
      "targets": [
        {
          "expr": "histogram_quantile(0.95, rate(spectra_sync_duration_seconds_bucket[5m]))"
        }
      ]
    },
    {
      "title": "API Calls by Operation",
      "type": "piechart",
      "targets": [
        {
          "expr": "sum by (operation) (spectra_api_calls_total)"
        }
      ]
    },
    {
      "title": "Errors by Type",
      "type": "table",
      "targets": [
        {
          "expr": "sum by (error_type, operation) (spectra_errors_total)"
        }
      ]
    }
  ]
}
```

## Alerting Rules

Example Prometheus alerting rules:

```yaml
groups:
  - name: spectra
    rules:
      - alert: SpectraSyncFailureRate
        expr: |
          sum(rate(spectra_sync_total{success="false"}[5m]))
          / sum(rate(spectra_sync_total[5m])) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High sync failure rate"
          description: "More than 10% of syncs are failing"

      - alert: SpectraHighApiLatency
        expr: |
          histogram_quantile(0.95, rate(spectra_api_duration_milliseconds_bucket[5m])) > 5000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High API latency"
          description: "95th percentile API latency is above 5 seconds"

      - alert: SpectraErrors
        expr: increase(spectra_errors_total[1h]) > 10
        labels:
          severity: critical
        annotations:
          summary: "spectra error spike"
          description: "More than 10 errors in the last hour"
```

## Troubleshooting

### Telemetry Not Working

1. **Check dependencies are installed:**
   ```bash
   pip install spectra[telemetry]
   ```

2. **Verify configuration:**
   ```bash
   OTEL_ENABLED=true OTEL_CONSOLE_EXPORT=true spectra --validate --markdown EPIC.md
   ```

3. **Check collector connectivity:**
   ```bash
   curl -v http://localhost:4317
   ```

### Prometheus Metrics Not Appearing

1. **Verify server is running:**
   ```bash
   curl http://localhost:9090/metrics
   ```

2. **Check firewall/network settings**

3. **Verify Prometheus scrape config targets the correct endpoint**

### High Memory Usage

If telemetry causes high memory usage:

1. Reduce metric cardinality by limiting labels
2. Decrease the metric export interval
3. Consider using sampling for traces

## See Also

- [Configuration](/guide/configuration) – General configuration options
- [Docker](/guide/docker) – Running spectra in containers
- [Architecture](/guide/architecture) – System design overview


