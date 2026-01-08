"""Tests for custom field mapping functionality."""

import tempfile
from pathlib import Path

import pytest

from spectryn.application.sync.field_mapping import (
    FieldDefinition,
    FieldDirection,
    FieldMapper,
    FieldMappingLoader,
    FieldType,
    FieldValueMapping,
    TrackerFieldMappingConfig,
    create_default_jira_mapping,
    create_field_mapper_from_config,
)


class TestFieldType:
    """Tests for FieldType enum."""

    def test_all_types_exist(self):
        """Test all field types are defined."""
        assert FieldType.TEXT.value == "text"
        assert FieldType.NUMBER.value == "number"
        assert FieldType.FLOAT.value == "float"
        assert FieldType.DROPDOWN.value == "dropdown"
        assert FieldType.MULTI_SELECT.value == "multi_select"
        assert FieldType.DATE.value == "date"
        assert FieldType.DATETIME.value == "datetime"
        assert FieldType.USER.value == "user"
        assert FieldType.URL.value == "url"
        assert FieldType.BOOLEAN.value == "boolean"
        assert FieldType.LABELS.value == "labels"
        assert FieldType.RICH_TEXT.value == "rich_text"


class TestFieldDirection:
    """Tests for FieldDirection enum."""

    def test_all_directions_exist(self):
        """Test all directions are defined."""
        assert FieldDirection.BIDIRECTIONAL.value == "bidirectional"
        assert FieldDirection.PUSH_ONLY.value == "push_only"
        assert FieldDirection.PULL_ONLY.value == "pull_only"
        assert FieldDirection.READ_ONLY.value == "read_only"


class TestFieldValueMapping:
    """Tests for FieldValueMapping."""

    def test_matches_markdown(self):
        """Test matching markdown values."""
        mapping = FieldValueMapping(
            markdown_value="High",
            tracker_value="10001",
            aliases=["H", "Important"],
        )
        assert mapping.matches_markdown("High")
        assert mapping.matches_markdown("high")
        assert mapping.matches_markdown("H")
        assert mapping.matches_markdown("important")
        assert not mapping.matches_markdown("Low")

    def test_matches_tracker(self):
        """Test matching tracker values."""
        mapping = FieldValueMapping(
            markdown_value="High",
            tracker_value="10001",
        )
        assert mapping.matches_tracker("10001")
        assert not mapping.matches_tracker("10002")


class TestFieldDefinition:
    """Tests for FieldDefinition."""

    def test_create_basic_field(self):
        """Test creating a basic field definition."""
        field = FieldDefinition(
            name="story_points",
            markdown_name="Story Points",
            tracker_field_id="customfield_10014",
            field_type=FieldType.NUMBER,
        )
        assert field.name == "story_points"
        assert field.markdown_name == "Story Points"
        assert field.tracker_field_id == "customfield_10014"
        assert field.field_type == FieldType.NUMBER
        assert field.direction == FieldDirection.BIDIRECTIONAL
        assert not field.required

    def test_field_to_dict_and_back(self):
        """Test serialization roundtrip."""
        field = FieldDefinition(
            name="team",
            markdown_name="Team",
            tracker_field_id="customfield_10050",
            field_type=FieldType.DROPDOWN,
            required=True,
            value_mappings=[
                FieldValueMapping("Backend", "10001", ["BE"]),
                FieldValueMapping("Frontend", "10002", ["FE"]),
            ],
        )
        data = field.to_dict()
        restored = FieldDefinition.from_dict(data)

        assert restored.name == field.name
        assert restored.markdown_name == field.markdown_name
        assert restored.tracker_field_id == field.tracker_field_id
        assert restored.field_type == field.field_type
        assert restored.required == field.required
        assert len(restored.value_mappings) == 2


