# CI/CD Integration

Integrate spectryn into your continuous integration and deployment pipelines.

## GitHub Actions

### Basic Sync on Push

```yaml
# .github/workflows/jira-sync.yml
name: Sync to Jira

on:
  push:
    paths:
      - 'docs/EPIC.md'
    branches:
      - main

jobs:
  sync:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - name: Install spectryn
        run: pip install spectryn
      
      - name: Sync to Jira
        env:
          JIRA_URL: ${{ secrets.JIRA_URL }}
          JIRA_EMAIL: ${{ secrets.JIRA_EMAIL }}
          JIRA_API_TOKEN: ${{ secrets.JIRA_API_TOKEN }}
        run: |
          spectryn \
            --markdown docs/EPIC.md \
            --epic ${{ vars.EPIC_KEY }} \
            --execute \
            --no-confirm \
            --export results.json
      
      - name: Upload results
        uses: actions/upload-artifact@v4
        with:
          name: jira-sync-results
          path: results.json
```

### PR Preview (Dry Run)

```yaml
# .github/workflows/jira-preview.yml
name: Preview Jira Changes

on:
  pull_request:
    paths:
      - 'docs/EPIC.md'

jobs:
  preview:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - name: Install spectryn
        run: pip install spectryn
      
      - name: Preview changes
        id: preview
        env:
          JIRA_URL: ${{ secrets.JIRA_URL }}
          JIRA_EMAIL: ${{ secrets.JIRA_EMAIL }}
          JIRA_API_TOKEN: ${{ secrets.JIRA_API_TOKEN }}
        run: |
          spectryn \
            --markdown docs/EPIC.md \
            --epic ${{ vars.EPIC_KEY }} \
            --output json \
            > preview.json
          
          # Extract summary for PR comment
          echo "stories=$(jq '.summary.stories' preview.json)" >> $GITHUB_OUTPUT
          echo "subtasks=$(jq '.summary.subtasks_to_create' preview.json)" >> $GITHUB_OUTPUT
      
      - name: Comment on PR
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: `## 📋 Jira Sync Preview
              
              This PR would sync to Jira epic \`${{ vars.EPIC_KEY }}\`:
              
              - **Stories**: ${{ steps.preview.outputs.stories }}
              - **Subtasks to create**: ${{ steps.preview.outputs.subtasks }}
              
              Changes will be applied when merged to main.`
            })
```

### Sync with Matrix Strategy

```yaml
# .github/workflows/multi-epic-sync.yml
name: Sync Multiple Epics

on:
  workflow_dispatch:
    inputs:
      epics:
        description: 'Comma-separated epic keys'
        required: true
        default: 'PROJ-100,PROJ-200'

jobs:
  sync:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        epic: ${{ fromJSON(format('["{0}"]', replace(inputs.epics, ',', '","'))) }}
    
    steps:
      - uses: actions/checkout@v4
      
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - run: pip install spectryn
      
      - name: Sync ${{ matrix.epic }}
        env:
          JIRA_URL: ${{ secrets.JIRA_URL }}
          JIRA_EMAIL: ${{ secrets.JIRA_EMAIL }}
          JIRA_API_TOKEN: ${{ secrets.JIRA_API_TOKEN }}
        run: |
          spectryn \
            --markdown docs/${{ matrix.epic }}.md \
            --epic ${{ matrix.epic }} \
            --execute \
            --no-confirm
```

## GitLab CI

### Basic Pipeline

```yaml
# .gitlab-ci.yml
stages:
  - validate
  - sync

variables:
  EPIC_KEY: "PROJ-123"

validate-markdown:
  stage: validate
  image: python:3.12
  script:
    - pip install spectryn
    - spectryn --markdown docs/EPIC.md --epic $EPIC_KEY --validate
  rules:
    - changes:
        - docs/EPIC.md

sync-to-jira:
  stage: sync
  image: python:3.12
  variables:
    JIRA_URL: $JIRA_URL
    JIRA_EMAIL: $JIRA_EMAIL
    JIRA_API_TOKEN: $JIRA_API_TOKEN
  script:
    - pip install spectryn
    - spectryn --markdown docs/EPIC.md --epic $EPIC_KEY --execute --no-confirm
  rules:
    - if: $CI_COMMIT_BRANCH == "main"
      changes:
        - docs/EPIC.md
  artifacts:
    reports:
      dotenv: sync-results.env
