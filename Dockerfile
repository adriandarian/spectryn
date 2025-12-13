# ==============================================================================
# md2jira Dockerfile
# Production-ready containerized CLI tool for syncing markdown to Jira
# ==============================================================================

# Build stage - install dependencies and build the package
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Copy only the files needed for installation
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Build the wheel
RUN pip wheel --no-cache-dir --wheel-dir /wheels .

# ==============================================================================
# Runtime stage - minimal image with only runtime dependencies
# ==============================================================================
FROM python:3.12-slim AS runtime

# Labels following OCI standards
LABEL org.opencontainers.image.title="md2jira"
LABEL org.opencontainers.image.description="A production-grade CLI tool for synchronizing markdown documentation with Jira"
LABEL org.opencontainers.image.version="2.0.0"
LABEL org.opencontainers.image.authors="Adrian Darian <adrian.the.hactus@gmail.com>"
LABEL org.opencontainers.image.source="https://github.com/adriandarian/md2jira"
LABEL org.opencontainers.image.licenses="MIT"

# Create non-root user for security
RUN groupadd --gid 1000 md2jira \
    && useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash md2jira

# Set working directory
WORKDIR /workspace

# Install the wheel from builder stage
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl \
    && rm -rf /wheels

# Switch to non-root user
USER md2jira

# Set environment variables
# Note: Users should provide their own JIRA credentials at runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Default entrypoint is the md2jira CLI
ENTRYPOINT ["md2jira"]

# Default command shows help
CMD ["--help"]

