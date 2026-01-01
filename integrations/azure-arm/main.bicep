// Copyright (c) spectra
// SPDX-License-Identifier: MIT

// Main Bicep template for deploying Spectra to Azure

@description('Location for all resources')
param location string = resourceGroup().location

@description('Name prefix for all resources')
param namePrefix string = 'spectra'

@description('Spectra container image')
param spectraImage string = 'spectra/spectra:latest'

@description('Deployment mode: aci (Container Instances), aca (Container Apps), or function')
@allowed(['aci', 'aca', 'function'])
param deploymentMode string = 'aci'

@description('Jira instance URL')
param jiraUrl string

@description('Jira account email')
@secure()
param jiraEmail string

@description('Jira API token')
@secure()
param jiraApiToken string

@description('Project key')
param projectKey string = ''

@description('Epic key to sync')
param epicKey string

@description('Path to markdown file (for git source)')
param markdownPath string = 'docs/user-stories.md'

@description('Cron schedule for sync')
param schedule string = '0 */6 * * *'

@description('Enable dry-run mode')
param dryRun bool = false

@description('Enable Key Vault for secrets')
param useKeyVault bool = true

@description('Enable Application Insights')
param enableMonitoring bool = true

@description('Tags for all resources')
param tags object = {
  application: 'spectra'
  environment: 'production'
}

// Variables
var uniqueSuffix = uniqueString(resourceGroup().id)
var keyVaultName = '${namePrefix}-kv-${uniqueSuffix}'
var logAnalyticsName = '${namePrefix}-logs-${uniqueSuffix}'
var appInsightsName = '${namePrefix}-insights-${uniqueSuffix}'
var storageAccountName = '${namePrefix}st${uniqueSuffix}'
var containerGroupName = '${namePrefix}-aci-${uniqueSuffix}'
var containerAppEnvName = '${namePrefix}-env-${uniqueSuffix}'
var containerAppName = '${namePrefix}-app'
var functionAppName = '${namePrefix}-func-${uniqueSuffix}'

// Log Analytics Workspace
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = if (enableMonitoring) {
  name: logAnalyticsName
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// Application Insights
resource appInsights 'Microsoft.Insights/components@2020-02-02' = if (enableMonitoring) {
  name: appInsightsName
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: enableMonitoring ? logAnalytics.id : null
  }
}

// Key Vault
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = if (useKeyVault) {
  name: keyVaultName
  location: location
  tags: tags
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
  }
}

// Store secrets in Key Vault
resource jiraEmailSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (useKeyVault) {
  parent: keyVault
  name: 'jira-email'
  properties: {
    value: jiraEmail
  }
}

resource jiraTokenSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (useKeyVault) {
  parent: keyVault
  name: 'jira-api-token'
  properties: {
    value: jiraApiToken
  }
}

// Storage Account (for Function App)
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = if (deploymentMode == 'function') {
  name: storageAccountName
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
  }
}

// Container Instance deployment
resource containerGroup 'Microsoft.ContainerInstance/containerGroups@2023-05-01' = if (deploymentMode == 'aci') {
  name: containerGroupName
  location: location
  tags: tags
  properties: {
    containers: [
      {
        name: 'spectra'
        properties: {
          image: spectraImage
          command: [
            'spectra'
            'sync'
            '--tracker'
            'jira'
            '--markdown'
            '/data/spec.md'
            '--epic-key'
            epicKey
            dryRun ? '--dry-run' : '--execute'
          ]
          environmentVariables: [
            {
              name: 'JIRA_URL'
              value: jiraUrl
            }
            {
              name: 'JIRA_EMAIL'
              secureValue: useKeyVault ? null : jiraEmail
              value: useKeyVault ? '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/jira-email/)' : null
            }
            {
              name: 'JIRA_API_TOKEN'
              secureValue: useKeyVault ? null : jiraApiToken
              value: useKeyVault ? '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/jira-api-token/)' : null
            }
            {
              name: 'JIRA_PROJECT'
              value: projectKey
            }
          ]
          resources: {
            requests: {
              cpu: 1
              memoryInGB: 1
            }
          }
        }
      }
    ]
    osType: 'Linux'
    restartPolicy: 'OnFailure'
  }
}

