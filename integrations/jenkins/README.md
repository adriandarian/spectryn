# Spectra Jenkins Plugin

Jenkins Shared Library for syncing markdown specifications to issue trackers.

## Features

- **Shared Library** - Reusable Jenkins pipeline steps
- **Multiple Trackers** - Support for Jira, GitHub, Azure DevOps, Linear, and more
- **Flexible Modes** - Dry-run, execute, pull (reverse sync)
- **Credentials Management** - Jenkins credentials integration
- **Pipeline DSL** - Easy-to-use declarative and scripted pipelines

## Installation

### Method 1: Global Shared Library

1. Go to **Manage Jenkins > Configure System > Global Pipeline Libraries**
2. Add a new library:
   - Name: `spectryn`
   - Default version: `main`
   - Retrieval method: Modern SCM
   - Source Code Management: Git
   - Project Repository: `https://github.com/spectryn/spectryn.git`
   - Library Path: `integrations/jenkins`

### Method 2: Per-Pipeline Library

```groovy
@Library('spectryn@main') _
```

## Quick Start

### Declarative Pipeline

```groovy
@Library('spectryn') _

pipeline {
    agent any

    environment {
        JIRA_CREDENTIALS = credentials('jira-api-token')
    }

    stages {
        stage('Sync to Jira') {
            steps {
                spectrynSync(
                    markdownFile: 'docs/user-stories.md',
                    epicKey: 'PROJ-123',
                    tracker: 'jira',
                    jiraUrl: 'https://company.atlassian.net',
                    execute: true
                )
            }
        }
    }
}
```

### Scripted Pipeline

```groovy
@Library('spectryn') _

node {
    stage('Checkout') {
        checkout scm
    }

    stage('Sync') {
        spectrynSync(
            markdownFile: 'docs/user-stories.md',
            epicKey: env.EPIC_KEY,
            execute: true
        )
    }
}
```

## Configuration

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `markdownFile` | Yes | | Path to markdown file |
| `epicKey` | No | | Epic key to sync |
| `tracker` | No | `jira` | Tracker type |
| `jiraUrl` | No | | Jira instance URL |
| `dryRun` | No | `false` | Preview mode |
| `execute` | No | `true` | Execute changes |
| `phase` | No | `all` | Sync phase |
| `incremental` | No | `false` | Incremental sync |
| `multiEpic` | No | `false` | Multi-epic mode |
| `epicFilter` | No | | Epic filter (comma-separated) |
| `backup` | No | `true` | Create backup |
| `verbose` | No | `false` | Verbose output |
| `exportResults` | No | | Export results file |
| `pythonVersion` | No | `3.11` | Python version |

### Credentials Setup

1. Go to **Manage Jenkins > Credentials**
2. Add credentials:

**Jira (Username with password)**
- ID: `jira-credentials`
- Username: Your Jira email
- Password: Your API token

**GitHub (Secret text)**
- ID: `github-token`
- Secret: Your GitHub PAT

## Examples

### Full Pipeline with Stages

```groovy
@Library('spectryn') _

pipeline {
    agent any

    parameters {
        string(name: 'EPIC_KEY', defaultValue: 'PROJ-123', description: 'Epic key to sync')
        booleanParam(name: 'DRY_RUN', defaultValue: false, description: 'Dry-run mode')
    }

    environment {
        JIRA_URL = 'https://company.atlassian.net'
    }

    stages {
        stage('Validate') {
            steps {
                spectrynValidate(
                    markdownFile: 'docs/user-stories.md'
                )
            }
        }

        stage('Preview') {
            when {
                expression { params.DRY_RUN }
            }
            steps {
                spectrynDiff(
                    markdownFile: 'docs/user-stories.md',
                    epicKey: params.EPIC_KEY
                )
            }
        }

        stage('Sync') {
            when {
                expression { !params.DRY_RUN }
            }
            steps {
                spectrynSync(
                    markdownFile: 'docs/user-stories.md',
                    epicKey: params.EPIC_KEY,
                    execute: true,
                    backup: true
                )
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'sync-results.json', allowEmptyArchive: true
        }
        success {
            slackSend(message: "✅ Spectra sync completed for ${params.EPIC_KEY}")
        }
        failure {
            slackSend(message: "❌ Spectra sync failed for ${params.EPIC_KEY}")
        }
    }
}
```

### Multi-Tracker Sync

```groovy
@Library('spectryn') _

pipeline {
    agent any

    stages {
        stage('Sync to Multiple Trackers') {
            parallel {
                stage('Jira') {
                    steps {
                        spectrynSync(
                            markdownFile: 'docs/user-stories.md',
                            epicKey: env.JIRA_EPIC,
                            tracker: 'jira',
                            jiraUrl: env.JIRA_URL,
                            execute: true
                        )
                    }
                }
                stage('GitHub') {
                    steps {
                        spectrynSync(
                            markdownFile: 'docs/user-stories.md',
                            tracker: 'github',
                            execute: true
                        )
                    }
                }
            }
        }
    }
}
```

### Scheduled Sync

```groovy
@Library('spectryn') _

pipeline {
    agent any

    triggers {
        cron('H 6 * * 1-5')  // Weekday mornings
    }

    stages {
        stage('Incremental Sync') {
            steps {
                spectrynSync(
                    markdownFile: 'docs/user-stories.md',
                    epicKey: env.EPIC_KEY,
                    incremental: true,
                    execute: true
                )
            }
        }
    }
}
```

### Pull (Reverse Sync)

```groovy
@Library('spectryn') _

pipeline {
    agent any

    stages {
        stage('Pull from Jira') {
            steps {
                spectrynPull(
                    epicKey: 'PROJ-123',
                    outputFile: 'docs/imported-stories.md',
                    tracker: 'jira'
                )
            }
        }

        stage('Commit Changes') {
            steps {
                sh '''
                    git add docs/imported-stories.md
                    git commit -m "Update stories from Jira"
                    git push
                '''
            }
        }
    }
}
```

## Shared Library Functions

### spectrynSync

```groovy
spectrynSync(
    markdownFile: 'docs/stories.md',
    epicKey: 'PROJ-123',
    tracker: 'jira',
    execute: true
)
```

### spectrynValidate

```groovy
spectrynValidate(
    markdownFile: 'docs/stories.md'
)
```

### spectrynDiff

```groovy
spectrynDiff(
    markdownFile: 'docs/stories.md',
    epicKey: 'PROJ-123'
)
```

### spectrynPull

```groovy
spectrynPull(
    epicKey: 'PROJ-123',
    outputFile: 'docs/stories.md'
)
```

## Troubleshooting

### Python Not Found

Ensure Python is installed on the Jenkins agent:

```groovy
pipeline {
    agent {
        docker {
            image 'python:3.11-slim'
        }
    }
    // ...
}
```

### Credentials Issues

Verify credentials are accessible:

```groovy
withCredentials([usernamePassword(credentialsId: 'jira-credentials',
                                   usernameVariable: 'JIRA_EMAIL',
                                   passwordVariable: 'JIRA_API_TOKEN')]) {
    spectrynSync(markdownFile: 'docs/stories.md', epicKey: 'PROJ-123')
}
```

## License

MIT License - see [LICENSE](../../LICENSE) for details.
