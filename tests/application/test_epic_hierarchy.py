"""Tests for epic hierarchy functionality."""

import textwrap

import pytest

from spectryn.application.sync.epic_hierarchy import (
    EpicHierarchy,
    EpicLevel,
    EpicNode,
    HierarchyExtractor,
    HierarchySyncConfig,
    HierarchySyncResult,
    build_hierarchy_from_epics,
    extract_epic_hierarchy,
)


class TestEpicLevel:
    """Tests for EpicLevel enum."""

    def test_all_levels_exist(self):
        """Test all hierarchy levels are defined."""
        assert EpicLevel.PORTFOLIO.value == "portfolio"
        assert EpicLevel.INITIATIVE.value == "initiative"
        assert EpicLevel.THEME.value == "theme"
        assert EpicLevel.EPIC.value == "epic"
        assert EpicLevel.FEATURE.value == "feature"

    def test_from_string(self):
        """Test parsing level from string."""
        assert EpicLevel.from_string("portfolio") == EpicLevel.PORTFOLIO
        assert EpicLevel.from_string("INITIATIVE") == EpicLevel.INITIATIVE
        assert EpicLevel.from_string("unknown") == EpicLevel.EPIC

    def test_depth_ordering(self):
        """Test that depth reflects hierarchy."""
        assert EpicLevel.PORTFOLIO.depth < EpicLevel.INITIATIVE.depth
        assert EpicLevel.INITIATIVE.depth < EpicLevel.EPIC.depth
        assert EpicLevel.EPIC.depth < EpicLevel.FEATURE.depth


class TestEpicNode:
    """Tests for EpicNode class."""

    def test_create_basic(self):
        """Test creating a basic node."""
        node = EpicNode(
            id="EPIC-123",
            title="Test Epic",
            level=EpicLevel.EPIC,
        )
        assert node.id == "EPIC-123"
        assert node.title == "Test Epic"
        assert node.level == EpicLevel.EPIC

    def test_add_child(self):
        """Test adding a child node."""
        parent = EpicNode(id="INIT-1", title="Initiative", level=EpicLevel.INITIATIVE)
        child = EpicNode(id="EPIC-1", title="Epic", level=EpicLevel.EPIC)

        parent.add_child(child)

        assert len(parent.children) == 1
        assert child.parent_id == parent.id

    def test_find_child(self):
        """Test finding direct child."""
        parent = EpicNode(id="INIT-1", title="Initiative")
        child1 = EpicNode(id="EPIC-1", title="Epic 1")
        child2 = EpicNode(id="EPIC-2", title="Epic 2")

        parent.add_child(child1)
        parent.add_child(child2)

        found = parent.find_child("EPIC-2")
        assert found is not None
        assert found.id == "EPIC-2"

    def test_find_descendant_recursive(self):
        """Test finding descendant recursively."""
        root = EpicNode(id="PORT-1", title="Portfolio")
        init = EpicNode(id="INIT-1", title="Initiative")
        epic = EpicNode(id="EPIC-1", title="Epic")

        root.add_child(init)
        init.add_child(epic)

        found = root.find_descendant("EPIC-1")
        assert found is not None
        assert found.id == "EPIC-1"

    def test_get_all_descendants(self):
        """Test getting all descendants."""
        root = EpicNode(id="ROOT", title="Root")
        child1 = EpicNode(id="CHILD-1", title="Child 1")
        child2 = EpicNode(id="CHILD-2", title="Child 2")
        grandchild = EpicNode(id="GRAND-1", title="Grandchild")

        root.add_child(child1)
        root.add_child(child2)
        child1.add_child(grandchild)

        descendants = root.get_all_descendants()
        assert len(descendants) == 3

    def test_aggregate_metrics(self):
        """Test aggregating metrics from children."""
        root = EpicNode(id="ROOT", title="Root")
        child1 = EpicNode(id="CHILD-1", title="Child 1", story_count=5, total_points=20)
        child2 = EpicNode(id="CHILD-2", title="Child 2", story_count=3, total_points=10)

        root.add_child(child1)
        root.add_child(child2)
        root.aggregate_metrics()

        assert root.story_count == 8
        assert root.total_points == 30

    def test_to_dict_and_back(self):
        """Test serialization roundtrip."""
        node = EpicNode(
            id="EPIC-1",
            title="Test Epic",
            level=EpicLevel.INITIATIVE,
            status="In Progress",
            story_count=10,
        )
        child = EpicNode(id="EPIC-2", title="Child")
        node.add_child(child)

        data = node.to_dict()
        restored = EpicNode.from_dict(data)

        assert restored.id == node.id
        assert restored.level == node.level
        assert len(restored.children) == 1


