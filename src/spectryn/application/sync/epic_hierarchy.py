"""
Epic Hierarchy - Support multi-level epic hierarchies.

This module provides support for nested epic structures:
- Parent/child epic relationships
- Initiative > Epic > Feature > Story hierarchy
- Portfolio-level epic trees
- Hierarchy visualization and traversal
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from spectryn.core.ports.issue_tracker import IssueTrackerPort

logger = logging.getLogger(__name__)


class EpicLevel(Enum):
    """Hierarchy level of an epic."""

    PORTFOLIO = "portfolio"  # Top-level strategic initiative
    INITIATIVE = "initiative"  # Large strategic initiative
    THEME = "theme"  # Grouping of related epics
    EPIC = "epic"  # Standard epic
    FEATURE = "feature"  # Feature-level epic
    CAPABILITY = "capability"  # Capability grouping

    @classmethod
    def from_string(cls, value: str) -> "EpicLevel":
        """Parse level from string."""
        value_lower = value.lower().strip()
        mappings = {
            "portfolio": cls.PORTFOLIO,
            "initiative": cls.INITIATIVE,
            "theme": cls.THEME,
            "epic": cls.EPIC,
            "feature": cls.FEATURE,
            "capability": cls.CAPABILITY,
        }
        return mappings.get(value_lower, cls.EPIC)

    @property
    def depth(self) -> int:
        """Get hierarchy depth (lower is higher level)."""
        depths = {
            EpicLevel.PORTFOLIO: 0,
            EpicLevel.INITIATIVE: 1,
            EpicLevel.THEME: 2,
            EpicLevel.EPIC: 3,
            EpicLevel.FEATURE: 4,
            EpicLevel.CAPABILITY: 5,
        }
        return depths.get(self, 3)


@dataclass
class EpicNode:
    """
    A node in the epic hierarchy tree.

    Represents an epic with its position in the hierarchy.
    """

    id: str  # Epic key or ID
    title: str
    level: EpicLevel = EpicLevel.EPIC

    # Hierarchy
    parent_id: str | None = None
    children: list["EpicNode"] = field(default_factory=list)

    # Metadata
    status: str = ""
    summary: str = ""
    external_key: str | None = None

    # Aggregated metrics
    story_count: int = 0
    total_points: int = 0
    completion_pct: float = 0.0

    # Sync metadata
    synced: bool = False
    synced_at: datetime | None = None

    def add_child(self, child: "EpicNode") -> None:
        """Add a child epic."""
        child.parent_id = self.id
        self.children.append(child)

    def find_child(self, epic_id: str) -> "EpicNode | None":
        """Find a child by ID (direct children only)."""
        for child in self.children:
            if child.id == epic_id:
                return child
        return None

    def find_descendant(self, epic_id: str) -> "EpicNode | None":
        """Find a descendant by ID (recursive search)."""
        if self.id == epic_id:
            return self

        for child in self.children:
            found = child.find_descendant(epic_id)
            if found:
                return found

        return None

    def get_path(self) -> list[str]:
        """Get path from root to this node."""
        # This would need parent reference for full path
        return [self.id]

    def get_all_descendants(self) -> list["EpicNode"]:
        """Get all descendants (children, grandchildren, etc.)."""
        descendants = []
        for child in self.children:
            descendants.append(child)
            descendants.extend(child.get_all_descendants())
        return descendants

    def aggregate_metrics(self) -> None:
        """Aggregate metrics from children."""
        for child in self.children:
            child.aggregate_metrics()
            self.story_count += child.story_count
            self.total_points += child.total_points

        # Calculate completion based on children
        if self.children:
            total_completion = sum(c.completion_pct for c in self.children)
            self.completion_pct = total_completion / len(self.children)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "title": self.title,
            "level": self.level.value,
            "parent_id": self.parent_id,
            "children": [c.to_dict() for c in self.children],
            "status": self.status,
            "summary": self.summary,
            "external_key": self.external_key,
            "story_count": self.story_count,
            "total_points": self.total_points,
            "completion_pct": self.completion_pct,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EpicNode":
        """Create from dictionary."""
        node = cls(
            id=data.get("id", ""),
            title=data.get("title", ""),
            level=EpicLevel.from_string(data.get("level", "epic")),
            parent_id=data.get("parent_id"),
            status=data.get("status", ""),
            summary=data.get("summary", ""),
            external_key=data.get("external_key"),
            story_count=data.get("story_count", 0),
            total_points=data.get("total_points", 0),
            completion_pct=data.get("completion_pct", 0.0),
        )

        for child_data in data.get("children", []):
            child = cls.from_dict(child_data)
            node.add_child(child)

        return node


@dataclass
class EpicHierarchy:
    """
    Complete epic hierarchy tree.

    Supports multiple root nodes for portfolio-level views.
    """

    roots: list[EpicNode] = field(default_factory=list)
    _node_index: dict[str, EpicNode] = field(default_factory=dict)

    def add_root(self, node: EpicNode) -> None:
        """Add a root epic."""
        self.roots.append(node)
        self._index_node(node)

    def _index_node(self, node: EpicNode) -> None:
        """Add node to index for fast lookup."""
        self._node_index[node.id] = node
        for child in node.children:
            self._index_node(child)

    def find_node(self, epic_id: str) -> EpicNode | None:
        """Find an epic by ID."""
        return self._node_index.get(epic_id)

    def add_node(
        self,
        node: EpicNode,
        parent_id: str | None = None,
    ) -> bool:
        """
        Add a node to the hierarchy.

        Args:
            node: Node to add
            parent_id: Parent node ID (None = root)

        Returns:
            True if added successfully
        """
        if parent_id is None:
            self.add_root(node)
            return True

        parent = self.find_node(parent_id)
        if parent:
            parent.add_child(node)
            self._node_index[node.id] = node
            return True

        return False

    def get_ancestors(self, epic_id: str) -> list[EpicNode]:
        """Get all ancestors of an epic (parent, grandparent, etc.)."""
        node = self.find_node(epic_id)
        if not node:
            return []

        ancestors = []
        current_id = node.parent_id
        while current_id:
            parent = self.find_node(current_id)
            if parent:
                ancestors.append(parent)
                current_id = parent.parent_id
            else:
                break

        return ancestors

    def get_depth(self, epic_id: str) -> int:
        """Get depth of an epic in the hierarchy (0 = root)."""
        return len(self.get_ancestors(epic_id))

    def get_all_nodes(self) -> list[EpicNode]:
        """Get all nodes in the hierarchy."""
        return list(self._node_index.values())

    def get_nodes_at_level(self, level: EpicLevel) -> list[EpicNode]:
        """Get all nodes at a specific level."""
        return [n for n in self._node_index.values() if n.level == level]

    def aggregate_all_metrics(self) -> None:
        """Aggregate metrics for all nodes (call after building tree)."""
        for root in self.roots:
            root.aggregate_metrics()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "roots": [r.to_dict() for r in self.roots],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EpicHierarchy":
        """Create from dictionary."""
        hierarchy = cls()
        for root_data in data.get("roots", []):
            root = EpicNode.from_dict(root_data)
            hierarchy.add_root(root)
        return hierarchy

    def to_tree_string(self, indent: str = "  ") -> str:
        """Generate a tree representation as string."""
        lines = []

        def render_node(node: EpicNode, prefix: str = "") -> None:
            status_icon = "✓" if node.completion_pct >= 100 else "○"
            lines.append(f"{prefix}{status_icon} [{node.level.value}] {node.id}: {node.title}")
            for i, child in enumerate(node.children):
                is_last = i == len(node.children) - 1
                child_prefix = prefix + ("└─ " if is_last else "├─ ")
                next_prefix = prefix + ("   " if is_last else "│  ")
                render_node(child, child_prefix if prefix else "")
                # Update for next iteration
                if prefix:
                    lines[-1] = lines[-1].replace(prefix, next_prefix, 1)

        for root in self.roots:
            render_node(root)

        return "\n".join(lines)


@dataclass
class HierarchySyncConfig:
    """Configuration for hierarchy synchronization."""

    enabled: bool = True

    # Sync behavior
    sync_parent_links: bool = True  # Sync parent/child links to tracker
    create_missing_parents: bool = False  # Create parent epics if missing
    validate_hierarchy: bool = True  # Validate hierarchy before sync

    # Level mapping (tracker-specific)
    level_field: str | None = None  # Custom field for level (e.g., customfield_10100)
    parent_field: str | None = None  # Custom field for parent link

    # Jira-specific
    use_portfolio_parent: bool = True  # Use Jira Portfolio parent link
    use_epic_link: bool = True  # Use epic link for story->epic


@dataclass
class HierarchySyncResult:
    """Result of hierarchy sync operation."""

    success: bool = True
    dry_run: bool = False

    # Counts
    nodes_processed: int = 0
    parent_links_created: int = 0
    parent_links_updated: int = 0
    levels_updated: int = 0
    errors: list[str] = field(default_factory=list)

    # Validation
    orphaned_nodes: list[str] = field(default_factory=list)
    invalid_parents: list[str] = field(default_factory=list)


class HierarchyExtractor:
    """Extract epic hierarchy from markdown content."""

    # Patterns for hierarchy in markdown
    PARENT_PATTERNS = [
        # | **Parent Epic** | INIT-123 |
        r"\|\s*\*\*Parent(?:\s*Epic)?\*\*\s*\|\s*([A-Z][A-Z0-9]*-\d+)\s*\|",
        # **Parent:** INIT-123
        r"\*\*Parent(?:\s*Epic)?:\*\*\s*([A-Z][A-Z0-9]*-\d+)",
        # Parent:: INIT-123 (Obsidian)
        r"Parent(?:\s*Epic)?::\s*([A-Z][A-Z0-9]*-\d+)",
    ]

    LEVEL_PATTERNS = [
        # | **Level** | Initiative |
        r"\|\s*\*\*Level\*\*\s*\|\s*(\w+)\s*\|",
        # **Level:** Initiative
        r"\*\*Level:\*\*\s*(\w+)",
        # Level:: Initiative
        r"Level::\s*(\w+)",
    ]

    CHILD_SECTION_PATTERN = r"#{2,4}\s*(?:Child(?:ren)?|Sub-?Epics?)\s*\n([\s\S]*?)(?=#{2,4}|\Z)"

    def __init__(self) -> None:
        """Initialize the extractor."""
        self.logger = logging.getLogger("HierarchyExtractor")
        import re

        self._re = re

    def extract_parent(self, content: str) -> str | None:
        """Extract parent epic key from content."""
        for pattern in self.PARENT_PATTERNS:
            match = self._re.search(pattern, content, self._re.IGNORECASE)
            if match:
                return match.group(1).upper()
        return None

    def extract_level(self, content: str) -> EpicLevel:
        """Extract epic level from content."""
        for pattern in self.LEVEL_PATTERNS:
            match = self._re.search(pattern, content, self._re.IGNORECASE)
            if match:
                return EpicLevel.from_string(match.group(1))
        return EpicLevel.EPIC

    def extract_children(self, content: str) -> list[str]:
        """Extract child epic keys from content."""
        import re

        children = []

        # Look for Children section
        section_match = re.search(self.CHILD_SECTION_PATTERN, content, re.IGNORECASE)
        if section_match:
            section_content = section_match.group(1)

            # Extract issue keys
            issue_pattern = r"([A-Z][A-Z0-9]*-\d+)"
            for match in re.finditer(issue_pattern, section_content):
                key = match.group(1)
                if key not in children:
                    children.append(key)

        return children


class HierarchySyncer:
    """
    Synchronize epic hierarchies with issue trackers.
    """

    def __init__(
        self,
        tracker: "IssueTrackerPort",
        config: HierarchySyncConfig | None = None,
    ):
        """
        Initialize the syncer.

        Args:
            tracker: Issue tracker adapter
            config: Sync configuration
        """
        self.tracker = tracker
        self.config = config or HierarchySyncConfig()
        self.logger = logging.getLogger("HierarchySyncer")

    def sync_hierarchy(
        self,
        hierarchy: EpicHierarchy,
        dry_run: bool = True,
    ) -> HierarchySyncResult:
        """
        Sync the epic hierarchy to the tracker.

        Args:
            hierarchy: Hierarchy to sync
            dry_run: If True, don't make changes

        Returns:
            HierarchySyncResult
        """
        result = HierarchySyncResult(dry_run=dry_run)

        if not self.config.enabled:
            return result

        # Validate hierarchy first
        if self.config.validate_hierarchy:
            validation = self._validate_hierarchy(hierarchy)
            result.orphaned_nodes = validation.get("orphaned", [])
            result.invalid_parents = validation.get("invalid", [])

        # Process each node
        for node in hierarchy.get_all_nodes():
            result.nodes_processed += 1

            if not node.external_key:
                self.logger.warning(f"Node {node.id} has no external key, skipping")
                continue

            # Sync parent link
            if self.config.sync_parent_links and node.parent_id:
                parent = hierarchy.find_node(node.parent_id)
                if parent and parent.external_key:
                    success = self._sync_parent_link(
                        node.external_key,
                        parent.external_key,
                        dry_run,
                    )
                    if success:
                        result.parent_links_created += 1
                    else:
                        result.errors.append(
                            f"Failed to link {node.external_key} to parent {parent.external_key}"
                        )

        result.success = len(result.errors) == 0
        return result

    def _validate_hierarchy(self, hierarchy: EpicHierarchy) -> dict[str, list[str]]:
        """Validate the hierarchy structure."""
        orphaned: list[str] = []
        invalid: list[str] = []

        for node in hierarchy.get_all_nodes():
            if node.parent_id:
                parent = hierarchy.find_node(node.parent_id)
                if not parent:
                    orphaned.append(node.id)

        return {"orphaned": orphaned, "invalid": invalid}

    def _sync_parent_link(
        self,
        child_key: str,
        parent_key: str,
        dry_run: bool,
    ) -> bool:
        """Sync a parent link in the tracker."""
        if dry_run:
            self.logger.info(f"[DRY-RUN] Would set parent of {child_key} to {parent_key}")
            return True

        try:
            # Use Portfolio parent if available
            if self.config.use_portfolio_parent and hasattr(self.tracker, "set_portfolio_parent"):
                return self.tracker.set_portfolio_parent(child_key, parent_key)

            # Fall back to custom field
            if self.config.parent_field:
                return self.tracker.update_issue(child_key, {self.config.parent_field: parent_key})

            # Fall back to issue link
            from spectryn.core.ports.issue_tracker import LinkType

            return self.tracker.create_link(
                child_key,
                parent_key,
                LinkType.IS_BLOCKED_BY,  # or CHILD_OF if supported
            )
        except Exception as e:
            self.logger.error(f"Failed to set parent link: {e}")
            return False


def build_hierarchy_from_epics(
    epics: list[dict[str, Any]],
) -> EpicHierarchy:
    """
    Build a hierarchy from a list of epic data.

    Args:
        epics: List of epic dictionaries with 'key', 'title', 'parent_key'

    Returns:
        EpicHierarchy
    """
    hierarchy = EpicHierarchy()
    extractor = HierarchyExtractor()

    # First pass: create all nodes
    nodes: dict[str, EpicNode] = {}
    for epic in epics:
        node = EpicNode(
            id=epic.get("key", ""),
            title=epic.get("title", ""),
            external_key=epic.get("key"),
            status=epic.get("status", ""),
            summary=epic.get("summary", ""),
        )

        # Extract level if available
        if epic.get("content"):
            node.level = extractor.extract_level(epic["content"])
            node.parent_id = extractor.extract_parent(epic["content"])

        if epic.get("parent_key"):
            node.parent_id = epic["parent_key"]

        nodes[node.id] = node

    # Second pass: build tree
    for node in nodes.values():
        if node.parent_id and node.parent_id in nodes:
            parent = nodes[node.parent_id]
            parent.add_child(node)
            hierarchy._node_index[node.id] = node
        else:
            # Root node
            hierarchy.add_root(node)

    return hierarchy


def extract_epic_hierarchy(content: str, epic_key: str) -> tuple[str | None, EpicLevel, list[str]]:
    """
    Convenience function to extract hierarchy info from markdown.

    Args:
        content: Markdown content
        epic_key: Current epic key

    Returns:
        Tuple of (parent_key, level, child_keys)
    """
    extractor = HierarchyExtractor()
    parent = extractor.extract_parent(content)
    level = extractor.extract_level(content)
    children = extractor.extract_children(content)
    return parent, level, children
