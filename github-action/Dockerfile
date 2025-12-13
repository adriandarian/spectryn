# GitHub Action for md2jira
FROM python:3.12-slim

LABEL maintainer="md2jira"
LABEL org.opencontainers.image.source="https://github.com/md2jira/md2jira"
LABEL org.opencontainers.image.description="Sync markdown documentation to Jira"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install md2jira
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Install md2jira from the parent directory (when building from repo)
# For published action, this would install from PyPI
COPY setup.py pyproject.toml README.md /app/
COPY src/ /app/src/
WORKDIR /app
RUN pip install --no-cache-dir -e .

# Copy entrypoint script
COPY github-action/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Set working directory to GitHub workspace
WORKDIR /github/workspace

ENTRYPOINT ["/entrypoint.sh"]

