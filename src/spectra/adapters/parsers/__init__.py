"""
Document Parsers - Convert source documents into domain entities.

Supported formats:
- Markdown (.md, .markdown) - Standard markdown epic files
- YAML (.yaml, .yml) - Structured YAML specifications
- JSON (.json) - Structured JSON specifications
- TOML (.toml) - TOML configuration-style format
- CSV (.csv, .tsv) - Spreadsheet/tabular data
- AsciiDoc (.adoc, .asciidoc) - Technical documentation format
- Excel (.xlsx, .xlsm, .xls) - Microsoft Excel spreadsheets
- TOON (.toon) - Token-Oriented Object Notation (LLM-optimized)
- Notion - Notion export files (pages, databases, folders)
- ReStructuredText (.rst, .rest) - Python documentation standard
- Org-mode (.org) - Emacs outliner format
- Obsidian Markdown - Wikilinks, dataview syntax, frontmatter
- Confluence Cloud - Parse directly from Confluence pages via API
- Google Docs - Parse from Google Workspace documents via API
- Protobuf (.proto) - Protocol Buffer specifications
- GraphQL (.graphql, .gql) - GraphQL schema files
- PlantUML/Mermaid (.puml, .mmd) - Diagram-based requirements
- OpenAPI/Swagger (.yaml, .json) - API specifications
- Google Sheets - Direct cloud spreadsheet sync via API
"""

from .asciidoc_parser import AsciiDocParser
from .base_dict_parser import BaseDictParser
from .confluence_parser import ConfluenceParser
from .csv_parser import CsvParser
from .diagram_parser import DiagramParser
from .excel_parser import ExcelParser

# Frontmatter parsing
from .frontmatter import (
    FieldMapping,
    FrontmatterConfig,
    FrontmatterFormat,
    FrontmatterParser,
    FrontmatterParseResult,
    FrontmatterSpan,
    MergeStrategy,
    create_frontmatter_parser,
    create_markdown_with_frontmatter,
    extract_html_comment_frontmatter,
    extract_inline_frontmatter,
    extract_yaml_frontmatter,
    get_frontmatter,
    has_frontmatter,
    parse_acceptance_criteria_from_frontmatter,
    parse_description_from_frontmatter,
    parse_epic_from_frontmatter,
    parse_story_from_frontmatter,
    parse_subtasks_from_frontmatter,
    strip_frontmatter,
)
from .google_docs_parser import GoogleDocsParser
from .google_sheets_parser import GoogleSheetsParser
from .graphql_parser import GraphQLParser
from .json_parser import JsonParser
from .markdown import MarkdownParser
from .notion_parser import NotionParser
from .notion_plugin import NotionParserPlugin
from .obsidian_parser import ObsidianParser
from .openapi_parser import OpenAPIParser
from .orgmode_parser import OrgModeParser
from .parser_utils import parse_blockquote_comments, parse_datetime
from .protobuf_parser import ProtobufParser

# Round-trip editing
from .roundtrip import (
    EditOperation,
    EditType,
    FieldSpan,
    ParsedStoryWithSpans,
    RoundtripEditor,
    RoundtripParser,
    RoundtripParseResult,
    SectionSpan,
    SourceSpan,
    StorySpan,
    batch_update_stories,
    update_story_in_file,
)
from .rst_parser import RstParser

# Schema validation
from .schema_validation import (
    EpicSchema,
    FieldSchema,
    FieldType,
    SchemaPreset,
    SchemaValidator,
    StorySchema,
    SubtaskSchema,
    ValidatingParser,
    ValidationError,
    ValidationMode,
    ValidationResult,
    ValidationSeverity,
    ValidationWarning,
    create_schema,
    create_validator,
    matches_pattern,
    max_length,
    max_value,
    min_length,
    min_value,
    not_empty,
    one_of,
    valid_priority,
    valid_status,
    valid_story_id,
)
from .streaming import (
    ChunkedFileProcessor,
    ChunkInfo,
    MemoryMappedParser,
    StoryBuffer,
    StreamingConfig,
    StreamingMarkdownParser,
    StreamingStats,
    estimate_file_stories,
    get_file_stats,
    stream_stories_from_directory,
    stream_stories_from_file,
)

