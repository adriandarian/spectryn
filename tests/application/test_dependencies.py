"""Tests for story dependencies/relationships sync functionality."""

import textwrap

import pytest

from spectra.application.sync.dependencies import (
    Dependency,
    DependencyExtractor,
    DependencyGraph,
    DependencySyncConfig,
    DependencySyncResult,
    DependencyType,
    build_dependency_graph,
    extract_dependencies,
)


class TestDependencyType:
    """Tests for DependencyType enum."""

    def test_all_types_exist(self):
        """Test all dependency types are defined."""
        assert DependencyType.BLOCKS.value == "blocks"
        assert DependencyType.IS_BLOCKED_BY.value == "is blocked by"
        assert DependencyType.DEPENDS_ON.value == "depends on"
        assert DependencyType.RELATES_TO.value == "relates to"
        assert DependencyType.DUPLICATES.value == "duplicates"

    def test_from_string_blocks(self):
        """Test parsing 'blocks' type."""
        assert DependencyType.from_string("blocks") == DependencyType.BLOCKS
        assert DependencyType.from_string("BLOCKS") == DependencyType.BLOCKS

    def test_from_string_blocked_by(self):
        """Test parsing 'blocked by' variants."""
        assert DependencyType.from_string("is blocked by") == DependencyType.IS_BLOCKED_BY
        assert DependencyType.from_string("blocked by") == DependencyType.IS_BLOCKED_BY

    def test_from_string_depends_on(self):
        """Test parsing 'depends on' variants."""
        assert DependencyType.from_string("depends on") == DependencyType.DEPENDS_ON
        assert DependencyType.from_string("depends-on") == DependencyType.DEPENDS_ON

    def test_from_string_unknown_defaults_to_relates(self):
        """Test unknown types default to relates_to."""
        assert DependencyType.from_string("unknown") == DependencyType.RELATES_TO

    def test_inverse(self):
        """Test inverse relationship lookup."""
        assert DependencyType.BLOCKS.inverse == DependencyType.IS_BLOCKED_BY
        assert DependencyType.IS_BLOCKED_BY.inverse == DependencyType.BLOCKS
        assert DependencyType.DEPENDS_ON.inverse == DependencyType.IS_DEPENDENCY_OF
        assert DependencyType.RELATES_TO.inverse == DependencyType.RELATES_TO

    def test_is_blocking(self):
        """Test blocking relationship check."""
        assert DependencyType.BLOCKS.is_blocking is True
        assert DependencyType.IS_BLOCKED_BY.is_blocking is True
        assert DependencyType.RELATES_TO.is_blocking is False

    def test_is_dependency(self):
        """Test dependency relationship check."""
        assert DependencyType.DEPENDS_ON.is_dependency is True
        assert DependencyType.BLOCKS.is_dependency is True
        assert DependencyType.RELATES_TO.is_dependency is False


class TestDependency:
    """Tests for Dependency class."""

    def test_create_basic(self):
        """Test creating a basic dependency."""
        dep = Dependency(
            source_id="US-001",
            target_id="PROJ-123",
            dependency_type=DependencyType.BLOCKS,
        )
        assert dep.source_id == "US-001"
        assert dep.target_id == "PROJ-123"
        assert dep.dependency_type == DependencyType.BLOCKS

    def test_str_representation(self):
        """Test string representation."""
        dep = Dependency(
            source_id="US-001",
            target_id="PROJ-123",
            dependency_type=DependencyType.BLOCKS,
        )
        assert "blocks" in str(dep)
        assert "PROJ-123" in str(dep)

    def test_to_dict_and_back(self):
        """Test serialization roundtrip."""
        dep = Dependency(
            source_id="US-001",
            target_id="PROJ-123",
            dependency_type=DependencyType.DEPENDS_ON,
            source_key="MAIN-001",
            description="Needs this first",
            synced=True,
        )
        data = dep.to_dict()
        restored = Dependency.from_dict(data)

        assert restored.source_id == dep.source_id
        assert restored.target_id == dep.target_id
        assert restored.dependency_type == dep.dependency_type
        assert restored.source_key == dep.source_key
        assert restored.synced == dep.synced


