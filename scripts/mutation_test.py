#!/usr/bin/env python3
"""
Mutation Testing Script for spectryn.

This script runs mutation testing on specific modules and generates reports.
Mutation testing helps verify test quality by introducing small code changes
(mutations) and checking if tests catch them.

Usage:
    # Run on all core modules
    python scripts/mutation_test.py
    
    # Run on specific module
    python scripts/mutation_test.py --module result
    
    # Run with HTML report
    python scripts/mutation_test.py --html
    
    # Show surviving mutants only
    python scripts/mutation_test.py --survivors

Requirements:
    pip install mutmut

How it works:
    1. mutmut creates mutations (small code changes) in source files
    2. For each mutation, it runs the test suite
    3. If tests pass with a mutation, the mutant "survived" (test gap found!)
    4. If tests fail, the mutant was "killed" (tests are effective)

Interpreting results:
    - Killed: Tests caught the mutation (good!)
    - Survived: Tests didn't catch it (potential test gap)
    - Timeout: Test took too long (likely infinite loop mutation)
    - Suspicious: Unusual behavior during test
"""

import argparse
import subprocess
import sys
from pathlib import Path


# Modules to test with mutation testing
MUTATION_TARGETS = {
    "result": "src/spectryn/core/result.py",
    "specification": "src/spectryn/core/specification.py",
    "container": "src/spectryn/core/container.py",
    "exceptions": "src/spectryn/core/exceptions.py",
    "constants": "src/spectryn/core/constants.py",
    "entities": "src/spectryn/core/domain/entities.py",
    "value_objects": "src/spectryn/core/domain/value_objects.py",
    "enums": "src/spectryn/core/domain/enums.py",
}


def run_mutation_test(
    module: str | None = None,
    quick: bool = False,
    html: bool = False,
    survivors_only: bool = False,
) -> int:
    """
    Run mutation testing.
    
    Args:
        module: Specific module to test (or None for all)
        quick: Run quick mode (fewer mutations)
        html: Generate HTML report
        survivors_only: Only show surviving mutants
        
    Returns:
        Exit code (0 = success, 1 = survivors found)
    """
    # Determine paths to mutate
    if module:
        if module not in MUTATION_TARGETS:
            print(f"Unknown module: {module}")
            print(f"Available: {', '.join(MUTATION_TARGETS.keys())}")
            return 1
        paths = MUTATION_TARGETS[module]
        tests = f"tests/core/test_{module}.py"
    else:
        paths = "src/spectryn/core/"
        tests = "tests/core/"

    # Build mutmut command
    cmd = ["mutmut", "run"]
    cmd.extend(["--paths-to-mutate", paths])
    cmd.extend(["--tests-dir", tests])

    if quick:
        # Limit mutations for quick testing
        cmd.extend(["--simple-status"])

    print(f"🧬 Running mutation tests on: {paths}")
    print(f"📋 Using tests from: {tests}")
    print("-" * 60)

    # Run mutation testing
    result = subprocess.run(cmd, check=False, cwd=Path(__file__).parent.parent)

    # Show results
    print()
    print("=" * 60)
    print("📊 Mutation Testing Results")
    print("=" * 60)

    # Get results summary
    subprocess.run(["mutmut", "results"], check=False, cwd=Path(__file__).parent.parent)

    # Show survivors if requested
    if survivors_only:
        print()
        print("-" * 60)
        print("🧟 Surviving Mutants (Test Gaps)")
        print("-" * 60)
        subprocess.run(
            ["mutmut", "results", "--only-survivors"],
            check=False, cwd=Path(__file__).parent.parent
        )

    # Generate HTML report if requested
    if html:
        print()
        print("📄 Generating HTML report...")
        subprocess.run(
            ["mutmut", "html"],
            check=False, cwd=Path(__file__).parent.parent
        )
        print("Report generated: html/index.html")

    return result.returncode


def show_surviving_mutant(mutant_id: int) -> None:
    """Show diff for a specific surviving mutant."""
    subprocess.run(
        ["mutmut", "show", str(mutant_id)],
        check=False, cwd=Path(__file__).parent.parent
    )


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run mutation testing on spectryn modules"
    )
    parser.add_argument(
        "--module", "-m",
        choices=list(MUTATION_TARGETS.keys()),
        help="Specific module to test"
    )
    parser.add_argument(
        "--quick", "-q",
        action="store_true",
        help="Quick mode (fewer mutations)"
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="Generate HTML report"
    )
    parser.add_argument(
        "--survivors", "-s",
        action="store_true",
        help="Show surviving mutants only"
    )
    parser.add_argument(
        "--show",
        type=int,
        metavar="ID",
        help="Show diff for a specific mutant ID"
    )

    args = parser.parse_args()

    if args.show:
        show_surviving_mutant(args.show)
        return 0

    return run_mutation_test(
        module=args.module,
        quick=args.quick,
        html=args.html,
        survivors_only=args.survivors,
    )


if __name__ == "__main__":
    sys.exit(main())

