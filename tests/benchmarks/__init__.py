"""
Performance Benchmarks for md2jira.

This module contains performance benchmarks for critical operations.
Run with: pytest tests/benchmarks/ --benchmark-only

Benchmarks help:
- Detect performance regressions
- Compare implementation alternatives
- Track performance over time
- Identify bottlenecks

Usage:
    # Run all benchmarks
    pytest tests/benchmarks/ --benchmark-only
    
    # Save baseline
    pytest tests/benchmarks/ --benchmark-save=baseline
    
    # Compare against baseline
    pytest tests/benchmarks/ --benchmark-compare=baseline
    
    # Generate HTML report
    pytest tests/benchmarks/ --benchmark-only --benchmark-autosave
"""

