# Flexibility Plan: Remove System-Imposed Constraints

> ✅ **FULLY IMPLEMENTED** - This plan has been completely implemented. All parsers now accept any PREFIX-NUMBER format, custom separators (hyphen, underscore, forward slash), and GitHub-style `#123` IDs.

## Problem Statement

Spectra currently hardcodes `US-` as the story ID prefix throughout the codebase. This is prescriptive and forces users to conform to our naming convention rather than their own. Organizations use various prefixes:

- `EU-001`, `NA-002` (regional teams)
- `PROJ-123`, `AUTH-456` (project-based)
- `BE-001`, `FE-002` (team-based: backend, frontend)
- `FEAT-001`, `BUG-002` (type-based)
- `JIRA-123` (tool-based)
- Custom conventions unique to each org

**Philosophy Change**: Spectra should be **descriptive** (parse what the user writes) not **prescriptive** (force the user to write what we expect).

---

## Affected Areas

### 1. Core Domain: `StoryId` Value Object

**File**: `src/spectra/core/domain/value_objects.py`

**Current Issues**:
```python
@dataclass(frozen=True)
class StoryId:
    """Format: US-XXX (e.g., US-001, US-042)"""  # ← Prescriptive doc

    def __post_init__(self) -> None:
        if not re.match(r"^US-\d{3,}$", self.value):  # ← Validates only US-
            pass

    @classmethod
    def from_string(cls, value: str) -> StoryId:
        value = value.strip().upper()
        if not value.startswith("US-"):
            value = f"US-{value}"  # ← Forces US- prefix!
        return cls(value)
```

**Fix**:
- Accept any `[A-Z]+-\d+` format (like `IssueKey` already does)
- Remove forced prefix insertion
- Consider merging with or deprecating in favor of `IssueKey` which is already flexible

---

### 2. Markdown Parser Patterns

**File**: `src/spectra/adapters/parsers/markdown.py`

**Current Issues**:
```python
# Lines 102-106 - Only match US-###
STORY_PATTERN = r"### (?:[^\n]+ )?(US-\d+): ([^\n]+)\n"
STORY_PATTERN_FLEXIBLE = r"### (?:.*?)?(US-\d+):\s*([^\n]+)\n"
STORY_PATTERN_H1 = r"^#\s+(?:.*?)?(US-\d+):\s*([^\n]+?)(?:\s*[✅🔲🟡⏸️]+)?\s*$"

# Line 543 - Error message mentions only US-
"No user stories found matching pattern '### [emoji] US-XXX: Title' or '### US-XXX: Title'"
```

**Fix**:
```python
# Generic pattern: PREFIX-NUMBER where PREFIX is 1+ uppercase letters
STORY_ID_PATTERN = r"[A-Z]+-\d+"

STORY_PATTERN = rf"### (?:[^\n]+ )?({STORY_ID_PATTERN}): ([^\n]+)\n"
STORY_PATTERN_FLEXIBLE = rf"### (?:.*?)?({STORY_ID_PATTERN}):\s*([^\n]+)\n"
STORY_PATTERN_H1 = rf"^#\s+(?:.*?)?({STORY_ID_PATTERN}):\s*([^\n]+?)(?:\s*[✅🔲🟡⏸️]+)?\s*$"
```

---

### 3. Validator Patterns

**File**: `src/spectra/cli/validate.py`

**Current Issues**:
```python
# Line 219-221 - h1 only allows US-, h2/h3 allows any
STORY_PATTERN = re.compile(
    r"^(?:"
    r"#{2,3}\s+(?:[^\s:]+\s+)?(?P<id1>US-\d+|[A-Z]+-\d+)"  # h2/h3: any ✓
    r"|"
    r"#\s+(?:[^\s:]+\s+)?(?P<id2>US-\d+)"  # h1: ONLY US-XXX ✗
    r"):\s*(?P<title>.+?)(?:\s*[✅🔲🟡⏸️]+)?$",
)

# Line 318 - Prescriptive suggestion
suggestion="Add stories with format: ### US-001: Story Title"
```

**Fix**:
- Make h1 pattern also accept `[A-Z]+-\d+`
- Update suggestions to use generic format: `### PREFIX-001: Story Title`

---

### 4. Other Parsers

**AsciiDoc Parser** (`src/spectra/adapters/parsers/asciidoc_parser.py`):
```python
STORY_PATTERN = r"^==\s+(?:.*?)?(US-\d+):\s*([^\n]+)"  # ← Hardcoded
```

**Notion Parser** (`src/spectra/adapters/parsers/notion_parser.py`):
```python
STORY_ID_PATTERNS = [
    r"(?:US|STORY|S)-?\d{3,}",  # ← Limited options
    ...
]
```