```

### With Docker

```yaml
# .gitlab-ci.yml
sync-jira:
  image: adrianthehactus/spectryn:latest
  stage: deploy
  variables:
    JIRA_URL: $JIRA_URL
    JIRA_EMAIL: $JIRA_EMAIL
    JIRA_API_TOKEN: $JIRA_API_TOKEN
  script:
    - spectryn --markdown docs/EPIC.md --epic $EPIC_KEY --execute --no-confirm
  only:
    refs:
      - main
    changes:
      - docs/EPIC.md
```

## Jenkins

### Declarative Pipeline

```groovy
// Jenkinsfile
pipeline {
    agent {
        docker {
            image 'python:3.12'
        }
    }
    
    environment {
        JIRA_URL = credentials('jira-url')
        JIRA_EMAIL = credentials('jira-email')
        JIRA_API_TOKEN = credentials('jira-api-token')
        EPIC_KEY = 'PROJ-123'
    }
    
    stages {
        stage('Install') {
            steps {
                sh 'pip install spectryn'
            }
        }
        
        stage('Validate') {
            steps {
                sh "spectryn --markdown docs/EPIC.md --epic ${EPIC_KEY} --validate"
            }
        }
        
        stage('Preview') {
            when {
                not { branch 'main' }
            }
            steps {
                sh "spectryn --markdown docs/EPIC.md --epic ${EPIC_KEY}"
            }
        }
        
        stage('Sync') {
            when {
                branch 'main'
            }
            steps {
                sh "spectryn --markdown docs/EPIC.md --epic ${EPIC_KEY} --execute --no-confirm"
            }
        }
    }
    
    post {
        success {
            slackSend channel: '#jira-sync',
                      message: "✅ Jira sync completed for ${EPIC_KEY}"
        }
        failure {
            slackSend channel: '#jira-sync',
                      message: "❌ Jira sync failed for ${EPIC_KEY}"
        }
    }
}
```

## CircleCI

```yaml
# .circleci/config.yml
version: 2.1

jobs:
  sync-jira:
    docker:
      - image: cimg/python:3.12
    steps:
      - checkout
      - run:
          name: Install spectryn
          command: pip install spectryn
      - run:
          name: Sync to Jira
          command: |
            spectryn \
              --markdown docs/EPIC.md \
              --epic $EPIC_KEY \
              --execute \
              --no-confirm \
              --export results.json
      - store_artifacts:
          path: results.json

workflows:
  sync:
    jobs:
      - sync-jira:
          filters:
            branches:
              only: main
```

## Error Handling

### Handle Partial Success

```yaml
# GitHub Actions
- name: Sync to Jira
  id: sync
  continue-on-error: true
  run: |
    spectryn --markdown docs/EPIC.md --epic $EPIC_KEY --execute --no-confirm
    echo "exit_code=$?" >> $GITHUB_OUTPUT

- name: Check result
  run: |
    if [ "${{ steps.sync.outputs.exit_code }}" -eq "64" ]; then
      echo "::warning::Sync completed with some failures"
    elif [ "${{ steps.sync.outputs.exit_code }}" -ne "0" ]; then
      echo "::error::Sync failed"
      exit 1
    fi
```

### Retry on Transient Errors

```yaml
# GitHub Actions
- name: Sync with retry
  uses: nick-fields/retry@v2
  with:
    timeout_minutes: 10
    max_attempts: 3
    retry_on: error
    command: |
      spectryn --markdown docs/EPIC.md --epic $EPIC_KEY --execute --no-confirm
```

## Secrets Management

### GitHub

Set up secrets in repository settings:

1. Go to Settings → Secrets and variables → Actions
2. Add repository secrets:
   - `JIRA_URL`
   - `JIRA_EMAIL`
   - `JIRA_API_TOKEN`
3. Add repository variables:
   - `EPIC_KEY`

### GitLab

Set up variables in CI/CD settings:

1. Go to Settings → CI/CD → Variables
2. Add variables (masked and protected):
   - `JIRA_URL`
   - `JIRA_EMAIL`
   - `JIRA_API_TOKEN`
   - `EPIC_KEY`

### Jenkins

Use Jenkins credentials:

```groovy
environment {
    JIRA_CREDS = credentials('jira-credentials')
    // Exposes JIRA_CREDS_USR and JIRA_CREDS_PSW
}
```

