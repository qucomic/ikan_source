# Legado to Ikan Batch Converter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Build an offline CLI that tolerantly reads batches of Legado sources, emits one ordinary Ikan JSON candidate per source, validates each candidate, and writes a structured conversion report.

**Architecture:** A small Python package separates tolerant input parsing, capability scanning, deterministic conversion, and CLI/report orchestration. Conversion is stage-based and conservative: unsupported runtime behavior is reported and never copied into an executable Ikan field as if it worked.

**Tech Stack:** Python 3 standard library, `unittest`, existing `validate_rule.py`.

**Spec:** `docs/superpowers/specs/2026-09-05-legado-to-ikan-converter-design.md`

## Global Constraints

- Do not make network requests or execute source-provided JavaScript.
- Do not add third-party Python dependencies.
- Emit one ordinary Ikan JSON object per source, never a subscription array or `ikan://` value.
- Preserve unsupported source fragments only as redacted, bounded report excerpts.
- Continue a batch after per-source parse or conversion failures.
- Exit `0` for all converted, `2` for any partial/unsupported source, and `1` for batch-level failure.
- Use the existing `scripts/validate_rule.py` implementation for static Ikan validation.

---

### Task 1: Conversion Models and Tolerant Input Parser

**Files:**
- Create: `.agents/skills/writing-ikan-rules/scripts/legado_converter/__init__.py`
- Create: `.agents/skills/writing-ikan-rules/scripts/legado_converter/models.py`
- Create: `.agents/skills/writing-ikan-rules/scripts/legado_converter/input_parser.py`
- Create: `.agents/skills/writing-ikan-rules/tests/test_legado_input_parser.py`

**Interfaces:**
- Produce `Diagnostic`, `SourceLocation`, `ParsedSource`, `ValidationSummary`, and `ConversionResult` dataclasses in `models.py`.
- Produce `parse_text(text: str, origin: str) -> tuple[list[ParsedSource], list[Diagnostic]]`.
- Produce `load_inputs(path: Path) -> tuple[list[ParsedSource], list[Diagnostic]]` with deterministic directory traversal.

- [x] **Step 1: Write failing parser tests**

Cover a single object, standard array, comma-separated objects without brackets, optional trailing comma, braces and `},{` inside JavaScript strings, non-object entries, malformed trailing content, and deterministic `.json`/`.txt` directory order.

```python
def test_parses_comma_separated_objects_without_splitting_script_strings():
    text = r'''{"bookSourceName":"A","jsLib":"const x = '},{';"},
{"bookSourceName":"B"},'''
    sources, diagnostics = parse_text(text, "batch.txt")
    self.assertEqual(["A", "B"], [item.value["bookSourceName"] for item in sources])
    self.assertEqual([], diagnostics)
    self.assertEqual("batch.txt#2", sources[1].location.label)
```

- [x] **Step 2: Run parser tests and verify RED**

Run:

```bash
python3 .agents/skills/writing-ikan-rules/tests/test_legado_input_parser.py
```

Expected: import failure because `legado_converter.input_parser` does not exist.

- [x] **Step 3: Implement models and structural JSON stream parsing**

Use `json.JSONDecoder().raw_decode` in a cursor loop. Accept optional commas and whitespace only between complete top-level values. Flatten array entries while retaining one-based source indexes. Reject unexpected non-comma trailing characters with an `input.invalid_json` error.

```python
@dataclass(frozen=True)
class Diagnostic:
    code: str
    severity: str
    field: str
    message: str
    excerpt: str = ""

@dataclass(frozen=True)
class ParsedSource:
    value: dict[str, Any]
    location: SourceLocation
```

Directory loading must ignore other extensions and sort candidate paths by their POSIX path strings.

- [x] **Step 4: Run parser tests and verify GREEN**

Run the parser test file and confirm all cases pass with no warnings or errors.

- [x] **Step 5: Commit Task 1**

```bash
git add .agents/skills/writing-ikan-rules/scripts/legado_converter .agents/skills/writing-ikan-rules/tests/test_legado_input_parser.py
git commit -m "feat: parse legado rule batches"
```

---

### Task 2: Capability Scanner and Redaction

**Files:**
- Create: `.agents/skills/writing-ikan-rules/scripts/legado_converter/capability_scanner.py`
- Create: `.agents/skills/writing-ikan-rules/tests/test_legado_capability_scanner.py`

**Interfaces:**
- Produce `scan_capabilities(source: Mapping[str, Any]) -> list[Diagnostic]`.
- Produce `redact_excerpt(value: Any, limit: int = 240) -> str`.
- Diagnostic codes are stable strings beginning with `capability.`.

