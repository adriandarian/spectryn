# Contributing

Thank you for your interest in contributing to spectryn! This guide will help you get started.

## Code of Conduct

Please read and follow our [Code of Conduct](https://github.com/adriandarian/spectryn/blob/main/CODE_OF_CONDUCT.md).

## Getting Started

### Prerequisites

- Python 3.10 or higher
- Git

### Development Setup

```bash
# Clone the repository
git clone https://github.com/adriandarian/spectryn.git
cd spectryn

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode with dev dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/spectryn

# Run specific test file
pytest tests/cli/test_cli.py

# Run with verbose output
pytest -v
```

### Code Quality

```bash
# Format code
ruff format src/ tests/

# Lint
ruff check src/ tests/

# Type checking
mypy src/

# Run all checks
pre-commit run --all-files
```

## Making Changes

### Workflow

1. **Fork** the repository
2. **Create a branch** for your changes:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Make your changes** with clear, atomic commits
4. **Write tests** for new functionality
5. **Run the test suite** to ensure nothing is broken
6. **Submit a Pull Request**

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add support for Linear adapter
fix: handle empty description gracefully
docs: update configuration guide
test: add tests for backup functionality
refactor: simplify command execution flow
chore: update dependencies
```

### Pull Request Guidelines

- **Title**: Use conventional commit format
- **Description**: Explain what and why, not how
- **Tests**: Include tests for new functionality
- **Documentation**: Update docs for user-facing changes
- **Changelog**: Add entry to CHANGELOG.md for notable changes

## Project Structure

```
spectryn/
├── src/spectryn/        # Source code
│   ├── core/           # Domain logic and ports
│   ├── adapters/       # Infrastructure implementations
│   ├── application/    # Use cases and orchestration
│   ├── cli/            # Command line interface
│   └── plugins/        # Extension system
├── tests/              # Test suite
├── docs/               # Documentation (original markdown)
├── website/            # VitePress documentation site
└── packaging/          # Distribution packages
```

## Areas for Contribution

### Good First Issues

Look for issues labeled [`good first issue`](https://github.com/adriandarian/spectryn/labels/good%20first%20issue).

### Feature Requests

Check the [Issues](https://github.com/adriandarian/spectryn/issues) page for planned features and open discussions.

### Documentation

- Fix typos or unclear explanations
- Add examples
- Translate to other languages

### Testing

- Increase test coverage
- Add edge case tests
- Add integration tests

### New Adapters

Want to add support for a new issue tracker? See the [Plugin Guide](/guide/plugins).

## Development Tips

### Running Locally

```bash
# Run spectryn from source
python -m spectryn --help

# Or use the installed command
spectryn --help
```

### Debugging

```bash
# Enable debug logging
spectryn --markdown EPIC.md --epic TEST-1 -v

# Use Python debugger
python -m pdb -m spectryn --markdown EPIC.md --epic TEST-1
```

### Testing Against Jira

Create a test project in Jira Cloud for development:

1. Create a free Jira Cloud instance
2. Set up a test project with an epic
3. Configure credentials in `.env` (git-ignored)

## Release Process

Releases are handled by maintainers:

1. Update version in `pyproject.toml`
2. Update CHANGELOG.md
3. Create a release tag: `git tag v1.0.0`
4. Push tag: `git push --tags`
5. GitHub Actions publishes to PyPI

## Questions?

- **Bug reports**: [GitHub Issues](https://github.com/adriandarian/spectryn/issues)
- **Feature requests**: [GitHub Discussions](https://github.com/adriandarian/spectryn/discussions)
- **Security issues**: See [SECURITY.md](https://github.com/adriandarian/spectryn/blob/main/SECURITY.md)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