class TestTrackerFieldMappingConfig:
    """Tests for TrackerFieldMappingConfig."""

    def test_create_config(self):
        """Test creating tracker config."""
        config = TrackerFieldMappingConfig(
            tracker_type="jira",
            project_key="PROJ",
            story_points_field="customfield_10014",
            priority_field="priority",
        )
        assert config.tracker_type == "jira"
        assert config.project_key == "PROJ"
        assert config.story_points_field == "customfield_10014"

    def test_config_to_dict_and_back(self):
        """Test serialization roundtrip."""
        config = TrackerFieldMappingConfig(
            tracker_type="jira",
            story_points_field="customfield_10014",
            status_mapping={"Done": "Closed"},
            custom_fields=[
                FieldDefinition(
                    name="team",
                    markdown_name="Team",
                    tracker_field_id="customfield_10050",
                )
            ],
        )
        data = config.to_dict()
        restored = TrackerFieldMappingConfig.from_dict(data)

        assert restored.tracker_type == "jira"
        assert restored.story_points_field == "customfield_10014"
        assert restored.status_mapping == {"Done": "Closed"}
        assert len(restored.custom_fields) == 1


class TestFieldMapper:
    """Tests for FieldMapper."""

    def test_default_jira_mappings(self):
        """Test default Jira field mappings."""
        mapper = FieldMapper()

        assert mapper.get_tracker_field_id("story_points", "jira") == "customfield_10014"
        assert mapper.get_tracker_field_id("Story Points", "jira") == "customfield_10014"
        assert mapper.get_tracker_field_id("priority", "jira") == "priority"
        assert mapper.get_tracker_field_id("status", "jira") == "status"

    def test_custom_field_mapping(self):
        """Test custom field mappings override defaults."""
        config = TrackerFieldMappingConfig(
            tracker_type="jira",
            story_points_field="customfield_99999",
        )
        mapper = FieldMapper(config=config)

        assert mapper.get_tracker_field_id("story_points", "jira") == "customfield_99999"

    def test_project_specific_mapping(self):
        """Test project-specific field mappings."""
        global_config = TrackerFieldMappingConfig(
            tracker_type="jira",
            story_points_field="customfield_10014",
        )
        project_config = TrackerFieldMappingConfig(
            tracker_type="jira",
            project_key="PROJ",
            story_points_field="customfield_20000",
        )
        mapper = FieldMapper(configs=[global_config, project_config])

        # Project-specific takes precedence
        assert mapper.get_tracker_field_id("story_points", "jira", "PROJ") == "customfield_20000"
        # Falls back to global
        assert mapper.get_tracker_field_id("story_points", "jira") == "customfield_10014"

    def test_custom_field_definitions(self):
        """Test custom field definitions."""
        config = TrackerFieldMappingConfig(
            tracker_type="jira",
            custom_fields=[
                FieldDefinition(
                    name="team",
                    markdown_name="Team",
                    tracker_field_id="customfield_10050",
                    field_type=FieldType.DROPDOWN,
                )
            ],
        )
        mapper = FieldMapper(config=config)

        assert mapper.get_tracker_field_id("Team", "jira") == "customfield_10050"
        field_def = mapper.get_field_definition("Team", "jira")
        assert field_def is not None
        assert field_def.field_type == FieldType.DROPDOWN

    def test_reverse_lookup(self):
        """Test getting markdown name from tracker field ID."""
        config = TrackerFieldMappingConfig(
            tracker_type="jira",
            custom_fields=[
                FieldDefinition(
                    name="team",
                    markdown_name="Team",
                    tracker_field_id="customfield_10050",
                )
            ],
        )
        mapper = FieldMapper(config=config)

        assert mapper.get_markdown_field_name("customfield_10050", "jira") == "Team"

    def test_transform_dropdown_value_to_tracker(self):
        """Test transforming dropdown values to tracker format."""
        config = TrackerFieldMappingConfig(
            tracker_type="jira",
            custom_fields=[
                FieldDefinition(
                    name="priority",
                    markdown_name="Priority",
                    tracker_field_id="customfield_10040",
                    field_type=FieldType.DROPDOWN,
                    value_mappings=[
                        FieldValueMapping("Critical", "1", ["P0"]),
                        FieldValueMapping("High", "2", ["P1"]),
                        FieldValueMapping("Medium", "3", ["P2"]),
                    ],
                )
            ],
        )
        mapper = FieldMapper(config=config)

        assert mapper.transform_value_to_tracker("Priority", "Critical", "jira") == "1"
        assert mapper.transform_value_to_tracker("Priority", "P0", "jira") == "1"
        assert mapper.transform_value_to_tracker("Priority", "High", "jira") == "2"

    def test_transform_number_value(self):
        """Test transforming number values."""
        config = TrackerFieldMappingConfig(
            tracker_type="jira",
            custom_fields=[
                FieldDefinition(
                    name="effort",
                    markdown_name="Effort",
                    tracker_field_id="customfield_10041",
                    field_type=FieldType.NUMBER,
                )
            ],
        )
        mapper = FieldMapper(config=config)

        assert mapper.transform_value_to_tracker("Effort", "5", "jira") == 5
        assert mapper.transform_value_to_tracker("Effort", 10, "jira") == 10

    def test_transform_boolean_value(self):
        """Test transforming boolean values."""
        config = TrackerFieldMappingConfig(
            tracker_type="jira",
            custom_fields=[
                FieldDefinition(
                    name="feature_flag",
                    markdown_name="Feature Flag",
                    tracker_field_id="customfield_10042",
                    field_type=FieldType.BOOLEAN,
                )
            ],
        )
        mapper = FieldMapper(config=config)

        assert mapper.transform_value_to_tracker("Feature Flag", "true", "jira") is True
        assert mapper.transform_value_to_tracker("Feature Flag", "yes", "jira") is True
        assert mapper.transform_value_to_tracker("Feature Flag", "no", "jira") is False

    def test_transform_labels_value(self):
        """Test transforming labels values."""
        config = TrackerFieldMappingConfig(
            tracker_type="jira",
            custom_fields=[
                FieldDefinition(
                    name="tags",
                    markdown_name="Tags",
                    tracker_field_id="customfield_10043",
                    field_type=FieldType.LABELS,
                )
            ],
        )
        mapper = FieldMapper(config=config)

        result = mapper.transform_value_to_tracker("Tags", "bug, feature, urgent", "jira")
        assert result == ["bug", "feature", "urgent"]

    def test_validate_required_field(self):
        """Test validation of required fields."""
        config = TrackerFieldMappingConfig(
            tracker_type="jira",
            custom_fields=[
                FieldDefinition(
                    name="team",
                    markdown_name="Team",
                    tracker_field_id="customfield_10050",
                    required=True,
                )
            ],
        )
        mapper = FieldMapper(config=config)

        is_valid, error = mapper.validate_value("Team", "", "jira")
        assert not is_valid
        assert "required" in error.lower()

        is_valid, error = mapper.validate_value("Team", "Backend", "jira")
        assert is_valid
        assert error is None

    def test_validate_allowed_values(self):
        """Test validation of allowed values."""
        config = TrackerFieldMappingConfig(
            tracker_type="jira",
            custom_fields=[
                FieldDefinition(
                    name="env",
                    markdown_name="Environment",
                    tracker_field_id="customfield_10051",
                    allowed_values=["dev", "staging", "prod"],
                )
            ],
        )
        mapper = FieldMapper(config=config)

        is_valid, error = mapper.validate_value("Environment", "dev", "jira")
        assert is_valid

        is_valid, error = mapper.validate_value("Environment", "test", "jira")
        assert not is_valid
        assert "allowed values" in error.lower()

    def test_validate_numeric_bounds(self):
        """Test validation of numeric bounds."""
        config = TrackerFieldMappingConfig(
            tracker_type="jira",
            custom_fields=[
                FieldDefinition(
                    name="score",
                    markdown_name="Score",
                    tracker_field_id="customfield_10052",
                    field_type=FieldType.NUMBER,
                    min_value=1,
                    max_value=10,
                )
            ],
        )
        mapper = FieldMapper(config=config)

        is_valid, error = mapper.validate_value("Score", "5", "jira")
        assert is_valid

        is_valid, error = mapper.validate_value("Score", "0", "jira")
        assert not is_valid
        assert "below minimum" in error.lower()

        is_valid, error = mapper.validate_value("Score", "15", "jira")
        assert not is_valid
        assert "above maximum" in error.lower()

    def test_get_all_custom_fields(self):
        """Test getting all custom fields."""
        config = TrackerFieldMappingConfig(
            tracker_type="jira",
            custom_fields=[
                FieldDefinition(name="a", markdown_name="A", tracker_field_id="cf_a"),
                FieldDefinition(name="b", markdown_name="B", tracker_field_id="cf_b"),
            ],
        )
        mapper = FieldMapper(config=config)

        fields = mapper.get_all_custom_fields("jira")
        assert len(fields) == 2