- [x] **Step 1: Write failing scanner tests**

Create sanitized source fragments that independently exercise `java.ajax`, `java.get/put`, `source.getVariable/setVariable`, login info, cookies, WebView/browser calls, `JavaImporter`, `Packages.*`, CryptoJS, Java crypto, and virtual `bookSourceUrl`.

```python
def test_scans_android_and_stateful_runtime_dependencies():
    source = {
        "bookSourceUrl": "virtual source",
        "jsLib": "source.getVariable(); new JavaImporter(); Packages.javax.crypto.Cipher;",
    }
    codes = {item.code for item in scan_capabilities(source)}
    self.assertIn("capability.virtual_host", codes)
    self.assertIn("capability.source_variable", codes)
    self.assertIn("capability.java_importer", codes)
    self.assertIn("capability.java_packages", codes)
```

Test that values associated with keys matching `authorization`, `cookie`, `password`, `token`, `secret`, and `key` are replaced by `[REDACTED]`, and that excerpts are bounded.

- [x] **Step 2: Run scanner tests and verify RED**

Run the scanner test file. Expected: import failure for the missing scanner module.

- [x] **Step 3: Implement recursive scanning and redaction**

Walk dictionary/list/string values while retaining dot-separated field paths. Use explicit compiled patterns and deterministic diagnostic ordering. Detection is advisory and must not execute or parse JavaScript as Python.

Redaction must serialize structured values after recursively masking sensitive keys. For raw strings, mask common header/assignment forms before truncating.

- [x] **Step 4: Run scanner tests and verify GREEN**

Confirm every capability code and redaction case passes.

- [x] **Step 5: Commit Task 2**

```bash
git add .agents/skills/writing-ikan-rules/scripts/legado_converter/capability_scanner.py .agents/skills/writing-ikan-rules/tests/test_legado_capability_scanner.py
git commit -m "feat: scan legado conversion capabilities"
```

---

### Task 3: Deterministic Metadata, Template, Request, and Selector Conversion

**Files:**
- Create: `.agents/skills/writing-ikan-rules/scripts/legado_converter/converter.py`
- Create: `.agents/skills/writing-ikan-rules/tests/test_legado_converter_primitives.py`

**Interfaces:**
- Produce `convert_source(parsed: ParsedSource) -> ConversionResult`.
- Keep helper interfaces private except `safe_output_name(name: str, identity: str) -> str` for CLI use.
- `ConversionResult.rule` is one ordinary Ikan dictionary; diagnostics retain source field paths.

- [x] **Step 1: Write failing metadata and identity tests**

Assert deterministic IDs and file names, Unicode display-name preservation, duplicate-name separation by identity hash, host extraction from absolute source/request URLs, virtual-host diagnostics, and explicit Legado content-type mapping.

```python
def test_converts_basic_novel_metadata_with_stable_identity():
    result = convert_source(parsed({
        "bookSourceName": "看书君",
        "bookSourceGroup": "youchen",
        "bookSourceType": 0,
        "bookSourceUrl": "https://m.example.com/",
        "enabled": True,
    }))
    self.assertEqual("看书君", result.rule["name"])
    self.assertEqual("novel", result.rule["contentType"])
    self.assertEqual("https://m.example.com", result.rule["host"])
    self.assertRegex(result.rule["id"], r"^legado-[0-9a-f]{16}$")
```

- [x] **Step 2: Run metadata tests and verify RED**

Expected: import failure for the missing converter module.

- [x] **Step 3: Implement metadata and identity conversion**

Use SHA-256 over canonical `bookSourceName + "\n" + bookSourceUrl`, truncated to 16 lowercase hex characters. Sanitize file stems without discarding Unicode letters/numbers; normalize separators and cap the stem length.

Implement the tested Legado-to-Ikan content-type table. Unknown values produce `conversion.content_type` and use `mixed` only as an explicit candidate fallback.

- [x] **Step 4: Write failing URL and request tests**

Cover:

- `/search?q={{key}}&page={{page}}` → `/search?q=$keyword&page=$page`;
- supported page arithmetic;
- `url,{"method":"POST","body":"searchkey={{key}}"}` → an Ikan `@js:` request object;
- static headers and request/response encoding;
- unsupported Legado template expressions yielding diagnostics instead of fabricated output.

- [x] **Step 5: Implement URL template and request conversion**

Parse request suffixes structurally with `json.JSONDecoder`, not comma splitting. Generate compact deterministic JavaScript request objects with direct `keyword`, `page`, `result`, and `host` variables. Preserve ordinary templates when a request object is unnecessary.

- [x] **Step 6: Write failing selector conversion tests**

