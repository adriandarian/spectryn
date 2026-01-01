# Spectra Helm Chart

A Helm chart for deploying Spectra operator and scheduled syncs to Kubernetes.

## Features

- Deploy Spectra operator for managing sync CRDs
- Deploy standalone sync jobs
- Configure multiple trackers
- Secret management for credentials
- Prometheus metrics integration
- Network policies support

## Prerequisites

- Kubernetes 1.19+
- Helm 3.x
- PV provisioner (if using persistent storage)

## Installation

### Add the Helm repository

```bash
helm repo add spectra https://spectra.github.io/helm-charts
helm repo update
```

### Install the chart

```bash
# Install operator mode (recommended)
helm install spectra spectra/spectra \
  --namespace spectra-system \
  --create-namespace

# Install with custom values
helm install spectra spectra/spectra \
  --namespace spectra-system \
  --create-namespace \
  -f values.yaml
```

### Quick start with Jira

```bash
helm install spectra spectra/spectra \
  --namespace spectra-system \
  --create-namespace \
  --set jira.enabled=true \
  --set jira.url=https://company.atlassian.net \
  --set jira.email=user@company.com \
  --set jira.apiToken=your-api-token
```

## Configuration

See [values.yaml](values.yaml) for all available options.

### Key Configuration Options

| Parameter | Description | Default |
|-----------|-------------|---------|
| `operator.enabled` | Deploy the operator | `true` |
| `operator.image.repository` | Operator image repository | `spectra/operator` |
| `operator.image.tag` | Operator image tag | `latest` |
| `spectra.image.repository` | Spectra image repository | `spectra/spectra` |
| `spectra.image.tag` | Spectra image tag | `latest` |
| `jira.enabled` | Enable Jira tracker | `false` |
| `github.enabled` | Enable GitHub tracker | `false` |
| `metrics.enabled` | Enable Prometheus metrics | `true` |

## Examples

### Deploy with Jira sync

```yaml
# values-jira.yaml
operator:
  enabled: true

syncs:
  - name: project-sync
    source:
      type: configmap
      configMap:
        name: user-stories
        key: spec.md
    tracker:
      type: jira
      url: https://company.atlassian.net
      project: PROJ
      epicKey: PROJ-123
    schedule: "0 */6 * * *"
    credentials:
      existingSecret: jira-credentials

secrets:
  jira-credentials:
    email: user@company.com
    api-token: your-api-token
```

### Deploy with GitHub sync

```yaml
# values-github.yaml
syncs:
  - name: github-sync
    source:
      type: git
      git:
        repository: https://github.com/org/repo.git
        branch: main
        path: docs/stories.md
    tracker:
      type: github
      owner: org
      repo: project
    schedule: "*/30 * * * *"
    credentials:
      existingSecret: github-token
```

## Upgrading

```bash
helm upgrade spectra spectra/spectra \
  --namespace spectra-system \
  -f values.yaml
```

## Uninstalling

```bash
helm uninstall spectra --namespace spectra-system
kubectl delete namespace spectra-system
```

## License

MIT License - see [LICENSE](../../LICENSE) for details.
