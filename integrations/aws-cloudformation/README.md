# Spectra AWS CloudFormation Templates

AWS CloudFormation templates for deploying Spectra to AWS.

## Features

- **AWS Fargate** - Serverless container deployment
- **AWS Lambda** - Event-driven scheduled syncs
- **Amazon ECS** - Container orchestration
- **AWS Secrets Manager** - Secure credential management
- **Amazon CloudWatch** - Logging and monitoring
- **Amazon EventBridge** - Scheduled execution

## Prerequisites

- AWS account
- AWS CLI installed and configured
- Appropriate IAM permissions

## Quick Start

### Deploy with AWS CLI

```bash
# Deploy the main stack
aws cloudformation create-stack \
  --stack-name spectra-sync \
  --template-body file://spectra-fargate.yaml \
  --parameters \
    ParameterKey=JiraUrl,ParameterValue=https://company.atlassian.net \
    ParameterKey=JiraEmail,ParameterValue=user@company.com \
    ParameterKey=JiraApiToken,ParameterValue=your-api-token \
    ParameterKey=EpicKey,ParameterValue=PROJ-123 \
  --capabilities CAPABILITY_IAM
```

### Deploy with SAM CLI

```bash
sam deploy \
  --template-file spectra-lambda.yaml \
  --stack-name spectra-lambda \
  --parameter-overrides \
    JiraUrl=https://company.atlassian.net \
    JiraEmail=user@company.com \
    EpicKey=PROJ-123 \
  --capabilities CAPABILITY_IAM
```

## Templates

| Template | Description |
|----------|-------------|
| `spectra-fargate.yaml` | ECS Fargate deployment |
| `spectra-lambda.yaml` | Lambda-based scheduled sync |
| `spectra-ecs.yaml` | ECS with EC2 instances |
| `spectra-vpc.yaml` | VPC infrastructure |
| `spectra-secrets.yaml` | Secrets Manager setup |

## Configuration

### Required Parameters

| Parameter | Description |
|-----------|-------------|
| `JiraUrl` | Jira instance URL |
| `JiraEmail` | Jira account email |
| `JiraApiToken` | Jira API token |
| `EpicKey` | Epic key to sync |

### Optional Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `Environment` | `production` | Environment name |
| `SpectraImage` | `spectra/spectra:latest` | Container image |
| `Schedule` | `rate(6 hours)` | EventBridge schedule |
| `DryRun` | `false` | Enable dry-run mode |
| `VpcId` | Create new | Existing VPC ID |
| `SubnetIds` | Create new | Subnet IDs |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        AWS Account                           │
│  ┌─────────────────────────────────────────────────────────┐│
│  │                         VPC                              ││
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐ ││
│  │  │   Subnet    │  │   Subnet    │  │   Secrets Mgr   │ ││
│  │  │  (private)  │  │  (private)  │  │                 │ ││
│  │  └──────┬──────┘  └──────┬──────┘  └────────┬────────┘ ││
│  │         │                │                   │          ││
│  │         └────────┬───────┘                   │          ││
│  │                  │                           │          ││
│  │         ┌────────┴────────┐                  │          ││
│  │         │   ECS Fargate   │◄─────────────────┘          ││
│  │         │   (Spectra)     │                             ││
│  │         └────────┬────────┘                             ││
│  │                  │                                      ││
│  │         ┌────────┴────────┐                             ││
│  │         │   CloudWatch    │                             ││
│  │         │     Logs        │                             ││
│  │         └─────────────────┘                             ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  ┌─────────────────┐                                        │
│  │  EventBridge    │─────────► Triggers scheduled sync      │
│  │   (Schedule)    │                                        │
│  └─────────────────┘                                        │
└─────────────────────────────────────────────────────────────┘
```

## Examples

### Fargate with existing VPC

```bash
aws cloudformation create-stack \
  --stack-name spectra-sync \
  --template-body file://spectra-fargate.yaml \
  --parameters \
    ParameterKey=VpcId,ParameterValue=vpc-12345678 \
    ParameterKey=SubnetIds,ParameterValue="subnet-111,subnet-222" \
    ParameterKey=JiraUrl,ParameterValue=https://company.atlassian.net \
    ParameterKey=JiraEmail,ParameterValue=user@company.com \
    ParameterKey=JiraApiToken,ParameterValue=your-api-token \
    ParameterKey=EpicKey,ParameterValue=PROJ-123 \
  --capabilities CAPABILITY_IAM
```

### Lambda with custom schedule

```bash
aws cloudformation create-stack \
  --stack-name spectra-lambda \
  --template-body file://spectra-lambda.yaml \
  --parameters \
    ParameterKey=Schedule,ParameterValue="cron(0 */4 * * ? *)" \
    ParameterKey=JiraUrl,ParameterValue=https://company.atlassian.net \
    ParameterKey=JiraApiToken,ParameterValue=your-api-token \
    ParameterKey=EpicKey,ParameterValue=PROJ-123 \
  --capabilities CAPABILITY_IAM
```

## Cleanup

```bash
# Delete the stack
aws cloudformation delete-stack --stack-name spectra-sync

# Wait for deletion
aws cloudformation wait stack-delete-complete --stack-name spectra-sync
```

## License

MIT License - see [LICENSE](../../LICENSE) for details.
