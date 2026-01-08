# Telemetry & Observability

spectryn includes optional OpenTelemetry and Prometheus support for monitoring sync operations, API calls, and errors in production environments.

## Overview

The telemetry system provides:

- **Distributed tracing** via OpenTelemetry for debugging sync operations
- **Metrics collection** for monitoring sync health and performance
- **Prometheus integration** for scraping metrics into your monitoring stack

::: tip Optional Dependencies
Telemetry requires additional packages. Install with:

```bash
pip install spectryn[telemetry]
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
spectryn --otel-enable --otel-endpoint http://localhost:4317 --markdown EPIC.md --epic PROJ-123

# Via environment variables
export OTEL_ENABLED=true
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
spectryn --markdown EPIC.md --epic PROJ-123
```

### Prometheus

Start a Prometheus metrics server:

```bash
# Via CLI flags
spectryn --prometheus-enable --prometheus-port 9090 --markdown EPIC.md --epic PROJ-123

# Via environment variables
export PROMETHEUS_ENABLED=true
export PROMETHEUS_PORT=9090
spectryn --markdown EPIC.md --epic PROJ-123
```

Then scrape metrics at `http://localhost:9090/metrics`.

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OTEL_ENABLED` | Enable OpenTelemetry | `false` |
| `OTEL_SERVICE_NAME` | Service name for traces/metrics | `spectryn` |
| `OTEL_SERVICE_VERSION` | Service version for traces/metrics | `2.0.0` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP collector endpoint | None |
| `OTEL_EXPORTER_OTLP_INSECURE` | Use insecure connection | `true` |
| `OTEL_EXPORTER_OTLP_HEADERS` | Additional headers (comma-separated key=value pairs) | None |
| `OTEL_CONSOLE_EXPORT` | Export to console (debugging) | `false` |
| `OTEL_METRICS_ENABLED` | Enable metrics collection | `true` |
| `PROMETHEUS_ENABLED` | Enable Prometheus server | `false` |
| `PROMETHEUS_PORT` | Prometheus metrics port | `9090` |
| `PROMETHEUS_HOST` | Prometheus bind address | `0.0.0.0` |

### Export Configuration

#### OTLP Export (OpenTelemetry Protocol)

The OTLP exporter sends traces and metrics to an OpenTelemetry Collector or compatible backend (Jaeger, Zipkin, Datadog, etc.).

**Basic Configuration:**
```bash
export OTEL_ENABLED=true
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
spectryn --markdown EPIC.md --epic PROJ-123
```

**With Authentication Headers:**
```bash
export OTEL_ENABLED=true
export OTEL_EXPORTER_OTLP_ENDPOINT=https://api.datadoghq.com
export OTEL_EXPORTER_OTLP_HEADERS="DD-API-KEY=your-key,DD-SITE=datadoghq.com"
export OTEL_EXPORTER_OTLP_INSECURE=false
spectryn --markdown EPIC.md --epic PROJ-123
```

**Via CLI Flags:**
```bash
spectryn --otel-enable \
  --otel-endpoint http://localhost:4317 \
  --otel-service-name my-spectryn-instance \
  --markdown EPIC.md --epic PROJ-123
```

#### Prometheus Export

Prometheus metrics are exposed via HTTP on the configured port. The metrics endpoint is available at `/metrics`.

**Basic Configuration:**
```bash
export PROMETHEUS_ENABLED=true
export PROMETHEUS_PORT=9090
spectryn --markdown EPIC.md --epic PROJ-123
```

**Via CLI Flags:**
```bash
spectryn --prometheus \
  --prometheus-port 9090 \
  --prometheus-host 0.0.0.0 \
  --markdown EPIC.md --epic PROJ-123
```

**Accessing Metrics:**
```bash
curl http://localhost:9090/metrics
```

#### Console Export (Debugging)

For local development and debugging, you can export traces and metrics to the console:

```bash
export OTEL_ENABLED=true
export OTEL_CONSOLE_EXPORT=true
spectryn --markdown EPIC.md --epic PROJ-123
```

Or via CLI:
```bash
spectryn --otel-enable --otel-console --markdown EPIC.md --epic PROJ-123
```

### Programmatic Configuration

```python
from spectryn.cli.telemetry import (
    TelemetryConfig,
    TelemetryProvider,
    configure_telemetry,
    configure_prometheus,
)

# Configure OpenTelemetry
config = TelemetryConfig(
    enabled=True,
    service_name="spectryn",
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
    service_name="spectryn",
)

# Configure Prometheus
configure_prometheus(
    enabled=True,
    port=9090,
    host="0.0.0.0",
    service_name="spectryn",
)
```

## Available Metrics

### OpenTelemetry Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `spectryn.sync.total` | Counter | Total sync operations |
| `spectryn.sync.duration` | Histogram | Sync duration in seconds |
| `spectryn.stories.processed` | Counter | Stories processed |
| `spectryn.api.calls` | Counter | API calls made |
| `spectryn.api.duration` | Histogram | API call duration in ms |
| `spectryn.errors.total` | Counter | Total errors |

### Prometheus Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `spectryn_sync_total` | Counter | `epic_key`, `success` | Total sync operations |
| `spectryn_sync_duration_seconds` | Histogram | `epic_key` | Sync duration |
| `spectryn_stories_processed_total` | Counter | `epic_key`, `operation` | Stories processed |
| `spectryn_api_calls_total` | Counter | `operation`, `success` | API calls |
| `spectryn_api_duration_milliseconds` | Histogram | `operation` | API duration |
| `spectryn_errors_total` | Counter | `error_type`, `operation` | Errors |
| `spectryn_active_syncs` | Gauge | - | Currently active syncs |
| `spectryn_info` | Gauge | `version`, `service_name` | Service info |

## Tracing

### Using the `@traced` Decorator

Add tracing to your custom functions:

```python
from spectryn.cli.telemetry import traced

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
from spectryn.cli.telemetry import get_telemetry