Cover common CSS class/tag/index shorthand, XPath, JSONPath, current-node `text/href/src`, `&&`, `||`, simple `##` replacement, and unsupported constructs.

- [x] **Step 7: Implement conservative selector conversion**

Convert only recognized grammar. Return no executable candidate for unknown operators and add `conversion.selector_unsupported` with the original field path.

- [x] **Step 8: Run primitive tests and verify GREEN**

Run the full primitive test file and the existing validator tests.

- [x] **Step 9: Commit Task 3**

```bash
git add .agents/skills/writing-ikan-rules/scripts/legado_converter/converter.py .agents/skills/writing-ikan-rules/tests/test_legado_converter_primitives.py
git commit -m "feat: convert legado rule primitives"
```

---

### Task 4: Stage Mapping, Discovery, Signing, and JavaScript Degradation

**Files:**
- Modify: `.agents/skills/writing-ikan-rules/scripts/legado_converter/converter.py`
- Create: `.agents/skills/writing-ikan-rules/tests/fixtures/legado_static_novel.json`
- Create: `.agents/skills/writing-ikan-rules/tests/fixtures/legado_dynamic_discover.json`
- Create: `.agents/skills/writing-ikan-rules/tests/test_legado_converter_stages.py`

**Interfaces:**
- Extend `convert_source` to fill search/discover/chapter/content Ikan fields and `converted_stages`/`disabled_stages`.
- Define deterministic diagnostic codes for incomplete stages and unsupported scripts.

- [x] **Step 1: Write failing static-stage tests**

Use a minimal HTML source and a minimal JSON API source. Assert complete mappings for:

```text
ruleSearch.bookList -> searchList
ruleSearch.name -> searchName
ruleSearch.bookUrl -> searchResult
ruleExplore.bookList -> discoverList
ruleToc.chapterList -> chapterList
ruleToc.chapterName -> chapterName
ruleToc.chapterUrl -> chapterResult
ruleContent.content -> contentItems
```

Also cover optional author, cover, status, latest chapter, intro, and tags fields.

- [x] **Step 2: Run static-stage tests and verify RED**

Expected: required stage fields are absent or stages are not classified.

- [x] **Step 3: Implement stage mapping and disablement policy**

Search and discovery require address, list, name, and result; disable them when conversion cannot produce that set. Chapter/content remain in the candidate and record `conversion.chapter_incomplete` or `conversion.content_incomplete` when required fields are absent.

- [x] **Step 4: Write failing discovery tests**

Cover:

- a JSON array encoded in `exploreUrl` with title rows and static category entries;
- category addresses containing `{{page}}`;
- a recognized generated independent category list;
- a normalized multi-row filter fixture converted to `@@DiscoverRule`;
- a combined signed filter returning nested `@js:apiRequest(...)` with literal `${page}`;
- an opaque dynamic discovery script being disabled and reported.

- [x] **Step 5: Implement discovery conversion**

Skip empty heading rows as requests while using them as the current channel name. Emit `channel::title::address` for independent categories. Generate `@@DiscoverRule` only from structurally recognized filter definitions with exact keys. Use nested `@js:` for recognized page-sensitive signing helpers.

- [x] **Step 6: Write failing JavaScript and crypto degradation tests**

Cover compatible `jsLib` functions, `java.md5Encode` rewriting to `CryptoJS.MD5`, Base64 helpers, recognized AES, unresolved `java.ajax`, `JavaImporter`, `Packages.*`, source variables, login APIs, and browser/UI calls.

- [x] **Step 7: Implement safe JavaScript rewrites**

Apply exact token/AST-light rewrites only to tested forms. Set `useCryptoJS: true` when generated fields or `loadJs` use CryptoJS. If unsupported runtime symbols remain, omit the executable fragment and add a diagnostic with a redacted excerpt.

- [x] **Step 8: Run stage tests and verify GREEN**

Run stage, primitive, parser, scanner, and existing validator tests.

- [x] **Step 9: Commit Task 4**

```bash
git add .agents/skills/writing-ikan-rules/scripts/legado_converter/converter.py .agents/skills/writing-ikan-rules/tests/fixtures .agents/skills/writing-ikan-rules/tests/test_legado_converter_stages.py
git commit -m "feat: convert legado rule stages"
```

---

### Task 5: Validation Integration, Batch Report, and CLI

**Files:**
- Create: `.agents/skills/writing-ikan-rules/scripts/convert_legado_rules.py`
- Modify: `.agents/skills/writing-ikan-rules/scripts/legado_converter/models.py`
- Create: `.agents/skills/writing-ikan-rules/tests/test_convert_legado_rules_cli.py`