class TestDependencyGraph:
    """Tests for DependencyGraph class."""

    def test_add_dependency(self):
        """Test adding dependencies."""
        graph = DependencyGraph()
        dep = Dependency(
            source_id="A",
            target_id="B",
            dependency_type=DependencyType.BLOCKS,
        )
        graph.add(dep)

        assert len(graph.dependencies) == 1

    def test_get_blocking(self):
        """Test getting blocking dependencies."""
        graph = DependencyGraph()
        graph.add(Dependency("A", "B", DependencyType.BLOCKS))  # A blocks B
        graph.add(Dependency("C", "B", DependencyType.BLOCKS))  # C blocks B

        blocking = graph.get_blocking("B")
        assert len(blocking) == 2

    def test_get_blocked_by(self):
        """Test getting blocked-by dependencies."""
        graph = DependencyGraph()
        graph.add(Dependency("A", "B", DependencyType.IS_BLOCKED_BY))  # A is blocked by B
        graph.add(Dependency("A", "C", DependencyType.DEPENDS_ON))  # A depends on C

        blocked = graph.get_blocked_by("A")
        assert len(blocked) == 2

    def test_get_all_for_story(self):
        """Test getting all dependencies for a story."""
        graph = DependencyGraph()
        graph.add(Dependency("A", "B", DependencyType.BLOCKS))
        graph.add(Dependency("C", "A", DependencyType.RELATES_TO))
        graph.add(Dependency("D", "E", DependencyType.BLOCKS))

        deps = graph.get_all_for_story("A")
        assert len(deps) == 2

    def test_detect_cycles_simple(self):
        """Test detecting a simple cycle."""
        graph = DependencyGraph()
        graph.add(Dependency("A", "B", DependencyType.BLOCKS))  # A blocks B
        graph.add(Dependency("B", "C", DependencyType.BLOCKS))  # B blocks C
        graph.add(Dependency("C", "A", DependencyType.BLOCKS))  # C blocks A (cycle!)

        cycles = graph.detect_cycles()
        assert len(cycles) > 0

    def test_detect_cycles_none(self):
        """Test no cycles in valid graph."""
        graph = DependencyGraph()
        graph.add(Dependency("A", "B", DependencyType.BLOCKS))
        graph.add(Dependency("B", "C", DependencyType.BLOCKS))
        graph.add(Dependency("A", "C", DependencyType.BLOCKS))

        cycles = graph.detect_cycles()
        assert len(cycles) == 0

    def test_topological_sort(self):
        """Test topological sorting."""
        graph = DependencyGraph()
        graph.add(Dependency("A", "B", DependencyType.DEPENDS_ON))  # A depends on B
        graph.add(Dependency("B", "C", DependencyType.DEPENDS_ON))  # B depends on C

        order = graph.topological_sort()

        # C should come before B, B before A
        assert order.index("C") < order.index("B")
        assert order.index("B") < order.index("A")


class TestDependencyExtractor:
    """Tests for DependencyExtractor."""

    def test_extract_from_table(self):
        """Test extracting from markdown table."""
        content = textwrap.dedent("""
            ### Dependencies
            | Type | Target |
            |------|--------|
            | blocks | PROJ-123 |
            | depends on | OTHER-456 |
        """)
        deps = extract_dependencies(content, "US-001")
        assert len(deps) >= 2

    def test_extract_bold_label(self):
        """Test extracting from bold label format."""
        content = "**Blocks:** PROJ-123, PROJ-456"
        deps = extract_dependencies(content, "US-001")

        assert len(deps) == 2
        assert all(d.dependency_type == DependencyType.BLOCKS for d in deps)

    def test_extract_depends_on(self):
        """Test extracting depends-on relationship."""
        content = "**Depends on:** OTHER-789"
        deps = extract_dependencies(content, "US-001")

        assert len(deps) == 1
        assert deps[0].dependency_type == DependencyType.DEPENDS_ON
        assert deps[0].target_id == "OTHER-789"

    def test_extract_bullet_list(self):
        """Test extracting from bullet list."""
        content = textwrap.dedent("""
            #### Links
            - blocks: PROJ-123
            - relates to: PROJ-456
        """)
        deps = extract_dependencies(content, "US-001")
        assert len(deps) >= 2

    def test_extract_obsidian_dataview(self):
        """Test extracting Obsidian dataview format."""
        content = "Blocks:: PROJ-123, PROJ-456"
        deps = extract_dependencies(content, "US-001")

        assert len(deps) == 2

    def test_no_dependencies(self):
        """Test content without dependencies."""
        content = "### US-001: Simple Story\n\nJust a description."
        deps = extract_dependencies(content, "US-001")
        assert len(deps) == 0

    def test_no_duplicates(self):
        """Test that duplicates are filtered out."""
        content = textwrap.dedent("""
            **Blocks:** PROJ-123
            - blocks: PROJ-123
        """)
        deps = extract_dependencies(content, "US-001")

        # Should only have one PROJ-123 blocks dependency
        blocks_123 = [d for d in deps if d.target_id == "PROJ-123"]
        assert len(blocks_123) == 1

    def test_multiple_formats(self):
        """Test extracting from multiple formats."""
        content = textwrap.dedent("""
            ### US-001: Story

            **Blocks:** PROJ-123
            **Depends on:** OTHER-456

            #### Dependencies
            | Type | Target |
            | relates to | THIRD-789 |
        """)
        deps = extract_dependencies(content, "US-001")
        assert len(deps) >= 3


class TestDependencySyncConfig:
    """Tests for DependencySyncConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = DependencySyncConfig()
        assert config.enabled is True
        assert config.sync_blocks is True
        assert config.sync_depends_on is True
        assert config.detect_cycles is True
        assert config.allow_cross_project is True

    def test_custom_config(self):
        """Test custom configuration values."""
        config = DependencySyncConfig(
            sync_relates=False,
            fail_on_cycle=True,
        )
        assert config.sync_relates is False
        assert config.fail_on_cycle is True


class TestDependencySyncResult:
    """Tests for DependencySyncResult."""

    def test_success_by_default(self):
        """Test success is True by default."""
        result = DependencySyncResult()
        assert result.success is True

    def test_has_cycles(self):
        """Test has_cycles property."""
        result = DependencySyncResult()
        assert result.has_cycles is False

        result.cycles_detected = [["A", "B", "C", "A"]]
        assert result.has_cycles is True