// Container Apps Environment
resource containerAppEnvironment 'Microsoft.App/managedEnvironments@2023-05-01' = if (deploymentMode == 'aca') {
  name: containerAppEnvName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: enableMonitoring ? logAnalytics.properties.customerId : null
        sharedKey: enableMonitoring ? logAnalytics.listKeys().primarySharedKey : null
      }
    }
  }
}

// Container App
resource containerApp 'Microsoft.App/containerApps@2023-05-01' = if (deploymentMode == 'aca') {
  name: containerAppName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerAppEnvironment.id
    configuration: {
      secrets: [
        {
          name: 'jira-email'
          value: jiraEmail
        }
        {
          name: 'jira-api-token'
          value: jiraApiToken
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'spectra'
          image: spectraImage
          command: [
            'spectra'
            'sync'
            '--tracker'
            'jira'
            '--markdown'
            '/data/spec.md'
            '--epic-key'
            epicKey
            dryRun ? '--dry-run' : '--execute'
          ]
          env: [
            {
              name: 'JIRA_URL'
              value: jiraUrl
            }
            {
              name: 'JIRA_EMAIL'
              secretRef: 'jira-email'
            }
            {
              name: 'JIRA_API_TOKEN'
              secretRef: 'jira-api-token'
            }
            {
              name: 'JIRA_PROJECT'
              value: projectKey
            }
          ]
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 1
      }
    }
  }
}

// Function App (for scheduled execution)
resource hostingPlan 'Microsoft.Web/serverfarms@2022-09-01' = if (deploymentMode == 'function') {
  name: '${namePrefix}-plan-${uniqueSuffix}'
  location: location
  tags: tags
  sku: {
    name: 'Y1'
    tier: 'Dynamic'
  }
  properties: {
    reserved: true
  }
}

resource functionApp 'Microsoft.Web/sites@2022-09-01' = if (deploymentMode == 'function') {
  name: functionAppName
  location: location
  tags: tags
  kind: 'functionapp,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: hostingPlan.id
    siteConfig: {
      linuxFxVersion: 'DOCKER|${spectraImage}'
      appSettings: [
        {
          name: 'AzureWebJobsStorage'
          value: 'DefaultEndpointsProtocol=https;AccountName=${storageAccount.name};EndpointSuffix=${environment().suffixes.storage};AccountKey=${storageAccount.listKeys().keys[0].value}'
        }
        {
          name: 'FUNCTIONS_EXTENSION_VERSION'
          value: '~4'
        }
        {
          name: 'FUNCTIONS_WORKER_RUNTIME'
          value: 'custom'
        }
        {
          name: 'JIRA_URL'
          value: jiraUrl
        }
        {
          name: 'JIRA_EMAIL'
          value: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/jira-email/)'
        }
        {
          name: 'JIRA_API_TOKEN'
          value: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/jira-api-token/)'
        }
        {
          name: 'JIRA_PROJECT'
          value: projectKey
        }
        {
          name: 'EPIC_KEY'
          value: epicKey
        }
        {
          name: 'SYNC_SCHEDULE'
          value: schedule
        }
        {
          name: 'DRY_RUN'
          value: string(dryRun)
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: enableMonitoring ? appInsights.properties.ConnectionString : ''
        }
      ]
    }
    httpsOnly: true
  }
}

// Key Vault access for Function App
resource keyVaultAccessPolicy 'Microsoft.KeyVault/vaults/accessPolicies@2023-07-01' = if (useKeyVault && deploymentMode == 'function') {
  parent: keyVault
  name: 'add'
  properties: {
    accessPolicies: [
      {
        tenantId: subscription().tenantId
        objectId: functionApp.identity.principalId
        permissions: {
          secrets: [
            'get'
            'list'
          ]
        }
      }
    ]
  }
}

// Outputs
output resourceGroupName string = resourceGroup().name
output keyVaultName string = useKeyVault ? keyVault.name : ''
output keyVaultUri string = useKeyVault ? keyVault.properties.vaultUri : ''
output containerGroupName string = deploymentMode == 'aci' ? containerGroup.name : ''
output containerAppName string = deploymentMode == 'aca' ? containerApp.name : ''
output functionAppName string = deploymentMode == 'function' ? functionApp.name : ''
output appInsightsInstrumentationKey string = enableMonitoring ? appInsights.properties.InstrumentationKey : ''