class TestFieldMappingLoader:
    """Tests for FieldMappingLoader."""

    def test_load_from_yaml(self):
        """Test loading configuration from YAML file."""
        yaml_content = """
tracker_type: jira
project_key: TEST
story_points_field: customfield_99999
status_mapping:
  Done: Closed
custom_fields:
  - name: team
    markdown_name: Team
    tracker_field_id: customfield_10050
    field_type: dropdown
    value_mappings:
      - markdown: Backend
        tracker: "10001"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            config = FieldMappingLoader.load_from_yaml(Path(f.name))

        assert config.tracker_type == "jira"
        assert config.project_key == "TEST"
        assert config.story_points_field == "customfield_99999"
        assert config.status_mapping == {"Done": "Closed"}
        assert len(config.custom_fields) == 1
        assert config.custom_fields[0].name == "team"

    def test_save_to_yaml(self):
        """Test saving configuration to YAML file."""
        config = TrackerFieldMappingConfig(
            tracker_type="jira",
            project_key="TEST",
            story_points_field="customfield_10014",
            custom_fields=[
                FieldDefinition(
                    name="team",
                    markdown_name="Team",
                    tracker_field_id="customfield_10050",
                )
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mapping.yaml"
            FieldMappingLoader.save_to_yaml(config, path)

            assert path.exists()

            # Reload and verify
            loaded = FieldMappingLoader.load_from_yaml(path)
            assert loaded.tracker_type == "jira"
            assert loaded.project_key == "TEST"

    def test_load_from_dict(self):
        """Test loading configuration from dictionary."""
        data = {
            "tracker_type": "github",
            "story_points_field": "story_points",
            "custom_fields": [
                {
                    "name": "complexity",
                    "markdown_name": "Complexity",
                    "tracker_field_id": "complexity_label",
                    "field_type": "dropdown",
                }
            ],
        }
        config = FieldMappingLoader.load_from_dict(data)

        assert config.tracker_type == "github"
        assert config.story_points_field == "story_points"
        assert len(config.custom_fields) == 1


class TestCreateDefaultJiraMapping:
    """Tests for create_default_jira_mapping."""

    def test_creates_valid_config(self):
        """Test that default mapping is valid."""
        config = create_default_jira_mapping()

        assert config.tracker_type == "jira"
        assert config.story_points_field == "customfield_10014"
        assert config.priority_field == "priority"
        assert config.status_field == "status"
        assert "Done" in config.status_mapping
        assert "Critical" in config.priority_mapping


class TestCreateFieldMapperFromConfig:
    """Tests for create_field_mapper_from_config."""

    def test_creates_mapper_from_file(self):
        """Test creating mapper from config file."""
        yaml_content = """
tracker_type: jira
story_points_field: customfield_99999
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            mapper = create_field_mapper_from_config(config_path=Path(f.name))

        assert mapper.get_tracker_field_id("story_points", "jira") == "customfield_99999"

    def test_creates_mapper_from_dict(self):
        """Test creating mapper from dictionary."""
        config_dict = {
            "tracker_type": "jira",
            "story_points_field": "customfield_88888",
        }
        mapper = create_field_mapper_from_config(config_dict=config_dict)

        assert mapper.get_tracker_field_id("story_points", "jira") == "customfield_88888"

    def test_uses_defaults_when_no_config(self):
        """Test using defaults when no config provided."""
        mapper = create_field_mapper_from_config()

        # Should use default Jira mapping
        assert mapper.get_tracker_field_id("story_points", "jira") == "customfield_10014"