class TestEpicHierarchy:
    """Tests for EpicHierarchy class."""

    def test_add_root(self):
        """Test adding root nodes."""
        hierarchy = EpicHierarchy()
        root1 = EpicNode(id="PORT-1", title="Portfolio 1")
        root2 = EpicNode(id="PORT-2", title="Portfolio 2")

        hierarchy.add_root(root1)
        hierarchy.add_root(root2)

        assert len(hierarchy.roots) == 2

    def test_find_node(self):
        """Test finding any node by ID."""
        hierarchy = EpicHierarchy()
        root = EpicNode(id="ROOT", title="Root")
        child = EpicNode(id="CHILD", title="Child")
        root.add_child(child)
        hierarchy.add_root(root)

        found = hierarchy.find_node("CHILD")
        assert found is not None
        assert found.id == "CHILD"

    def test_add_node_to_parent(self):
        """Test adding node to existing parent."""
        hierarchy = EpicHierarchy()
        root = EpicNode(id="ROOT", title="Root")
        hierarchy.add_root(root)

        child = EpicNode(id="CHILD", title="Child")
        success = hierarchy.add_node(child, parent_id="ROOT")

        assert success is True
        assert len(root.children) == 1

    def test_get_ancestors(self):
        """Test getting ancestors of a node."""
        hierarchy = EpicHierarchy()
        root = EpicNode(id="ROOT", title="Root")
        child = EpicNode(id="CHILD", title="Child")
        grandchild = EpicNode(id="GRAND", title="Grandchild")

        root.add_child(child)
        child.add_child(grandchild)
        hierarchy.add_root(root)

        ancestors = hierarchy.get_ancestors("GRAND")
        assert len(ancestors) == 2
        assert ancestors[0].id == "CHILD"
        assert ancestors[1].id == "ROOT"

    def test_get_depth(self):
        """Test getting node depth."""
        hierarchy = EpicHierarchy()
        root = EpicNode(id="ROOT", title="Root")
        child = EpicNode(id="CHILD", title="Child")
        root.add_child(child)
        hierarchy.add_root(root)

        assert hierarchy.get_depth("ROOT") == 0
        assert hierarchy.get_depth("CHILD") == 1

    def test_get_all_nodes(self):
        """Test getting all nodes."""
        hierarchy = EpicHierarchy()
        root = EpicNode(id="ROOT", title="Root")
        child1 = EpicNode(id="C1", title="Child 1")
        child2 = EpicNode(id="C2", title="Child 2")

        root.add_child(child1)
        root.add_child(child2)
        hierarchy.add_root(root)

        all_nodes = hierarchy.get_all_nodes()
        assert len(all_nodes) == 3

    def test_get_nodes_at_level(self):
        """Test getting nodes at specific level."""
        hierarchy = EpicHierarchy()
        root = EpicNode(id="ROOT", title="Root", level=EpicLevel.PORTFOLIO)
        child = EpicNode(id="CHILD", title="Child", level=EpicLevel.INITIATIVE)

        root.add_child(child)
        hierarchy.add_root(root)

        initiatives = hierarchy.get_nodes_at_level(EpicLevel.INITIATIVE)
        assert len(initiatives) == 1
        assert initiatives[0].id == "CHILD"

    def test_to_tree_string(self):
        """Test tree string generation."""
        hierarchy = EpicHierarchy()
        root = EpicNode(id="ROOT", title="Root")
        child = EpicNode(id="CHILD", title="Child")
        root.add_child(child)
        hierarchy.add_root(root)

        tree_str = hierarchy.to_tree_string()
        assert "ROOT" in tree_str
        assert "CHILD" in tree_str

    def test_to_dict_and_back(self):
        """Test serialization roundtrip."""
        hierarchy = EpicHierarchy()
        root = EpicNode(id="ROOT", title="Root")
        child = EpicNode(id="CHILD", title="Child")
        root.add_child(child)
        hierarchy.add_root(root)

        data = hierarchy.to_dict()
        restored = EpicHierarchy.from_dict(data)

        assert len(restored.roots) == 1
        assert len(restored.roots[0].children) == 1


