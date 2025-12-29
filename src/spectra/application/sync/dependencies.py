"""
Story Dependencies/Relationships - Parse and sync blocks/depends-on relationships.

This module provides comprehensive dependency synchronization:
- Parse dependency declarations from markdown
- Support multiple relationship types (blocks, depends on, relates to)
- Sync dependencies to/from issue trackers
- Detect circular dependencies
- Validate cross-project dependencies
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from spectra.core.domain.entities import UserStory
    from spectra.core.ports.issue_tracker import IssueTrackerPort

logger = logging.getLogger(__name__)


class DependencyType(Enum):
    """Types of dependencies between stories/issues."""

    BLOCKS = "blocks"  # This issue blocks another
    IS_BLOCKED_BY = "is blocked by"  # This issue is blocked by another
    DEPENDS_ON = "depends on"  # This issue depends on another
    IS_DEPENDENCY_OF = "is dependency of"  # This is a dependency of another
    RELATES_TO = "relates to"  # Related (no dependency)
    DUPLICATES = "duplicates"  # This duplicates another
    IS_DUPLICATED_BY = "is duplicated by"  # This is duplicated by another
    CLONES = "clones"  # This clones another
    IS_CLONED_BY = "is cloned by"  # This is cloned by another
    PARENT_OF = "parent of"  # Parent/child hierarchy
    CHILD_OF = "child of"  # Child of parent

    @classmethod
    def from_string(cls, value: str) -> "DependencyType":
        """Parse dependency type from string."""
        value_lower = value.lower().strip()

        mappings = {
            "blocks": cls.BLOCKS,
            "is blocked by": cls.IS_BLOCKED_BY,
            "blocked by": cls.IS_BLOCKED_BY,
            "depends on": cls.DEPENDS_ON,
            "depends-on": cls.DEPENDS_ON,
            "dependency of": cls.IS_DEPENDENCY_OF,
            "is dependency of": cls.IS_DEPENDENCY_OF,
            "relates to": cls.RELATES_TO,
            "related to": cls.RELATES_TO,
            "relates": cls.RELATES_TO,
            "duplicates": cls.DUPLICATES,
            "is duplicated by": cls.IS_DUPLICATED_BY,
            "duplicated by": cls.IS_DUPLICATED_BY,
            "clones": cls.CLONES,
            "is cloned by": cls.IS_CLONED_BY,
            "cloned by": cls.IS_CLONED_BY,
            "parent of": cls.PARENT_OF,
            "child of": cls.CHILD_OF,
        }

        return mappings.get(value_lower, cls.RELATES_TO)

    @property
    def inverse(self) -> "DependencyType":
        """Get the inverse relationship type."""
        inverses = {
            DependencyType.BLOCKS: DependencyType.IS_BLOCKED_BY,
            DependencyType.IS_BLOCKED_BY: DependencyType.BLOCKS,
            DependencyType.DEPENDS_ON: DependencyType.IS_DEPENDENCY_OF,
            DependencyType.IS_DEPENDENCY_OF: DependencyType.DEPENDS_ON,
            DependencyType.DUPLICATES: DependencyType.IS_DUPLICATED_BY,
            DependencyType.IS_DUPLICATED_BY: DependencyType.DUPLICATES,
            DependencyType.CLONES: DependencyType.IS_CLONED_BY,
            DependencyType.IS_CLONED_BY: DependencyType.CLONES,
            DependencyType.PARENT_OF: DependencyType.CHILD_OF,
            DependencyType.CHILD_OF: DependencyType.PARENT_OF,
            DependencyType.RELATES_TO: DependencyType.RELATES_TO,
        }
        return inverses.get(self, DependencyType.RELATES_TO)

    @property
    def is_blocking(self) -> bool:
        """Check if this is a blocking relationship."""
        return self in (DependencyType.BLOCKS, DependencyType.IS_BLOCKED_BY)

    @property
    def is_dependency(self) -> bool:
        """Check if this is a dependency relationship."""
        return self in (
            DependencyType.DEPENDS_ON,
            DependencyType.IS_DEPENDENCY_OF,
            DependencyType.BLOCKS,
            DependencyType.IS_BLOCKED_BY,
        )


@dataclass
class Dependency:
    """
    Represents a dependency between two stories/issues.
    """

    source_id: str  # Local story ID
    target_id: str  # Target issue ID (local or external key)
    dependency_type: DependencyType

    # Optional metadata
    source_key: str | None = None  # External key if synced
    target_key: str | None = None  # Resolved external key
    description: str = ""

    # Sync status
    synced: bool = False
    synced_at: datetime | None = None
    error: str | None = None

    def __str__(self) -> str:
        source = self.source_key or self.source_id
        target = self.target_key or self.target_id
        return f"{source} {self.dependency_type.value} {target}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "dependency_type": self.dependency_type.value,
            "source_key": self.source_key,
            "target_key": self.target_key,
            "description": self.description,
            "synced": self.synced,
            "synced_at": self.synced_at.isoformat() if self.synced_at else None,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Dependency":
        """Create from dictionary."""
        synced_at = None
        if data.get("synced_at"):
            synced_at = datetime.fromisoformat(data["synced_at"])

        return cls(
            source_id=data.get("source_id", ""),
            target_id=data.get("target_id", ""),
            dependency_type=DependencyType.from_string(data.get("dependency_type", "")),
            source_key=data.get("source_key"),
            target_key=data.get("target_key"),
            description=data.get("description", ""),
            synced=data.get("synced", False),
            synced_at=synced_at,
            error=data.get("error"),
        )


@dataclass
class DependencyGraph:
    """
    Graph of dependencies between stories.

    Supports cycle detection and topological sorting.
    """

    dependencies: list[Dependency] = field(default_factory=list)

    def add(self, dependency: Dependency) -> None:
        """Add a dependency to the graph."""
        self.dependencies.append(dependency)

    def get_blocking(self, story_id: str) -> list[Dependency]:
        """Get dependencies that block a story."""
        return [
            d
            for d in self.dependencies
            if d.target_id == story_id and d.dependency_type == DependencyType.BLOCKS
        ]

    def get_blocked_by(self, story_id: str) -> list[Dependency]:
        """Get stories that this story is blocked by."""
        return [
            d
            for d in self.dependencies
            if d.source_id == story_id
            and d.dependency_type in (DependencyType.IS_BLOCKED_BY, DependencyType.DEPENDS_ON)
        ]

    def get_all_for_story(self, story_id: str) -> list[Dependency]:
        """Get all dependencies involving a story."""
        return [d for d in self.dependencies if story_id in (d.source_id, d.target_id)]

    def detect_cycles(self) -> list[list[str]]:
        """
        Detect circular dependencies.

        Returns:
            List of cycles (each cycle is a list of story IDs)
        """
        # Build adjacency list
        graph: dict[str, set[str]] = {}
        for dep in self.dependencies:
            if dep.dependency_type.is_dependency:
                if dep.source_id not in graph:
                    graph[dep.source_id] = set()
                graph[dep.source_id].add(dep.target_id)

        cycles = []
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def dfs(node: str, path: list[str]) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor, path)
                elif neighbor in rec_stack:
                    # Found a cycle
                    cycle_start = path.index(neighbor)
                    cycle = [*path[cycle_start:], neighbor]
                    cycles.append(cycle)

            path.pop()
            rec_stack.remove(node)

        for node in graph:
            if node not in visited:
                dfs(node, [])

        return cycles

    def topological_sort(self) -> list[str]:
        """
        Sort stories in dependency order.

        Returns stories in an order where dependencies come before dependents.

        Returns:
            List of story IDs in dependency order
        """
        # Build adjacency list (reverse direction for topo sort)
        in_degree: dict[str, int] = {}
        graph: dict[str, list[str]] = {}

        # Collect all nodes
        all_nodes = set()
        for dep in self.dependencies:
            all_nodes.add(dep.source_id)
            all_nodes.add(dep.target_id)

        for node in all_nodes:
            in_degree[node] = 0
            graph[node] = []

        # Build graph
        for dep in self.dependencies:
            if dep.dependency_type.is_dependency:
                # source depends on target, so target -> source
                graph[dep.target_id].append(dep.source_id)
                in_degree[dep.source_id] += 1

        # Kahn's algorithm
        result = []
        queue = [node for node in all_nodes if in_degree[node] == 0]

        while queue:
            node = queue.pop(0)
            result.append(node)

            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return result


class DependencyExtractor:
    """Extract dependencies from markdown content."""

    # Issue key pattern (e.g., PROJ-123)
    ISSUE_KEY_PATTERN = r"[A-Z][A-Z0-9]*-\d+"

    # Dependency patterns in markdown
    DEPENDENCY_PATTERNS = [
        # Table row: | blocks | PROJ-123 |
        r"\|\s*(blocks|blocked by|depends on|relates to|duplicates)\s*\|\s*("
        + ISSUE_KEY_PATTERN
        + r")\s*\|",
        # Bold label: **Blocks:** PROJ-123
        r"\*\*(Blocks|Blocked by|Depends on|Depends-on|Related to|Relates to|Duplicates):"
        r"?\*\*\s*(" + ISSUE_KEY_PATTERN + r"(?:\s*,\s*" + ISSUE_KEY_PATTERN + r")*)",
        # Bullet list: - blocks: PROJ-123
        r"[-*]\s*(blocks|blocked by|depends on|relates to|duplicates)[:\s]+("
        + ISSUE_KEY_PATTERN
        + r")",
        # Obsidian dataview: Blocks:: PROJ-123
        r"(Blocks|Blocked by|Depends on|Depends-on|Related to|Duplicates)::\s*("
        + ISSUE_KEY_PATTERN
        + r"(?:\s*,\s*"
        + ISSUE_KEY_PATTERN
        + r")*)",
    ]

    # Section header patterns
    SECTION_PATTERNS = [
        r"#{2,4}\s*(?:Dependencies|Relationships|Links|Blockers)\s*\n([\s\S]*?)(?=#{2,4}|\Z)",
    ]

    def __init__(self):
        """Initialize the extractor."""
        self.logger = logging.getLogger("DependencyExtractor")

    def extract_from_content(self, content: str, story_id: str) -> list[Dependency]:
        """
        Extract dependencies from markdown content.

        Args:
            content: Markdown content
            story_id: Source story ID

        Returns:
            List of dependencies
        """
        dependencies = []
        seen: set[tuple[str, str]] = set()  # (type, target) to avoid duplicates

        # Extract from dependency sections
        for section_pattern in self.SECTION_PATTERNS:
            for section_match in re.finditer(section_pattern, content, re.IGNORECASE):
                section_content = section_match.group(1)
                deps = self._extract_from_section(section_content, story_id)
                for dep in deps:
                    key = (dep.dependency_type.value, dep.target_id)
                    if key not in seen:
                        dependencies.append(dep)
                        seen.add(key)

        # Extract inline dependencies
        for pattern in self.DEPENDENCY_PATTERNS:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                dep_type_str = match.group(1)
                targets_str = match.group(2)

                # Handle multiple targets (comma-separated)
                targets = re.findall(self.ISSUE_KEY_PATTERN, targets_str)

                for target in targets:
                    dep_type = DependencyType.from_string(dep_type_str)
                    key = (dep_type.value, target)
                    if key not in seen:
                        dependencies.append(
                            Dependency(
                                source_id=story_id,
                                target_id=target,
                                dependency_type=dep_type,
                            )
                        )
                        seen.add(key)

        return dependencies

    def _extract_from_section(self, section_content: str, story_id: str) -> list[Dependency]:
        """Extract dependencies from a section's content."""
        dependencies = []

        # Table rows
        table_pattern = r"\|\s*([^|]+)\s*\|\s*(" + self.ISSUE_KEY_PATTERN + r")\s*\|"
        for match in re.finditer(table_pattern, section_content, re.IGNORECASE):
            dep_type_str = match.group(1).strip().lower()
            target = match.group(2).strip()

            # Skip header rows
            if dep_type_str.startswith("-") or dep_type_str == "type":
                continue

            dep_type = DependencyType.from_string(dep_type_str)
            dependencies.append(
                Dependency(
                    source_id=story_id,
                    target_id=target,
                    dependency_type=dep_type,
                )
            )

        # Bullet lists
        bullet_pattern = r"[-*]\s*(?:([^:]+):\s*)?(" + self.ISSUE_KEY_PATTERN + r")"
        for match in re.finditer(bullet_pattern, section_content):
            dep_type_str = match.group(1) or "relates to"
            target = match.group(2).strip()

            dep_type = DependencyType.from_string(dep_type_str.strip())
            dependencies.append(
                Dependency(
                    source_id=story_id,
                    target_id=target,
                    dependency_type=dep_type,
                )
            )

        return dependencies


