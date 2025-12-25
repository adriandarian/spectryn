"""
YouTrack Adapter - Integration with JetBrains YouTrack.

This module provides the YouTrackAdapter and related components for
syncing user stories to YouTrack issue tracker.
"""

from spectra.adapters.youtrack.adapter import YouTrackAdapter
from spectra.adapters.youtrack.client import YouTrackApiClient


__all__ = ["YouTrackAdapter", "YouTrackApiClient"]
