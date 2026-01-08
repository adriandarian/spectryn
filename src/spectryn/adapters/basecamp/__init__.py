"""
Basecamp Adapter - Integration with Basecamp 3.

Maps Spectra's domain model to Basecamp:
- Epic → Project or Message Board category
- Story → Todo or Message
- Subtask → Todo list item
- Status → Todo completion status
- Priority → Not natively supported (stored in notes)
- Story Points → Not natively supported (stored in notes)
"""

from .adapter import BasecampAdapter
from .client import BasecampApiClient


__all__ = ["BasecampAdapter", "BasecampApiClient"]
