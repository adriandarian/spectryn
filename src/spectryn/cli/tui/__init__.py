"""
TUI - Interactive Terminal User Interface for Spectra.

Provides a rich, interactive dashboard with:
- Real-time sync progress monitoring
- Epic and story browser with tree navigation
- Conflict resolution UI with diff viewer
- Keyboard navigation and command palette

Requires the 'tui' optional dependency:
    pip install spectra[tui]
"""

from spectryn.cli.tui.app import SpectraTUI, run_tui


__all__ = ["SpectraTUI", "run_tui"]
