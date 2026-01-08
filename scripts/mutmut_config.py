"""
Mutmut configuration for mutation testing.

This file configures mutmut for the spectryn project.
Run mutation tests with: mutmut run

See: https://mutmut.readthedocs.io/
"""


def pre_mutation(context):
    """
    Called before each mutation is applied.
    
    Args:
        context: Mutation context with filename, line, etc.
        
    Return True to skip this mutation.
    """
    # Skip mutations in test files
    if "test_" in context.filename:
        return True

    # Skip __init__.py files (usually just re-exports)
    if context.filename.endswith("__init__.py"):
        return True

    # Skip docstrings
    if context.current_source_line.strip().startswith('"""'):
        return True
    if context.current_source_line.strip().startswith("'''"):
        return True

    return False


# Configure source paths
def init():
    """Initialize mutmut configuration."""