**Fix**: Use generic `[A-Z]+-\d+` pattern in all parsers.

---

### 5. Multi-File Directory Parsing

**File**: `src/spectra/adapters/parsers/markdown.py`

**Current Issue** (line 84):
```python
# US-001-*.md, US-002-*.md, etc. (individual story files)
```

The directory parser likely expects files named `US-###-*.md`.

**Fix**: Accept any `PREFIX-###-*.md` pattern or rely on content parsing rather than filename matching.

---

### 6. Documentation & Examples

**Files affected**:
- `docs/guide/schema.md` - Pattern documentation
- `docs/guide/agents.md` - Example patterns
- `docs/guide/quick-start.md` - All examples use US-
- `docs/guide/getting-started.md` - Examples
- `docs/examples/template.md` - Template uses US-
- `docs/reference/cli.md` - CLI examples
- `README.md` - Examples

**Fix**:
- Update pattern documentation to show generic format
- Keep examples using a consistent prefix (maybe `STORY-001` to be neutral)
- Add note that any `PREFIX-###` format works

---

### 7. Tests

All test files use `US-001`, `US-002`, etc. as test fixtures.

**Fix**:
- Add tests with different prefixes (`EU-001`, `PROJ-123`, `FEAT-001`)
- Ensure all parsers handle varied prefixes
- Keep some `US-` tests for backwards compatibility

---

### 8. AI Prompts & Templates

**File**: `src/spectra/cli/ai_fix.py`

Contains hardcoded examples using `US-001` format in prompts.

**Fix**: Make prompts dynamic or use neutral examples.

---

## Implementation Plan

### Phase 1: Core Changes (Breaking)

1. **Update `StoryId` value object**
   - Remove `US-` prefix enforcement
   - Accept any `[A-Z]+-\d+` format
   - Add `prefix` property to extract the prefix portion

2. **Update regex patterns** in all parsers:
   - `markdown.py`
   - `asciidoc_parser.py`
   - `notion_parser.py`
   - `validate.py`

3. **Update error messages** to be generic

### Phase 2: Tests

1. Add parameterized tests for various prefixes
2. Ensure all parsers handle:
   - `US-001` (backwards compat)
   - `EU-001`, `NA-001` (regional)
   - `PROJ-123` (project)
   - `A-1` (minimal)
   - `VERYLONGPREFIX-99999` (edge case)

### Phase 3: Documentation

1. Update all docs to show generic pattern
2. Clarify that users can use their own convention
3. Update template.md with neutral examples

---

## Backwards Compatibility

- All changes should be **backwards compatible** for existing `US-` users
- The generic pattern `[A-Z]+-\d+` includes `US-\d+`
- No migration needed for existing documents

---

## Related Improvements Status

While we're removing restrictions, consider these related improvements:

| Improvement | Status | Notes |
|-------------|--------|-------|
| **Epic ID flexibility** | ✅ Done | `IssueKey` accepts any `[A-Z]+-\d+` format |
| **Number padding** | ✅ Done | Pattern `[A-Z]+-\d+` allows `PROJ-1` or `PROJ-001` |
| **Lowercase tolerance** | ✅ Done | `StoryId` normalizes to uppercase via `.upper()` |
| **Custom separators** | ✅ Done | Supports hyphen `-`, underscore `_`, and forward slash `/` |
| **Purely numeric IDs** | ✅ Done | All parsers support `#123` GitHub-style IDs |

### ~~Remaining Work~~ ✅ ALL COMPLETED

1. ~~**Custom separators** (`PROJ_001`, `PROJ/001`)~~: ✅ **COMPLETED**
   - `STORY_ID_PATTERN` updated in all parsers to accept `[-_/]`
   - See `markdown.py` line 657: `PROJ-123, PROJ_123, PROJ/123`

2. ~~**Universal `#123` support**~~: ✅ **COMPLETED**
   - GitHub-style `#123` IDs supported in all parsers
   - See `markdown.py` line 914: error messages now show `#123` as valid format

---

## Priority

**High** - This is a fundamental usability issue that limits adoption. Users shouldn't have to rename their existing stories to match our conventions.

---

## Estimated Effort

- Phase 1: ~2-3 hours
- Phase 2: ~1-2 hours
- Phase 3: ~1 hour

**Total**: ~4-6 hours

---

## Success Criteria

1. Users can use any `PREFIX-NUMBER` format for story IDs
2. All existing `US-` documents continue to work
3. Documentation clearly states format flexibility
4. Tests cover multiple prefix formats

