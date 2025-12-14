# Makefile for md2jira development
# Run 'make help' to see available targets

.PHONY: help install test lint format typecheck mutation clean

# Default target
help:
	@echo "md2jira Development Commands"
	@echo "============================"
	@echo ""
	@echo "Setup:"
	@echo "  make install      Install all dev dependencies"
	@echo ""
	@echo "Testing:"
	@echo "  make test         Run all tests"
	@echo "  make test-fast    Run tests without slow tests"
	@echo "  make test-cov     Run tests with coverage"
	@echo "  make mutation     Run mutation testing (core modules)"
	@echo ""
	@echo "Benchmarking:"
	@echo "  make bench        Run all benchmarks"
	@echo "  make bench-save   Save benchmark baseline"
	@echo "  make bench-compare Compare against baseline"
	@echo "  make bench-quick  Run quick benchmark subset"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint         Run linter (ruff)"
	@echo "  make format       Format code (ruff + black)"
	@echo "  make typecheck    Run type checker (mypy)"
	@echo "  make check        Run all checks (lint + typecheck + test)"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean        Remove build artifacts and caches"

# Installation
install:
	pip install -e ".[dev,async]"

# Testing
test:
	pytest tests/ -v

test-fast:
	pytest tests/ -v --ignore=tests/integration --ignore=tests/property -x

test-cov:
	pytest tests/ --cov=src/md2jira --cov-report=html --cov-report=term-missing

# Benchmarking
bench:
	@echo "⏱️  Running performance benchmarks..."
	pytest tests/benchmarks/ --benchmark-only --benchmark-group-by=func

bench-save:
	@echo "⏱️  Saving benchmark baseline..."
	pytest tests/benchmarks/ --benchmark-only --benchmark-save=baseline
	@echo "Baseline saved to .benchmarks/"

bench-compare:
	@echo "⏱️  Comparing against baseline..."
	pytest tests/benchmarks/ --benchmark-only --benchmark-compare=baseline

bench-quick:
	@echo "⏱️  Running quick benchmarks..."
	pytest tests/benchmarks/test_result_bench.py -k "creation" --benchmark-only

bench-json:
	@echo "⏱️  Running benchmarks with JSON output..."
	pytest tests/benchmarks/ --benchmark-only --benchmark-json=benchmark_results.json
	@echo "Results saved to benchmark_results.json"

# Mutation Testing
mutation:
	@echo "🧬 Running mutation tests..."
	@echo "This may take several minutes..."
	@echo "Configure source paths in mutmut_config.py"
	mutmut run
	mutmut results

mutation-report:
	mutmut html
	@echo "Report generated at: html/index.html"

mutation-survivors:
	@echo "🧟 Surviving mutants (test gaps):"
	mutmut results

mutation-show:
	@echo "Use: mutmut show <mutant_id> to see specific mutation"

# Code Quality
lint:
	ruff check src/ tests/

format:
	ruff check --fix src/ tests/
	ruff format src/ tests/

typecheck:
	mypy src/md2jira/

check: lint typecheck test

# Cleanup
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .mutmut-cache/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf htmlcov/
	rm -rf html/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

