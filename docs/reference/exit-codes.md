# Exit Codes

spectryn uses standard Unix exit codes to indicate how the program terminated. These codes can be used in shell scripts for automation and CI/CD pipelines.

## Quick Reference

| Code | Name | Description |
|------|------|-------------|
| 0 | SUCCESS | Operation completed successfully |
| 1 | ERROR | General error (unspecified failure) |
| 2 | CONFIG_ERROR | Configuration error |
| 3 | FILE_NOT_FOUND | Input file not found |
| 4 | CONNECTION_ERROR | Failed to connect to Jira |
| 5 | AUTH_ERROR | Authentication failed |
| 6 | VALIDATION_ERROR | Input validation failed |
| 7 | PERMISSION_ERROR | Insufficient permissions |
| 8 | API_ERROR | Jira API returned an error |
| 64 | PARTIAL_SUCCESS | Completed with some failures |
| 80 | CANCELLED | Cancelled by user |
| 130 | SIGINT | Interrupted (Ctrl+C) |
| 143 | SIGTERM | Terminated by signal |

## Detailed Descriptions

### Success (0)

The operation completed without any errors.

```bash
spectryn --markdown EPIC.md --epic PROJ-123 --execute
echo $?  # Returns 0
```

### General Error (1)

A general, unspecified error occurred. Check the error message for details.

```bash
spectryn --markdown EPIC.md --epic PROJ-123
if [ $? -eq 1 ]; then
    echo "Something went wrong"
fi
```

### Configuration Error (2)

Configuration is missing or invalid. Common causes:

- Missing required environment variables (`JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`)
- Invalid config file syntax
- Invalid option combinations

```bash
# Missing JIRA_URL
unset JIRA_URL
spectryn --markdown EPIC.md --epic PROJ-123
echo $?  # Returns 2
```

**Fix:** Set required environment variables or provide a valid config file.

### File Not Found (3)

The specified input file does not exist.

```bash
spectryn --markdown nonexistent.md --epic PROJ-123
echo $?  # Returns 3
```

**Fix:** Verify the file path is correct and the file exists.

### Connection Error (4)

Failed to establish a connection to the Jira API. Common causes:

- Network issues
- Invalid Jira URL
- Jira server is down
- Firewall blocking the connection

```bash
export JIRA_URL="https://invalid.atlassian.net"
spectryn --markdown EPIC.md --epic PROJ-123
echo $?  # Returns 4
```

**Fix:** Verify your network connection and Jira URL.

### Authentication Error (5)

Authentication with Jira failed. Common causes:

- Invalid API token
- Incorrect email address
- Token has expired
- Token lacks required permissions

```bash
export JIRA_API_TOKEN="invalid_token"
spectryn --markdown EPIC.md --epic PROJ-123
echo $?  # Returns 5
```

**Fix:** Generate a new API token from [Atlassian Account Settings](https://id.atlassian.com/manage-profile/security/api-tokens).

### Validation Error (6)

The input file failed validation. Common causes:

- Invalid markdown structure
- Missing required sections
- Malformed story/subtask definitions

```bash
spectryn --validate --markdown invalid.md --epic PROJ-123
echo $?  # Returns 6
```

**Fix:** Use `--validate` to check your markdown file and fix reported issues.

### Permission Error (7)

Insufficient permissions to perform the requested operation. Common causes:

- User lacks edit permissions on the project
- User cannot create subtasks
- User cannot transition issues

```bash
spectryn --markdown EPIC.md --epic RESTRICTED-123 --execute
echo $?  # Returns 7
```

**Fix:** Contact your Jira administrator to request necessary permissions.

### API Error (8)

Jira API returned an error. This can occur due to:

- Issue doesn't exist
- Invalid field values
- Rate limiting
- Server-side errors

```bash
spectryn --markdown EPIC.md --epic INVALID-999 --execute
echo $?  # Returns 8
```

**Fix:** Check the error message for specific API error details.

### Partial Success (64)

The operation completed, but some individual operations failed. With graceful degradation enabled, spectryn continues processing even when some issues fail.

```bash
spectryn --markdown EPIC.md --epic PROJ-123 --execute
if [ $? -eq 64 ]; then
    echo "Sync completed with some failures - check the report"
fi
```

**Fix:** Review the error report to address individual failures.

### Cancelled (80)

The operation was cancelled by the user via a confirmation prompt.

```bash
spectryn --markdown EPIC.md --epic PROJ-123 --execute
# User types 'n' at confirmation prompt
echo $?  # Returns 80
```

### Interrupted - SIGINT (130)

The operation was interrupted by the user pressing Ctrl+C.

### Terminated - SIGTERM (143)

The process was terminated by a SIGTERM signal (e.g., from `kill` command).

## Using Exit Codes in Scripts

### Basic Error Handling

```bash
#!/bin/bash

spectryn --markdown EPIC.md --epic PROJ-123 --execute --no-confirm
EXIT_CODE=$?

case $EXIT_CODE in
    0)
        echo "✓ Sync completed successfully"
        ;;
    64)
        echo "⚠ Sync completed with some failures"
        # Continue - partial success is acceptable
        ;;
    2)
        echo "✗ Configuration error - check environment"
        exit 1
        ;;
    5)
        echo "✗ Authentication failed - check API token"
        exit 1
        ;;
    130)
        echo "Interrupted by user"
        exit 0
        ;;
    *)
        echo "✗ Sync failed with exit code $EXIT_CODE"
        exit 1
        ;;
esac
```

### CI/CD Pipeline Example

```yaml
# GitHub Actions example
- name: Sync to Jira
  id: sync
  run: |
    spectryn --markdown EPIC.md --epic ${{ env.EPIC_KEY }} --execute --no-confirm
  continue-on-error: true
  
- name: Check sync result
  run: |
    if [ "${{ steps.sync.outcome }}" = "failure" ]; then
      echo "::warning::Jira sync failed"
    fi
```

### Retry on Transient Errors

```bash
#!/bin/bash

MAX_RETRIES=3
RETRY_DELAY=5

for i in $(seq 1 $MAX_RETRIES); do
    spectryn --markdown EPIC.md --epic PROJ-123 --execute --no-confirm
    EXIT_CODE=$?
    
    case $EXIT_CODE in
        0|64)
            # Success or partial success
            exit 0
            ;;
        4|8)
            # Connection or API error - might be transient
            if [ $i -lt $MAX_RETRIES ]; then
                echo "Attempt $i failed, retrying in ${RETRY_DELAY}s..."
                sleep $RETRY_DELAY
                RETRY_DELAY=$((RETRY_DELAY * 2))
            else
                echo "Failed after $MAX_RETRIES attempts"
                exit 1
            fi
            ;;
        *)
            # Non-transient error
            exit 1
            ;;
    esac
done
```

## Programmatic Access

Exit codes are also available programmatically:

```python
from spectryn.cli.exit_codes import ExitCode

# Check exit code meaning
print(ExitCode.CONFIG_ERROR.description)
# Output: "Configuration error - check environment variables or config file"

# Convert exception to exit code
try:
    # ... operation
except Exception as e:
    exit_code = ExitCode.from_exception(e)
    sys.exit(exit_code)
```

## Exit Code Conventions

spectryn follows standard Unix conventions:

- **0**: Success
- **1-63**: Standard errors
- **64-79**: Partial success / warnings
- **80-127**: User actions (cancelled, etc.)
- **128+N**: Terminated by signal N (e.g., 130 = 128 + 2 for SIGINT)

This allows scripts to distinguish between different failure modes and handle them appropriately.

