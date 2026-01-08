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
npm install @spectryn/pulumi
# or
yarn add @spectryn/pulumi
```

### Python

```bash
pip install pulumi-spectryn
```

### Go

```bash
go get github.com/spectryn/pulumi-spectryn/sdk/go/spectryn
```

## Quick Start

### TypeScript

```typescript
import * as spectryn from "@spectryn/pulumi";

// Create a Spectra sync on AWS
const sync = new spectryn.aws.FargateSync("my-sync", {
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
import pulumi_spectryn as spectryn

# Create a Spectra sync on Kubernetes
sync = spectryn.kubernetes.SpectraSync("my-sync",
    tracker=spectryn.TrackerConfigArgs(
        type="jira",
        url="https://company.atlassian.net",
        project="PROJ",
        epic_key="PROJ-123",
        credentials=spectryn.CredentialsArgs(
            email=jira_email,
            api_token=pulumi.Output.secret(jira_token),
        ),
    ),
    source=spectryn.SourceConfigArgs(
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
| `spectryn.aws.FargateSync` | ECS Fargate-based sync |
| `spectryn.aws.LambdaSync` | Lambda-based sync |
| `spectryn.aws.EcsSync` | ECS EC2-based sync |

### Azure Resources

| Resource | Description |
|----------|-------------|
| `spectryn.azure.ContainerInstanceSync` | ACI-based sync |
| `spectryn.azure.ContainerAppSync` | Container Apps sync |
| `spectryn.azure.FunctionSync` | Azure Function sync |

### GCP Resources

| Resource | Description |
|----------|-------------|
| `spectryn.gcp.CloudRunSync` | Cloud Run sync |
| `spectryn.gcp.CloudFunctionSync` | Cloud Function sync |

### Kubernetes Resources

| Resource | Description |
|----------|-------------|
| `spectryn.kubernetes.SpectraSync` | CRD-based sync |
| `spectryn.kubernetes.CronJobSync` | CronJob-based sync |

## Configuration

### Tracker Types

```typescript
const jiraTracker: spectryn.TrackerConfig = {
    type: "jira",
    url: "https://company.atlassian.net",
    project: "PROJ",
    epicKey: "PROJ-123",
    credentials: {
        email: "user@company.com",
        apiToken: pulumi.secret("token"),
    },
};

const githubTracker: spectryn.TrackerConfig = {
    type: "github",
    owner: "myorg",
    repo: "myrepo",
    credentials: {
        token: pulumi.secret("ghp_..."),
    },
};

const linearTracker: spectryn.TrackerConfig = {
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
const s3Source: spectryn.SourceConfig = {
    type: "s3",
    bucket: "my-bucket",
    key: "docs/user-stories.md",
};

// Git source
const gitSource: spectryn.SourceConfig = {
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
const configMapSource: spectryn.SourceConfig = {
    type: "configmap",
    configMapName: "user-stories",
    key: "spec.md",
};
```

## Examples

### Multi-Cloud Deployment

```typescript
import * as pulumi from "@pulumi/pulumi";
import * as spectryn from "@spectryn/pulumi";

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
const awsSync = new spectryn.aws.FargateSync("aws-sync", {
    tracker: trackerConfig,
    source: { type: "s3", bucket: "specs", key: "stories.md" },
    schedule: "rate(6 hours)",
});

// Deploy to Azure
const azureSync = new spectryn.azure.ContainerInstanceSync("azure-sync", {
    tracker: trackerConfig,
    source: { type: "blob", container: "specs", blob: "stories.md" },
    schedule: "0 */6 * * *",
});

// Deploy to Kubernetes
const k8sSync = new spectryn.kubernetes.SpectraSync("k8s-sync", {
    tracker: trackerConfig,
    source: { type: "configmap", configMapName: "specs", key: "stories.md" },
    schedule: "0 */6 * * *",
});
```

### With Monitoring

```typescript
import * as spectryn from "@spectryn/pulumi";
import * as aws from "@pulumi/aws";

const sync = new spectryn.aws.FargateSync("monitored-sync", {
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
