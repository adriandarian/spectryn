# Spectra Kubernetes Operator

A Kubernetes operator for managing scheduled Spectra syncs using Custom Resource Definitions (CRDs).

## Features

- **SpectraSync CRD**: Define sync jobs declaratively
- **Scheduled Syncs**: Cron-based scheduling for automated syncs
- **Multiple Trackers**: Support for Jira, GitHub, Azure DevOps, Linear, and more
- **Dry Run Mode**: Test syncs without making changes
- **Status Tracking**: Monitor sync status via Kubernetes resources
- **Secret Management**: Secure credential handling via Kubernetes Secrets

## Installation

### Prerequisites

- Kubernetes 1.19+
- kubectl configured
- Helm 3.x (optional, for Helm installation)

### Install with kubectl

```bash
# Install CRDs
kubectl apply -f config/crd/bases/

# Install operator
kubectl apply -f config/manager/
```

### Install with Helm

```bash
helm install spectra-operator ./chart \
  --namespace spectra-system \
  --create-namespace
```

## Usage

### Basic Example

```yaml
apiVersion: spectra.io/v1alpha1
kind: SpectraSync
metadata:
  name: my-project-sync
  namespace: default
spec:
  # Source configuration
  source:
    type: configmap  # or git, pvc
    configMap:
      name: my-specs
      key: user-stories.md

  # Tracker configuration
  tracker:
    type: jira
    url: https://company.atlassian.net
    project: PROJ
    epicKey: PROJ-123
    credentialsSecret:
      name: jira-credentials
      emailKey: email
      tokenKey: api-token

  # Sync schedule (cron format)
  schedule: "0 */6 * * *"  # Every 6 hours

  # Options
  dryRun: false
  phases:
    - descriptions
    - subtasks
    - statuses
```

### Secret Configuration

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: jira-credentials
type: Opaque
stringData:
  email: your-email@company.com
  api-token: your-api-token
```

### Git Source Example

```yaml
apiVersion: spectra.io/v1alpha1
kind: SpectraSync
metadata:
  name: git-sync
spec:
  source:
    type: git
    git:
      repository: https://github.com/org/repo.git
      branch: main
      path: docs/user-stories.md
      credentialsSecret:
        name: git-credentials
        usernameKey: username
        passwordKey: token
  tracker:
    type: github
    owner: myorg
    repo: myrepo
    credentialsSecret:
      name: github-token
      tokenKey: token
  schedule: "*/30 * * * *"  # Every 30 minutes
```

## CRD Reference

### SpectraSync

| Field | Type | Description |
|-------|------|-------------|
| `spec.source` | SourceSpec | Source of markdown files |
| `spec.tracker` | TrackerSpec | Target issue tracker |
| `spec.schedule` | string | Cron schedule expression |
| `spec.dryRun` | bool | Enable dry-run mode |
| `spec.phases` | []string | Sync phases to execute |
| `spec.suspend` | bool | Suspend scheduled syncs |
| `spec.concurrencyPolicy` | string | How to handle concurrent runs |

### Status Fields

| Field | Type | Description |
|-------|------|-------------|
| `status.lastSyncTime` | Time | Last successful sync time |
| `status.lastSyncResult` | string | Result of last sync |
| `status.nextSyncTime` | Time | Next scheduled sync time |
| `status.conditions` | []Condition | Detailed status conditions |
| `status.syncHistory` | []SyncRecord | Recent sync history |

## Development

### Building

```bash
# Build operator image
make docker-build IMG=spectra/operator:latest

# Push image
make docker-push IMG=spectra/operator:latest
```

### Running Locally

```bash
# Install CRDs
make install

# Run operator locally
make run
```

### Testing

```bash
# Run unit tests
make test

# Run e2e tests
make test-e2e
```

## Configuration

### Operator Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--metrics-bind-address` | `:8080` | Metrics endpoint address |
| `--health-probe-bind-address` | `:8081` | Health probe address |
| `--leader-elect` | `false` | Enable leader election |
| `--sync-period` | `10m` | Controller sync period |

### Environment Variables

| Variable | Description |
|----------|-------------|
| `SPECTRA_IMAGE` | Spectra container image |
| `SPECTRA_IMAGE_PULL_POLICY` | Image pull policy |
| `LOG_LEVEL` | Logging level (debug, info, warn, error) |

## License

MIT License - see [LICENSE](../../LICENSE) for details.