# Tolerant parsing utilities
from .tolerant_markdown import (
    EmbeddedImage,
    InlineSubtaskInfo,
    ParsedTable,
    ParseErrorCode,
    ParseErrorInfo,
    ParseIssue,
    ParseLocation,
    ParseResult,
    ParseSeverity,
    ParseWarning,
    TableAlignment,
    TableCell,
    TolerantFieldExtractor,
    TolerantPatterns,
    TolerantSectionExtractor,
    extract_images_from_section,
    extract_table_from_section,
    extract_tables_from_content,
    get_column_number,
    get_context_lines,
    get_line_content,
    get_line_number,
    location_from_match,
    parse_checkboxes_tolerant,
    parse_description_tolerant,
    parse_embedded_images,
    parse_inline_subtasks,
    parse_markdown_table,
    table_to_markdown,
)
from .toml_parser import TomlParser
from .toon_parser import ToonParser
from .yaml_parser import YamlParser
from .yaml_plugin import YamlParserPlugin


__all__ = [
    "AsciiDocParser",
    "BaseDictParser",
    "ChunkInfo",
    "ChunkedFileProcessor",
    "ConfluenceParser",
    "CsvParser",
    "DiagramParser",
    # Round-trip editing exports
    "EditOperation",
    "EditType",
    # Image embedding exports
    "EmbeddedImage",
    # Schema validation exports
    "EpicSchema",
    "ExcelParser",
    # Frontmatter exports
    "FieldMapping",
    "FieldSchema",
    "FieldSpan",
    "FieldType",
    "FrontmatterConfig",
    "FrontmatterFormat",
    "FrontmatterParseResult",
    "FrontmatterParser",
    "FrontmatterSpan",
    "GoogleDocsParser",
    "GoogleSheetsParser",
    "GraphQLParser",
    # Inline subtask parsing
    "InlineSubtaskInfo",
    "JsonParser",
    "MarkdownParser",
    "MemoryMappedParser",
    "MergeStrategy",
    "NotionParser",
    "NotionParserPlugin",
    "ObsidianParser",
    "OpenAPIParser",
    "OrgModeParser",
    # Tolerant parsing exports
    "ParseErrorCode",
    "ParseErrorInfo",
    "ParseIssue",
    "ParseLocation",
    "ParseResult",
    "ParseSeverity",
    "ParseWarning",
    "ParsedStoryWithSpans",
    "ParsedTable",
    "ProtobufParser",
    "RoundtripEditor",
    "RoundtripParseResult",
    "RoundtripParser",
    "RstParser",
    "SchemaPreset",
    "SchemaValidator",
    "SectionSpan",
    "SourceSpan",
    "StoryBuffer",
    "StorySchema",
    "StorySpan",
    "StreamingConfig",
    "StreamingMarkdownParser",
    "StreamingStats",
    "SubtaskSchema",
    "TableAlignment",
    "TableCell",
    "TolerantFieldExtractor",
    "TolerantPatterns",
    "TolerantSectionExtractor",
    "TomlParser",
    "ToonParser",
    "ValidatingParser",
    "ValidationError",
    "ValidationMode",
    "ValidationResult",
    "ValidationSeverity",
    "ValidationWarning",
    "YamlParser",
    "YamlParserPlugin",
    "batch_update_stories",
    "create_frontmatter_parser",
    "create_markdown_with_frontmatter",
    "create_schema",
    "create_validator",
    "estimate_file_stories",
    "extract_html_comment_frontmatter",
    "extract_images_from_section",
    "extract_inline_frontmatter",
    "extract_table_from_section",
    "extract_tables_from_content",
    "extract_yaml_frontmatter",
    "get_column_number",
    "get_context_lines",
    "get_file_stats",
    "get_frontmatter",
    "get_line_content",
    "get_line_number",
    "has_frontmatter",
    "location_from_match",
    "matches_pattern",
    "max_length",
    "max_value",
    "min_length",
    "min_value",
    "not_empty",
    "one_of",
    "parse_acceptance_criteria_from_frontmatter",
    "parse_blockquote_comments",
    "parse_checkboxes_tolerant",
    "parse_datetime",
    "parse_description_from_frontmatter",
    "parse_description_tolerant",
    "parse_embedded_images",
    "parse_epic_from_frontmatter",
    "parse_inline_subtasks",
    "parse_markdown_table",
    "parse_story_from_frontmatter",
    "parse_subtasks_from_frontmatter",
    "stream_stories_from_directory",
    "stream_stories_from_file",
    "strip_frontmatter",
    "table_to_markdown",
    "update_story_in_file",
    "valid_priority",
    "valid_status",
    "valid_story_id",
]