telemetry = get_telemetry()

with telemetry.span("my.operation", attributes={"story_id": "STORY-001"}) as span:
    # Your code here
    if span:
        span.set_attribute("result", "success")
```

### Timed API Calls

Automatically time and record API call metrics:

```python
from spectryn.cli.telemetry import timed_api_call

@timed_api_call("get_issue")
def get_issue(key: str):
    # API call is timed and recorded
    return api.get_issue(key)
```

## Recording Custom Metrics

```python
from spectryn.cli.telemetry import get_telemetry

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
  spectryn:
    image: adriandarian/spectryn:latest
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
  spectryn:
    image: adriandarian/spectryn:latest
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
  - job_name: 'spectryn'
    static_configs:
      - targets: ['spectryn:9090']
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: spectryn
spec:
  template:
    spec:
      containers:
        - name: spectryn
          image: adriandarian/spectryn:latest
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
  name: spectryn
  labels:
    app: spectryn
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/port: "9090"
spec:
  ports:
    - port: 9090
      name: metrics
  selector:
    app: spectryn
```

## Grafana Dashboard

Here's a sample Grafana dashboard configuration for monitoring spectryn:

```json
{
  "title": "spectryn Sync Metrics",
  "panels": [
    {
      "title": "Sync Operations",
      "type": "stat",
      "targets": [
        {
          "expr": "sum(spectryn_sync_total)",
          "legendFormat": "Total Syncs"
        }
      ]
    },
    {
      "title": "Sync Success Rate",
      "type": "gauge",
      "targets": [
        {
          "expr": "sum(spectryn_sync_total{success=\"true\"}) / sum(spectryn_sync_total) * 100"
        }
      ]
    },
    {
      "title": "Sync Duration (p95)",
      "type": "timeseries",
      "targets": [
        {
          "expr": "histogram_quantile(0.95, rate(spectryn_sync_duration_seconds_bucket[5m]))"
        }
      ]
    },
    {
      "title": "API Calls by Operation",
      "type": "piechart",
      "targets": [
        {
          "expr": "sum by (operation) (spectryn_api_calls_total)"
        }
      ]
    },
    {
      "title": "Errors by Type",
      "type": "table",
      "targets": [
        {
          "expr": "sum by (error_type, operation) (spectryn_errors_total)"
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
  - name: spectryn
    rules:
      - alert: SpectraSyncFailureRate
        expr: |
          sum(rate(spectryn_sync_total{success="false"}[5m]))
          / sum(rate(spectryn_sync_total[5m])) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High sync failure rate"
          description: "More than 10% of syncs are failing"

      - alert: SpectraHighApiLatency
        expr: |
          histogram_quantile(0.95, rate(spectryn_api_duration_milliseconds_bucket[5m])) > 5000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High API latency"
          description: "95th percentile API latency is above 5 seconds"

      - alert: SpectraErrors
        expr: increase(spectryn_errors_total[1h]) > 10
        labels:
          severity: critical
        annotations:
          summary: "spectryn error spike"
          description: "More than 10 errors in the last hour"
```

## Troubleshooting

### Telemetry Not Working

1. **Check dependencies are installed:**
   ```bash
   pip install spectryn[telemetry]
   ```

2. **Verify configuration:**
   ```bash
   OTEL_ENABLED=true OTEL_CONSOLE_EXPORT=true spectryn --validate --markdown EPIC.md
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

## Integration Examples

### Datadog APM

Export traces and metrics to Datadog:

```bash
export OTEL_ENABLED=true
export OTEL_EXPORTER_OTLP_ENDPOINT=https://api.datadoghq.com
export OTEL_EXPORTER_OTLP_HEADERS="DD-API-KEY=your-key,DD-SITE=datadoghq.com"
export OTEL_EXPORTER_OTLP_INSECURE=false
export OTEL_SERVICE_NAME=spectryn-sync
spectryn --markdown EPIC.md --epic PROJ-123
```

### New Relic

Export to New Relic via OTLP:

```bash
export OTEL_ENABLED=true
export OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp.nr-data.net
export OTEL_EXPORTER_OTLP_HEADERS="api-key=your-new-relic-license-key"
export OTEL_EXPORTER_OTLP_INSECURE=false
export OTEL_SERVICE_NAME=spectryn
spectryn --markdown EPIC.md --epic PROJ-123
```

### Honeycomb

Export to Honeycomb:

```bash
export OTEL_ENABLED=true
export OTEL_EXPORTER_OTLP_ENDPOINT=https://api.honeycomb.io
export OTEL_EXPORTER_OTLP_HEADERS="x-honeycomb-team=your-api-key"
export OTEL_EXPORTER_OTLP_INSECURE=false
export OTEL_SERVICE_NAME=spectryn
spectryn --markdown EPIC.md --epic PROJ-123
```

### OpenTelemetry Collector

Use an OpenTelemetry Collector as an intermediary for processing and routing:

```yaml
# otel-collector-config.yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

exporters:
  logging:
    loglevel: debug
  prometheus:
    endpoint: "0.0.0.0:8889"
  jaeger:
    endpoint: jaeger:14250
    tls:
      insecure: true

service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [logging, jaeger]
    metrics:
      receivers: [otlp]
      exporters: [logging, prometheus]
```

Run spectryn with collector:
```bash
export OTEL_ENABLED=true
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
spectryn --markdown EPIC.md --epic PROJ-123
```

## See Also

- [Configuration](/guide/configuration) – General configuration options
- [Docker](/guide/docker) – Running spectryn in containers
- [Architecture](/guide/architecture) – System design overview


