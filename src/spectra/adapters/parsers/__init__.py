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
from .rst_parser import RstParser
from .toml_parser import TomlParser
from .toon_parser import ToonParser
from .yaml_parser import YamlParser
from .yaml_plugin import YamlParserPlugin


__all__ = [
    "AsciiDocParser",
    "BaseDictParser",
    "ConfluenceParser",
    "CsvParser",
    "DiagramParser",
    "ExcelParser",
    "GoogleDocsParser",
    "GoogleSheetsParser",
    "GraphQLParser",
    "JsonParser",
    "MarkdownParser",
    "NotionParser",
    "NotionParserPlugin",
    "ObsidianParser",
    "OpenAPIParser",
    "OrgModeParser",
    "ProtobufParser",
    "RstParser",
    "TomlParser",
    "ToonParser",
    "YamlParser",
    "YamlParserPlugin",
    "parse_blockquote_comments",
    "parse_datetime",
]
