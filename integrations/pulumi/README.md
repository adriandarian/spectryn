# Spectra Pulumi Provider

A Pulumi provider for deploying and managing Spectra syncs across multiple cloud platforms.

## Features

- **Multi-Cloud Support** - Deploy to AWS, Azure, GCP, and Kubernetes
- **Type-Safe Configuration** - Full TypeScript/Python type safety
- **Component Resources** - High-level abstractions for common patterns
- **Secrets Management** - Automatic secret encryption
- **Preview & Diff** - See changes before deployment

## Installation

### TypeScript/JavaScript

```bash
npm install @spectra/pulumi
# or
yarn add @spectra/pulumi
```

### Python

```bash
pip install pulumi-spectra
```

### Go

```bash
go get github.com/spectra/pulumi-spectra/sdk/go/spectra
```

## Quick Start

### TypeScript

```typescript
import * as spectra from "@spectra/pulumi";

// Create a Spectra sync on AWS
const sync = new spectra.aws.FargateSync("my-sync", {
    tracker: {
        type: "jira",
        url: "https://company.atlassian.net",
        project: "PROJ",
        epicKey: "PROJ-123",
        credentials: {
            email: jiraEmail,
            apiToken: pulumi.secret(jiraToken),
        },
    },
    source: {
        type: "s3",
        bucket: "my-specs-bucket",
        key: "user-stories.md",
    },
    schedule: "rate(6 hours)",
});

// Export the sync ARN
export const syncArn = sync.arn;
```

### Python

```python
import pulumi
import pulumi_spectra as spectra

# Create a Spectra sync on Kubernetes
sync = spectra.kubernetes.SpectraSync("my-sync",
    tracker=spectra.TrackerConfigArgs(
        type="jira",
        url="https://company.atlassian.net",
        project="PROJ",
        epic_key="PROJ-123",
        credentials=spectra.CredentialsArgs(
            email=jira_email,
            api_token=pulumi.Output.secret(jira_token),
        ),
    ),
    source=spectra.SourceConfigArgs(
        type="configmap",
        config_map_name="user-stories",
        key="spec.md",
    ),
    schedule="0 */6 * * *",
)

pulumi.export("sync_name", sync.name)
```

## Resources

### AWS Resources

| Resource | Description |
|----------|-------------|
| `spectra.aws.FargateSync` | ECS Fargate-based sync |
| `spectra.aws.LambdaSync` | Lambda-based sync |
| `spectra.aws.EcsSync` | ECS EC2-based sync |

### Azure Resources

| Resource | Description |
|----------|-------------|
| `spectra.azure.ContainerInstanceSync` | ACI-based sync |
| `spectra.azure.ContainerAppSync` | Container Apps sync |
| `spectra.azure.FunctionSync` | Azure Function sync |

### GCP Resources

| Resource | Description |
|----------|-------------|
| `spectra.gcp.CloudRunSync` | Cloud Run sync |
| `spectra.gcp.CloudFunctionSync` | Cloud Function sync |

### Kubernetes Resources

| Resource | Description |
|----------|-------------|
| `spectra.kubernetes.SpectraSync` | CRD-based sync |
| `spectra.kubernetes.CronJobSync` | CronJob-based sync |

## Configuration

### Tracker Types

```typescript
const jiraTracker: spectra.TrackerConfig = {
    type: "jira",
    url: "https://company.atlassian.net",
    project: "PROJ",
    epicKey: "PROJ-123",
    credentials: {
        email: "user@company.com",
        apiToken: pulumi.secret("token"),
    },
};

const githubTracker: spectra.TrackerConfig = {
    type: "github",
    owner: "myorg",
    repo: "myrepo",
    credentials: {
        token: pulumi.secret("ghp_..."),
    },
};

const linearTracker: spectra.TrackerConfig = {
    type: "linear",
    teamId: "TEAM-123",
    credentials: {
        apiKey: pulumi.secret("lin_api_..."),
    },
};
```

### Source Types

```typescript
// S3 source (AWS)
const s3Source: spectra.SourceConfig = {
    type: "s3",
    bucket: "my-bucket",
    key: "docs/user-stories.md",
};

// Git source
const gitSource: spectra.SourceConfig = {
    type: "git",
    repository: "https://github.com/org/repo.git",
    branch: "main",
    path: "docs/stories.md",
    credentials: {
        username: "git",
        password: pulumi.secret("ghp_..."),
    },
};

// ConfigMap source (Kubernetes)
const configMapSource: spectra.SourceConfig = {
    type: "configmap",
    configMapName: "user-stories",
    key: "spec.md",
};
```

## Examples

### Multi-Cloud Deployment

```typescript
import * as pulumi from "@pulumi/pulumi";
import * as spectra from "@spectra/pulumi";

const config = new pulumi.Config();
const trackerConfig = {
    type: "jira",
    url: config.require("jiraUrl"),
    credentials: {
        email: config.require("jiraEmail"),
        apiToken: config.requireSecret("jiraApiToken"),
    },
};

// Deploy to AWS
const awsSync = new spectra.aws.FargateSync("aws-sync", {
    tracker: trackerConfig,
    source: { type: "s3", bucket: "specs", key: "stories.md" },
    schedule: "rate(6 hours)",
});

// Deploy to Azure
const azureSync = new spectra.azure.ContainerInstanceSync("azure-sync", {
    tracker: trackerConfig,
    source: { type: "blob", container: "specs", blob: "stories.md" },
    schedule: "0 */6 * * *",
});

// Deploy to Kubernetes
const k8sSync = new spectra.kubernetes.SpectraSync("k8s-sync", {
    tracker: trackerConfig,
    source: { type: "configmap", configMapName: "specs", key: "stories.md" },
    schedule: "0 */6 * * *",
});
```

### With Monitoring

```typescript
import * as spectra from "@spectra/pulumi";
import * as aws from "@pulumi/aws";

const sync = new spectra.aws.FargateSync("monitored-sync", {
    tracker: { /* ... */ },
    source: { /* ... */ },
    schedule: "rate(1 hour)",
    monitoring: {
        enabled: true,
        alarmOnFailure: true,
        dashboardEnabled: true,
    },
});

// Access monitoring resources
export const dashboardUrl = sync.dashboard?.url;
export const alarmArn = sync.failureAlarm?.arn;
```

## Development

### Building

```bash
# Install dependencies
npm install

# Build provider
npm run build

# Run tests
npm test
```

### Publishing

```bash
# Publish to npm
npm publish

# Publish to PyPI
cd sdk/python && python -m build && twine upload dist/*
```

## License

MIT License - see [LICENSE](../../LICENSE) for details.