**Interfaces:**
- CLI: `convert_legado_rules.py INPUT --output OUTPUT_DIR`.
- Produce `run_conversion(input_path: Path, output_dir: Path) -> BatchResult` for direct tests.
- Write deterministic, UTF-8, pretty-printed JSON with `ensure_ascii=False` and trailing newline.

- [x] **Step 1: Write failing batch/validator tests**

Create a temporary input containing one complete source, one partial source, and one malformed/non-object entry. Assert continuation, deterministic output paths, one plain object per rule file, validator issue serialization, and summary counts.

- [x] **Step 2: Run batch tests and verify RED**

Expected: CLI module and `run_conversion` do not exist.

- [x] **Step 3: Implement validator loading and report serialization**

Load sibling `validate_rule.py` by file path using `importlib.util`, call `validate_document`, and serialize each issue as `{level, field, message}`. Do not duplicate validation logic.

Calculate status after validation:

```python
if not meaningful_reading_flow:
    status = "unsupported"
elif diagnostics_or_validation_errors_or_disabled_requested_stage:
    status = "partial"
else:
    status = "converted"
```

- [x] **Step 4: Implement safe output writing**

Create the explicit output directory if needed. Write individual files atomically through a temporary file in that directory followed by `Path.replace`. Never delete unrelated files. Resolve same-batch name collisions deterministically.

- [x] **Step 5: Write failing CLI exit-code tests**

Invoke the script with `subprocess.run` and assert codes `0`, `2`, and `1`, plus compact stdout summaries and useful stderr for batch-level failure.

- [x] **Step 6: Implement CLI argument handling and exit codes**

Use `argparse`. Catch expected input/output errors at the top level, print one concise error, and return `1`. Return `2` whenever any processed source is partial/unsupported or any input diagnostic has error severity.

- [x] **Step 7: Run CLI tests and verify GREEN**

Run all converter tests and existing validator tests.

- [x] **Step 8: Commit Task 5**

```bash
git add .agents/skills/writing-ikan-rules/scripts/convert_legado_rules.py .agents/skills/writing-ikan-rules/scripts/legado_converter/models.py .agents/skills/writing-ikan-rules/tests/test_convert_legado_rules_cli.py
git commit -m "feat: add legado batch conversion cli"
```

---

### Task 6: Skill Documentation and Acceptance Verification

**Files:**
- Modify: `.agents/skills/writing-ikan-rules/SKILL.md`
- Create: `.agents/skills/writing-ikan-rules/tests/fixtures/legado_mixed_batch.txt`
- Create: `.agents/skills/writing-ikan-rules/tests/test_legado_converter_acceptance.py`

**Interfaces:**
- Document the CLI command, offline-only guarantee, report statuses, and the rule that converted output is not live verification.
- Acceptance test invokes the public CLI contract only.

- [x] **Step 1: Write failing acceptance test**

Use a sanitized comma-separated fixture containing a basic HTML source, a static JSON API source, and a source with unsupported Java/Android code. Assert three output candidates, accurate converted/partial summary counts, valid JSON report schema, and no secret literals in report excerpts.

- [x] **Step 2: Run acceptance test and verify RED**

Expected: fail until all public CLI/report behavior is integrated.

- [x] **Step 3: Add concise skill usage documentation**

Add a “Batch conversion from Legado” section with:

```bash
python3 .agents/skills/writing-ikan-rules/scripts/convert_legado_rules.py INPUT --output OUTPUT_DIR
```

State that status `converted` means deterministic offline conversion plus static validation only. Require live stage checks before describing a rule as operational.

- [x] **Step 4: Run full automated verification**

```bash
python3 -m unittest discover -s .agents/skills/writing-ikan-rules/tests -p 'test_*.py'
python3 /Users/hucheng/.codex/skills/.system/skill-creator/scripts/quick_validate.py .agents/skills/writing-ikan-rules
python3 .agents/skills/writing-ikan-rules/scripts/validate_rule.py rules/qimao.json
git diff --check
```

Expected: all tests pass, the skill is valid, the existing 七猫 rule has zero errors/warnings, and no whitespace errors are reported.

- [x] **Step 5: Smoke-test the supplied sample batches without network access**

Run the CLI separately against both supplied attachment files into temporary directories. Confirm all structurally parseable sources receive report records, partial/unsupported sources do not abort later entries, and no input JavaScript is executed.

- [x] **Step 6: Commit Task 6**

```bash
git add .agents/skills/writing-ikan-rules/SKILL.md .agents/skills/writing-ikan-rules/tests/fixtures/legado_mixed_batch.txt .agents/skills/writing-ikan-rules/tests/test_legado_converter_acceptance.py
git commit -m "docs: document legado batch conversion"
```
