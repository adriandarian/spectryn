# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 2.x.x   | :white_check_mark: |
| < 2.0   | :x:                |

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security issue, please report it responsibly.

### How to Report

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, please report security issues via one of the following methods:

1. **Email**: Send details to the maintainer at [adrian.the.hactus@gmail.com](mailto:adrian.the.hactus@gmail.com)
2. **GitHub Security Advisories**: Use [GitHub's private vulnerability reporting](https://github.com/adriandarian/spectryn/security/advisories/new)

### What to Include

When reporting a vulnerability, please include:

- A clear description of the vulnerability
- Steps to reproduce the issue
- Affected versions
- Potential impact assessment
- Any suggested fixes (optional but appreciated)

### Response Timeline

- **Acknowledgment**: Within 48 hours
- **Initial Assessment**: Within 7 days
- **Resolution Target**: Within 30 days for critical issues, 90 days for others

We will keep you informed of progress and may reach out for additional information.

## Security Considerations

### Credential Management

spectryn requires Jira API credentials to function. Please follow these best practices:

#### ✅ Do

- Store credentials in environment variables or `.env` files
- Add `.env` to your `.gitignore` file
- Use [Jira API tokens](https://id.atlassian.com/manage-profile/security/api-tokens) instead of passwords
- Rotate API tokens periodically
- Use tokens with minimal required permissions

#### ❌ Don't

- Commit credentials to version control
- Share API tokens in plain text
- Use personal account tokens for shared automation
- Store tokens in markdown files or command history

### Environment Variables

The following environment variables contain sensitive data:

| Variable | Description | Sensitivity |
|----------|-------------|-------------|
| `JIRA_URL` | Jira instance URL | Low |
| `JIRA_EMAIL` | User email for authentication | Medium |
| `JIRA_API_TOKEN` | API token for authentication | **High** |

### API Token Permissions

When creating a Jira API token, the token inherits the permissions of your Jira account. Consider:

- Using a dedicated service account with limited project access
- Granting only the permissions needed (read/write to specific projects)
- Avoiding admin-level tokens for routine sync operations

### Network Security

- All communication with Jira uses HTTPS
- API tokens are sent via HTTP Basic Authentication headers
- No credentials are logged or written to output files

### Dry-Run Mode

By default, spectryn operates in **dry-run mode**, which:

- Shows what changes would be made without executing them
- Prevents accidental modifications to Jira issues
- Allows safe review before committing changes

Always use dry-run mode first when working with new markdown files or configurations.

## Dependency Security

### Monitoring

We use the following tools to monitor dependencies:

- Dependabot for automated dependency updates
- Regular security audits of the dependency tree

### Minimal Dependencies

spectryn maintains a minimal dependency footprint:

- `requests` - HTTP client for Jira API communication

Development dependencies are isolated and not installed in production.

### Auditing Dependencies

```bash
# Check for known vulnerabilities
pip-audit

# Review dependency tree
pip list --format=freeze
```

## Secure Development Practices

### Code Review

- All changes require code review before merging
- Security-sensitive changes require additional scrutiny
- Automated linting and type checking enforce code quality

### Testing

- Unit tests cover security-critical paths
- No credentials in test fixtures
- Mocked API responses for testing

### Release Process

- Signed releases (when applicable)
- Changelog documents security-related changes
- Version pinning for reproducible builds

## Known Limitations

### Token Storage

spectryn does not provide encrypted credential storage. Users are responsible for:

- Securing their `.env` files
- Using system keychain or secret managers in CI/CD environments
- Following their organization's security policies

### Audit Logging

While spectryn provides command-level logging and dry-run previews:

- Detailed audit logs are not persisted by default
- Use `--export` flag to save operation results for audit purposes
- Consider integrating with your organization's logging infrastructure

## Security Checklist for Users

Before using spectryn in production:

- [ ] API token stored securely (not in version control)
- [ ] `.env` added to `.gitignore`
- [ ] Using a service account or limited-permission token
- [ ] Tested with dry-run mode first
- [ ] Reviewed exported changes before execution
- [ ] Enabled confirmation prompts (default behavior)

## Acknowledgments

We appreciate the security research community's efforts in responsibly disclosing vulnerabilities. Contributors who report valid security issues will be acknowledged (with permission) in our release notes.

---

*Last updated: December 2024*

