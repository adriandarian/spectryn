# Docker Usage

spectryn provides official Docker images for containerized usage, perfect for CI/CD pipelines and consistent environments.

## Quick Start

### Pull the Image

```bash
docker pull adrianthehactus/spectryn:latest
```

### Basic Usage

```bash
docker run --rm \
  -e JIRA_URL=https://your-company.atlassian.net \
  -e JIRA_EMAIL=your.email@company.com \
  -e JIRA_API_TOKEN=your-api-token \
  -v $(pwd):/workspace \
  adrianthehactus/spectryn:latest \
  --markdown EPIC.md --epic PROJ-123
```

### Execute Sync

```bash
docker run --rm \
  -e JIRA_URL=https://your-company.atlassian.net \
  -e JIRA_EMAIL=your.email@company.com \
  -e JIRA_API_TOKEN=your-api-token \
  -v $(pwd):/workspace \
  adrianthehactus/spectryn:latest \
  --markdown EPIC.md --epic PROJ-123 --execute
```

## Docker Compose

For easier management with persistent configuration:

### docker compose.yml

```yaml
services:
  spectryn:
    image: adrianthehactus/spectryn:latest
    env_file:
      - .env
    volumes:
      - .:/workspace
    working_dir: /workspace
```

### .env File

```bash
JIRA_URL=https://your-company.atlassian.net
JIRA_EMAIL=your.email@company.com
JIRA_API_TOKEN=your-api-token
```

### Running with Docker Compose

```bash
# Preview changes (dry-run)
docker compose run --rm spectryn --markdown EPIC.md --epic PROJ-123

# Execute sync
docker compose run --rm spectryn --markdown EPIC.md --epic PROJ-123 --execute

# With verbose output
docker compose run --rm spectryn --markdown EPIC.md --epic PROJ-123 -v

# Specific phase only
docker compose run --rm spectryn --markdown EPIC.md --epic PROJ-123 --execute --phase subtasks
```

## Building Locally

Build the image from source:

```bash
git clone https://github.com/adriandarian/spectryn.git
cd spectryn
docker build -t spectryn:local .
```

### Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy source
COPY src/ src/

# Set entrypoint
ENTRYPOINT ["spectryn"]
CMD ["--help"]

# Default working directory for mounted files
WORKDIR /workspace
```

## CI/CD Integration

### GitHub Actions

```yaml
name: Sync to Jira

on:
  push:
    paths:
      - 'docs/EPIC.md'

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Sync to Jira
        run: |
          docker run --rm \
            -e JIRA_URL=${{ secrets.JIRA_URL }} \
            -e JIRA_EMAIL=${{ secrets.JIRA_EMAIL }} \
            -e JIRA_API_TOKEN=${{ secrets.JIRA_API_TOKEN }} \
            -v ${{ github.workspace }}:/workspace \
            adrianthehactus/spectryn:latest \
            --markdown docs/EPIC.md \
            --epic ${{ vars.EPIC_KEY }} \
            --execute \
            --no-confirm
```

### GitLab CI

```yaml
sync-jira:
  image: adrianthehactus/spectryn:latest
  variables:
    JIRA_URL: $JIRA_URL
    JIRA_EMAIL: $JIRA_EMAIL
    JIRA_API_TOKEN: $JIRA_API_TOKEN
  script:
    - spectryn --markdown EPIC.md --epic PROJ-123 --execute --no-confirm
  rules:
    - changes:
        - EPIC.md
```

### Jenkins

```groovy
pipeline {
    agent {
        docker {
            image 'adrianthehactus/spectryn:latest'
        }
    }
    
    environment {
        JIRA_URL = credentials('jira-url')
        JIRA_EMAIL = credentials('jira-email')
        JIRA_API_TOKEN = credentials('jira-token')
    }
    
    stages {
        stage('Sync') {
            steps {
                sh 'spectryn --markdown EPIC.md --epic PROJ-123 --execute --no-confirm'
            }
        }
    }
}
```

## Advanced Configuration

### Custom Config File

Mount a config file for complex configurations:

```bash
docker run --rm \
  -v $(pwd):/workspace \
  -v ~/.spectryn.yaml:/root/.spectryn.yaml:ro \
  adrianthehactus/spectryn:latest \
  --markdown EPIC.md --epic PROJ-123
```

### Using env-file

```bash
docker run --rm \
  --env-file .env \
  -v $(pwd):/workspace \
  adrianthehactus/spectryn:latest \
  --markdown EPIC.md --epic PROJ-123
```

### Export Results

Mount a volume to save export files:

```bash
docker run --rm \
  -e JIRA_URL=... \
  -e JIRA_EMAIL=... \
  -e JIRA_API_TOKEN=... \
  -v $(pwd):/workspace \
  adrianthehactus/spectryn:latest \
  --markdown EPIC.md --epic PROJ-123 --execute --export results.json
```

The `results.json` file will be saved in your current directory.

## Image Tags

| Tag | Description |
|-----|-------------|
| `latest` | Latest stable release |
| `x.y.z` | Specific version (e.g., `1.0.0`) |
| `main` | Latest development build |

## Troubleshooting

### Permission Issues

If you get permission errors, run with your user ID:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -e JIRA_URL=... \
  -v $(pwd):/workspace \
  adrianthehactus/spectryn:latest \
  --markdown EPIC.md --epic PROJ-123
```

### Network Issues

If the container can't reach Jira:

```bash
# Use host network mode
docker run --rm \
  --network host \
  -e JIRA_URL=... \
  -v $(pwd):/workspace \
  adrianthehactus/spectryn:latest \
  --markdown EPIC.md --epic PROJ-123
```

### Debug Mode

Run with verbose output to troubleshoot:

```bash
docker run --rm \
  -e JIRA_URL=... \
  -v $(pwd):/workspace \
  adrianthehactus/spectryn:latest \
  --markdown EPIC.md --epic PROJ-123 -v --log-format json
```

