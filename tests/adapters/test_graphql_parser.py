"""Tests for GraphQL Schema parser."""

import textwrap

import pytest

from spectryn.adapters.parsers.graphql_parser import GraphQLParser
from spectryn.core.domain.enums import Priority, Status


class TestGraphQLParser:
    """Tests for GraphQLParser."""

    @pytest.fixture
    def parser(self) -> GraphQLParser:
        """Create parser instance."""
        return GraphQLParser()

    @pytest.fixture
    def sample_graphql(self) -> str:
        """Sample GraphQL content with stories."""
        return textwrap.dedent('''
            # Epic: PROJ-123 - User API
            # Epic Key: PROJ-123

            """
            PROJ-001: Create User Mutation
            Story Points: 5
            Priority: High
            Status: Planned

            Description:
            As a client application
            I want to create users via GraphQL
            So that I can onboard new users

            Acceptance Criteria:
            - [ ] Validates email format
            - [x] Returns user ID
            """
            type Mutation {
                createUser(input: CreateUserInput!): User!
            }

            """
            PROJ-002: Query Users
            Story Points: 3
            Priority: Medium
            Status: Done
            """
            type Query {
                users(filter: UserFilter): [User!]!
                user(id: ID!): User
            }

            type User {
                id: ID!
                email: String!
                name: String
            }
        ''')

    def test_name(self, parser: GraphQLParser) -> None:
        """Test parser name."""
        assert parser.name == "GraphQL"

    def test_supported_extensions(self, parser: GraphQLParser) -> None:
        """Test supported file extensions."""
        assert ".graphql" in parser.supported_extensions
        assert ".gql" in parser.supported_extensions

    def test_can_parse_graphql_content(self, parser: GraphQLParser, sample_graphql: str) -> None:
        """Test can_parse with GraphQL content."""
        assert parser.can_parse(sample_graphql) is True

    def test_cannot_parse_plain_text(self, parser: GraphQLParser) -> None:
        """Test can_parse with plain text."""
        assert parser.can_parse("Just plain text") is False

    def test_parse_stories(self, parser: GraphQLParser, sample_graphql: str) -> None:
        """Test parsing stories from GraphQL content."""
        stories = parser.parse_stories(sample_graphql)

        assert len(stories) == 2

        # First story
        story1 = stories[0]
        assert str(story1.id) == "PROJ-001"
        assert story1.title == "Create User Mutation"
        assert story1.story_points == 5
        assert story1.priority == Priority.HIGH
        assert story1.status == Status.PLANNED

        # Description
        assert story1.description is not None
        assert "client application" in story1.description.role

        # Acceptance criteria
        assert len(story1.acceptance_criteria.items) == 2

        # Second story
        story2 = stories[1]
        assert str(story2.id) == "PROJ-002"
        assert story2.status == Status.DONE

    def test_parse_epic(self, parser: GraphQLParser, sample_graphql: str) -> None:
        """Test parsing epic from GraphQL content."""
        epic = parser.parse_epic(sample_graphql)

        assert epic is not None
        assert str(epic.key) == "PROJ-123"
        assert "User API" in epic.title
        assert len(epic.stories) == 2

    def test_validate_valid_content(self, parser: GraphQLParser, sample_graphql: str) -> None:
        """Test validation of valid GraphQL content."""
        errors = parser.validate(sample_graphql)
        assert len(errors) == 0

    def test_validate_missing_types(self, parser: GraphQLParser) -> None:
        """Test validation of GraphQL without type definitions."""
        errors = parser.validate("# Just a comment")
        assert any("type definitions" in e.lower() for e in errors)

    def test_parse_file(self, parser: GraphQLParser, tmp_path) -> None:
        """Test parsing from file."""
        content = textwrap.dedent('''
            """
            PROJ-001: Test Query
            Story Points: 3
            """
            type Query {
                test: String
            }
        ''')

        gql_file = tmp_path / "schema.graphql"
        gql_file.write_text(content)

        stories = parser.parse_stories(gql_file)
        assert len(stories) == 1
        assert str(stories[0].id) == "PROJ-001"