class TestHierarchyExtractor:
    """Tests for HierarchyExtractor."""

    def test_extract_parent_from_table(self):
        """Test extracting parent from markdown table."""
        content = textwrap.dedent("""
            ### EPIC-123: Test Epic

            | **Property** | **Value** |
            |--------------|-----------|
            | **Parent Epic** | INIT-100 |
            | **Status** | In Progress |
        """)
        parent, _level, _children = extract_epic_hierarchy(content, "EPIC-123")
        assert parent == "INIT-100"

    def test_extract_parent_inline(self):
        """Test extracting parent from inline format."""
        content = "**Parent:** INIT-200"
        parent, _level, _children = extract_epic_hierarchy(content, "EPIC-123")
        assert parent == "INIT-200"

    def test_extract_parent_obsidian(self):
        """Test extracting parent from Obsidian format."""
        content = "Parent:: INIT-300"
        parent, _level, _children = extract_epic_hierarchy(content, "EPIC-123")
        assert parent == "INIT-300"

    def test_extract_level(self):
        """Test extracting level from content."""
        content = "| **Level** | Initiative |"
        _parent, level, _children = extract_epic_hierarchy(content, "EPIC-123")
        assert level == EpicLevel.INITIATIVE

    def test_extract_children_section(self):
        """Test extracting children from section."""
        content = textwrap.dedent("""
            ### INIT-100: Initiative

            #### Children
            - EPIC-1: First Epic
            - EPIC-2: Second Epic
        """)
        _parent, _level, children = extract_epic_hierarchy(content, "INIT-100")
        assert len(children) == 2
        assert "EPIC-1" in children
        assert "EPIC-2" in children

    def test_no_hierarchy(self):
        """Test content without hierarchy info."""
        content = "### EPIC-123: Simple Epic\n\nJust a description."
        parent, level, children = extract_epic_hierarchy(content, "EPIC-123")
        assert parent is None
        assert level == EpicLevel.EPIC
        assert len(children) == 0


class TestBuildHierarchyFromEpics:
    """Tests for build_hierarchy_from_epics function."""

    def test_build_simple_hierarchy(self):
        """Test building a simple hierarchy."""
        epics = [
            {"key": "INIT-1", "title": "Initiative"},
            {"key": "EPIC-1", "title": "Epic 1", "parent_key": "INIT-1"},
            {"key": "EPIC-2", "title": "Epic 2", "parent_key": "INIT-1"},
        ]

        hierarchy = build_hierarchy_from_epics(epics)

        assert len(hierarchy.roots) == 1
        assert hierarchy.roots[0].id == "INIT-1"
        assert len(hierarchy.roots[0].children) == 2

    def test_build_multiple_roots(self):
        """Test building with multiple root nodes."""
        epics = [
            {"key": "PORT-1", "title": "Portfolio 1"},
            {"key": "PORT-2", "title": "Portfolio 2"},
        ]

        hierarchy = build_hierarchy_from_epics(epics)
        assert len(hierarchy.roots) == 2


class TestHierarchySyncConfig:
    """Tests for HierarchySyncConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = HierarchySyncConfig()
        assert config.enabled is True
        assert config.sync_parent_links is True
        assert config.validate_hierarchy is True

    def test_custom_config(self):
        """Test custom configuration values."""
        config = HierarchySyncConfig(
            create_missing_parents=True,
            level_field="customfield_10100",
        )
        assert config.create_missing_parents is True
        assert config.level_field == "customfield_10100"


class TestHierarchySyncResult:
    """Tests for HierarchySyncResult."""

    def test_success_by_default(self):
        """Test success is True by default."""
        result = HierarchySyncResult()
        assert result.success is True
