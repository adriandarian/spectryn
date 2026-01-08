# Spectra Azure ARM/Bicep Templates

Azure Resource Manager (ARM) and Bicep templates for deploying Spectra to Azure.

## Features

- **Azure Container Instances (ACI)** - Serverless container deployment
- **Azure Container Apps** - Managed Kubernetes-like deployment
- **Azure Functions** - Event-driven scheduled syncs
- **Azure Key Vault** - Secure credential management
- **Azure Monitor** - Logging and metrics integration

## Prerequisites

- Azure subscription
- Azure CLI installed
- Appropriate permissions to create resources

## Quick Start

### Deploy with Azure CLI (Bicep)

```bash
# Login to Azure
az login

# Create resource group
az group create --name spectryn-rg --location eastus

# Deploy Spectra
az deployment group create \
  --resource-group spectryn-rg \
  --template-file main.bicep \
  --parameters \
    jiraUrl='https://company.atlassian.net' \
    jiraEmail='user@company.com' \
    jiraApiToken='your-api-token' \
    epicKey='PROJ-123'
```

### Deploy with ARM Template

```bash
az deployment group create \
  --resource-group spectryn-rg \
  --template-file azuredeploy.json \
  --parameters @azuredeploy.parameters.json
```

## Templates

| Template | Description |
|----------|-------------|
| `main.bicep` | Main Bicep template |
| `azuredeploy.json` | ARM template (generated from Bicep) |
| `modules/` | Reusable Bicep modules |
| `examples/` | Example configurations |

## Configuration

### Required Parameters

| Parameter | Description |
|-----------|-------------|
| `jiraUrl` | Jira instance URL |
| `jiraEmail` | Jira account email |
| `jiraApiToken` | Jira API token |
| `epicKey` | Epic key to sync |

### Optional Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `location` | Resource group location | Azure region |
| `spectrynImage` | `spectryn/spectryn:latest` | Container image |
| `schedule` | `0 */6 * * *` | Cron schedule |
| `dryRun` | `false` | Enable dry-run mode |

## Examples

### Container Instance with Key Vault

```bash
az deployment group create \
  --resource-group spectryn-rg \
  --template-file examples/aci-keyvault.bicep \
  --parameters \
    keyVaultName='spectryn-kv' \
    jiraUrl='https://company.atlassian.net'
```

### Container Apps with managed identity

```bash
az deployment group create \
  --resource-group spectryn-rg \
  --template-file examples/container-apps.bicep \
  --parameters \
    environmentName='spectryn-env'
```

## License

MIT License - see [LICENSE](../../LICENSE) for details.
