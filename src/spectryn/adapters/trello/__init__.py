"""
Trello Adapter - Integration with Trello boards and cards.

Maps Spectra's domain model to Trello:
- Epic → Board or List (epic list)
- Story → Card
- Subtask → Checklist item or linked card
- Status → List (board lists)
- Priority → Labels
- Story Points → Custom field or card description
"""

from .adapter import TrelloAdapter
from .client import TrelloApiClient


__all__ = ["TrelloAdapter", "TrelloApiClient"]