@dataclass
class DependencySyncConfig:
    """Configuration for dependency synchronization."""

    enabled: bool = True
    sync_blocks: bool = True
    sync_depends_on: bool = True
    sync_relates: bool = True
    sync_duplicates: bool = True

    # Sync direction
    push_to_tracker: bool = True
    pull_from_tracker: bool = False

    # Validation
    validate_targets: bool = True  # Verify target issues exist
    detect_cycles: bool = True  # Check for circular dependencies
    fail_on_cycle: bool = False  # Fail if cycle detected

    # Cross-project
    allow_cross_project: bool = True
    allowed_projects: list[str] = field(default_factory=list)  # Empty = all


@dataclass
class DependencySyncResult:
    """Result of dependency sync operation."""

    success: bool = True
    dry_run: bool = False

    # Counts
    stories_processed: int = 0
    dependencies_created: int = 0
    dependencies_deleted: int = 0
    dependencies_unchanged: int = 0
    dependencies_failed: int = 0

    # Validation
    cycles_detected: list[list[str]] = field(default_factory=list)
    invalid_targets: list[str] = field(default_factory=list)

    # Errors
    errors: list[str] = field(default_factory=list)

    @property
    def has_cycles(self) -> bool:
        return len(self.cycles_detected) > 0


class DependencySyncer:
    """
    Synchronize dependencies between markdown and issue trackers.
    """

    def __init__(
        self,
        tracker: "IssueTrackerPort",
        config: DependencySyncConfig | None = None,
    ):
        """
        Initialize the syncer.

        Args:
            tracker: Issue tracker adapter
            config: Sync configuration
        """
        self.tracker = tracker
        self.config = config or DependencySyncConfig()
        self.logger = logging.getLogger("DependencySyncer")

    def sync_story_dependencies(
        self,
        story_id: str,
        issue_key: str,
        dependencies: list[Dependency],
        dry_run: bool = True,
    ) -> DependencySyncResult:
        """
        Sync dependencies for a single story.

        Args:
            story_id: Local story ID
            issue_key: Remote issue key
            dependencies: Dependencies to sync
            dry_run: If True, don't make changes

        Returns:
            DependencySyncResult
        """

        result = DependencySyncResult(dry_run=dry_run)
        result.stories_processed = 1

        if not self.config.enabled:
            return result

        # Filter dependencies by type
        deps_to_sync = [d for d in dependencies if self._should_sync_type(d.dependency_type)]

        # Validate targets if configured
        if self.config.validate_targets:
            for dep in deps_to_sync:
                if not self._validate_target(dep.target_id):
                    result.invalid_targets.append(dep.target_id)
                    dep.error = f"Target issue {dep.target_id} not found"

        # Get existing links from tracker
        existing_links = self.tracker.get_issue_links(issue_key)
        existing_set = {(link.link_type.value, link.target_key) for link in existing_links}

        # Sync each dependency
        for dep in deps_to_sync:
            if dep.error:
                result.dependencies_failed += 1
                continue

            # Map dependency type to link type
            link_type = self._to_link_type(dep.dependency_type)
            key = (link_type.value, dep.target_id)

            if key in existing_set:
                result.dependencies_unchanged += 1
                dep.synced = True
                continue

            # Create the link
            if dry_run:
                self.logger.info(
                    f"[DRY-RUN] Would create link: {issue_key} "
                    f"{dep.dependency_type.value} {dep.target_id}"
                )
                result.dependencies_created += 1
            else:
                success = self.tracker.create_link(
                    source_key=issue_key,
                    target_key=dep.target_id,
                    link_type=link_type,
                )
                if success:
                    result.dependencies_created += 1
                    dep.synced = True
                    dep.synced_at = datetime.now()
                else:
                    result.dependencies_failed += 1
                    dep.error = "Failed to create link"
                    result.errors.append(f"Failed to create link: {issue_key} -> {dep.target_id}")

        result.success = result.dependencies_failed == 0
        return result

    def validate_graph(self, stories: list["UserStory"]) -> DependencySyncResult:
        """
        Validate the dependency graph for cycles and issues.

        Args:
            stories: Stories to validate

        Returns:
            DependencySyncResult with validation results
        """
        result = DependencySyncResult()

        # Build graph
        graph = DependencyGraph()
        extractor = DependencyExtractor()

        for story in stories:
            # Extract dependencies from story content
            if story.description:
                deps = extractor.extract_from_content(
                    story.description.to_markdown(), str(story.id)
                )
                for dep in deps:
                    graph.add(dep)

            # Also add from story.links
            for link_type, target in story.links:
                dep_type = DependencyType.from_string(link_type)
                graph.add(
                    Dependency(
                        source_id=str(story.id),
                        target_id=target,
                        dependency_type=dep_type,
                    )
                )

        # Detect cycles
        if self.config.detect_cycles:
            cycles = graph.detect_cycles()
            result.cycles_detected = cycles
            if cycles and self.config.fail_on_cycle:
                result.success = False
                for cycle in cycles:
                    result.errors.append(f"Circular dependency detected: {' -> '.join(cycle)}")

        return result

    def _should_sync_type(self, dep_type: DependencyType) -> bool:
        """Check if a dependency type should be synced."""
        if dep_type in (DependencyType.BLOCKS, DependencyType.IS_BLOCKED_BY):
            return self.config.sync_blocks
        if dep_type in (DependencyType.DEPENDS_ON, DependencyType.IS_DEPENDENCY_OF):
            return self.config.sync_depends_on
        if dep_type == DependencyType.RELATES_TO:
            return self.config.sync_relates
        if dep_type in (DependencyType.DUPLICATES, DependencyType.IS_DUPLICATED_BY):
            return self.config.sync_duplicates
        return True

    def _validate_target(self, target_key: str) -> bool:
        """Validate that a target issue exists."""
        try:
            self.tracker.get_issue(target_key)
            return True
        except Exception:
            return False

    def _to_link_type(self, dep_type: DependencyType) -> "LinkType":
        """Convert DependencyType to LinkType."""
        from spectra.core.ports.issue_tracker import LinkType

        mapping = {
            DependencyType.BLOCKS: LinkType.BLOCKS,
            DependencyType.IS_BLOCKED_BY: LinkType.IS_BLOCKED_BY,
            DependencyType.DEPENDS_ON: LinkType.DEPENDS_ON,
            DependencyType.IS_DEPENDENCY_OF: LinkType.IS_DEPENDENCY_OF,
            DependencyType.RELATES_TO: LinkType.RELATES_TO,
            DependencyType.DUPLICATES: LinkType.DUPLICATES,
            DependencyType.IS_DUPLICATED_BY: LinkType.IS_DUPLICATED_BY,
            DependencyType.CLONES: LinkType.CLONES,
            DependencyType.IS_CLONED_BY: LinkType.IS_CLONED_BY,
        }
        return mapping.get(dep_type, LinkType.RELATES_TO)


def extract_dependencies(content: str, story_id: str) -> list[Dependency]:
    """
    Convenience function to extract dependencies from markdown.

    Args:
        content: Markdown content
        story_id: Story ID

    Returns:
        List of dependencies
    """
    extractor = DependencyExtractor()
    return extractor.extract_from_content(content, story_id)


def build_dependency_graph(stories: list["UserStory"]) -> DependencyGraph:
    """
    Build a dependency graph from stories.

    Args:
        stories: Stories with dependencies

    Returns:
        DependencyGraph
    """
    graph = DependencyGraph()
    extractor = DependencyExtractor()

    for story in stories:
        if story.description:
            deps = extractor.extract_from_content(story.description.to_markdown(), str(story.id))
            for dep in deps:
                graph.add(dep)

        for link_type, target in story.links:
            dep_type = DependencyType.from_string(link_type)
            graph.add(
                Dependency(
                    source_id=str(story.id),
                    target_id=target,
                    dependency_type=dep_type,
                )
            )

    return graph
