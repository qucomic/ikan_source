# Legado to Ikan Batch Converter Design

## Purpose

Build an offline batch converter that turns Legado source definitions into ordinary Ikan JSON rule files. The converter produces useful candidates at scale, validates every generated rule statically, and reports unsupported behavior without claiming that untested sources work against live websites.

The first release targets the representative patterns in the supplied samples while keeping the conversion pipeline extensible for later website-specific adapters and additional Legado syntax.

## Scope

The converter will:

- accept one Legado object, a standard JSON array, a comma-separated object stream without outer brackets, or a directory containing JSON/TXT inputs;
- continue processing after an individual source fails;
- convert metadata, content type, search, discovery, chapter, content, request, selector, pagination, header, and common JavaScript patterns;
- emit one ordinary Ikan JSON object per source;
- run the existing Ikan rule validator against every generated candidate;
- emit a machine-readable batch report with conversion and validation diagnostics;
- preserve unsupported source fragments in the report rather than presenting them as valid Ikan expressions.

The first release will not:

- make network requests or claim live-stage verification;
- emulate the Legado Android/Java runtime;
- guarantee complete conversion of arbitrary JavaScript;
- implement login UI, interactive WebView actions, CAPTCHA handling, or permanent source-variable storage;
- modify the Ikan engine.

## Architecture

The converter lives inside the `writing-ikan-rules` skill and uses only the Python standard library.

```text
.agents/skills/writing-ikan-rules/
  scripts/
    convert_legado_rules.py
    legado_converter/
      __init__.py
      input_parser.py
      capability_scanner.py
      converter.py
      models.py
  tests/
    fixtures/
    test_convert_legado_rules.py
```

Responsibilities are separated as follows:

- `convert_legado_rules.py` parses CLI arguments, invokes the pipeline, writes outputs, prints the summary, and selects the process exit code.
- `input_parser.py` reads supported input shapes and attaches an input location to every parsed source.
- `capability_scanner.py` identifies syntax and runtime dependencies before conversion.
- `converter.py` normalizes Legado fields and emits Ikan rule candidates stage by stage.
- `models.py` defines conversion status, structured diagnostics, source locations, and serialized report records.
- The existing `scripts/validate_rule.py` remains the single static Ikan validation implementation.

## Processing Model

```text
input files
  -> tolerant parsing
  -> capability scan
  -> normalized conversion state
  -> stage conversion
  -> Ikan validation
  -> rule files and conversion-report.json
```

Each parsed source is isolated. A malformed or unsupported source records a diagnostic and does not stop later sources.

The converter uses an internal normalized state rather than rewriting the input dictionary in place. It records the source field behind each generated Ikan field so diagnostics can identify the exact original location.

## Input Handling

Accepted file forms:

1. A single JSON object.
2. A JSON array of objects.
3. Top-level objects separated by commas, with no outer brackets and with an optional trailing comma.
4. A directory, processed in deterministic path order, containing `.json` and `.txt` files.

The tolerant parser must remain structural. It will use JSON decoding boundaries and must not split on textual `},{`, because that sequence may appear inside JavaScript strings.

Non-object entries produce an input diagnostic and are skipped. Duplicate sources are not silently merged.

## Output Layout and Identity

The CLI receives an output directory. It writes:

```text
output/
  <safe-name>-<stable-hash>.json
  conversion-report.json
```

The safe name is derived from `bookSourceName`. The stable hash is derived from the original source identity, preferring `bookSourceUrl` plus `bookSourceName`, so repeated conversion produces the same file name and distinct sources do not overwrite each other.

Each generated rule receives a deterministic Ikan `id` from the same identity. Unicode display names remain unchanged in the rule itself.

## Capability Scan

The scanner emits structured diagnostics with `code`, `severity`, `field`, `message`, and an optional source excerpt. Initial capability families include:

- ordinary URL templates and legacy request configurations;
- CSS, XPath, JSONPath, regex replacement, template interpolation, and JavaScript chains;
- `java.ajax`, `java.get`, `java.put`, `java.getString`, and hash/encoding helpers;
- `source.getVariable`, `source.setVariable`, and login information access;
- cookies and browser/WebView operations;
- `JavaImporter` and `Packages.*`;
- CryptoJS, MD5, Base64, AES, and Java crypto classes;
- dynamic discovery lists, static discovery JSON, and combined filters;
- virtual or non-URL `bookSourceUrl` values.

Capability detection does not itself claim conversion. The stage converter marks a diagnostic resolved only after a deterministic rewrite is applied.

## Conversion Rules

### Metadata

- Preserve source name, group, enabled state, ordering metadata when representable, and update time.
- Map Legado content types through an explicit tested table to Ikan `contentType` values.
- Derive `host` only from a verified absolute source URL or an absolute request URL. A virtual source name is never emitted as an Ikan host.
- Do not infer an author from comments. A future CLI author override may be added independently; the first release leaves unknown author values empty.

### Address and request rules

- Convert `{{key}}` to `$keyword`, `{{page}}` to `$page`, and supported upstream placeholders to their Ikan equivalents in ordinary templates.
- Convert recognized Legado request configurations into Ikan `@js:` request objects with `url`, `method`, `headers`, `body`, and encoding fields.
- Preserve relative URLs when the generated `host` makes their resolution deterministic.
- Convert page arithmetic only when it matches Ikan-supported arithmetic.
- Do not copy an opaque Legado address script into an Ikan address field unless every used runtime API has a deterministic Ikan mapping.

### Selectors and values

- Map common Legado CSS, XPath, JSONPath, attribute, text, template, replacement, fallback, and merge forms to documented Ikan expressions.
- Normalize current-node readers to canonical `text`, `href`, and `src` forms where their scope is known.
- Keep unknown selector operators out of generated rule fields and record them in the report.

### Search, discovery, chapter, and content stages

- Convert each stage independently and retain source-field provenance.
- Disable search or discovery when its required address or result mappings cannot be converted reliably.
- Convert static independent discovery entries to legacy `channel::category::address` strings.
- Convert recognizable multi-row filters to `@@DiscoverRule` with exact parameter keys.
- For per-page signing, emit nested `@js:` addresses so signing occurs after selected values and the current page are available.
- Map chapter item identifiers through `chapterResult`, building `contentUrl` only when a separate content request is required.
- Use `chapterPayload` when the directory response already embeds content.
- Keep a chapter/content candidate when incomplete, but report validation errors and never mark the source fully converted.

### JavaScript, signing, and crypto

- Move compatible shared helper functions from Legado `jsLib` into Ikan `loadJs` after deterministic runtime API rewrites.
- Rewrite known MD5, Base64, and common AES operations to CryptoJS or documented native image transforms and set `useCryptoJS` when required.
- Rewrite `java.ajax` only when its request and response role can be represented by an Ikan address request or the managed `http` API.
- Treat `JavaImporter`, `Packages.*`, arbitrary Android APIs, UI calls, and unresolved mutable storage as unsupported until an explicit adapter exists.

## Degradation Policy

The converter always distinguishes generated syntax from verified behavior.

- A completely converted source is `converted` only when all enabled stages were deterministically mapped and the generated rule has no static validation errors.
- A usable but incomplete candidate is `partial` when one or more fields or stages require manual work.
- A source is `unsupported` when no meaningful reading flow can be generated.

Unsupported original fragments are stored only in `conversion-report.json`, including their source field and a bounded excerpt. They are not inserted into executable Ikan fields as placeholders.

If search or discovery cannot be converted, its Ikan enable flag is set to `false`. If chapter or content cannot be completed, the candidate is still written, its validation failures are recorded, and its status cannot be `converted`.

## Report Contract

`conversion-report.json` contains batch metadata and one record per source:

```json
{
  "summary": {
    "total": 0,
    "converted": 0,
    "partial": 0,
    "unsupported": 0
  },
  "sources": [
    {
      "name": "Example",
      "input": "sources.txt#2",
      "output": "example-12345678.json",
      "status": "partial",
      "convertedStages": ["search"],
      "disabledStages": ["discover"],
      "diagnostics": [],
      "validation": {
        "errors": [],
        "warnings": []
      }
    }
  ]
}
```

Diagnostics use stable codes so future tooling can group recurring migration problems.

## CLI Contract

Initial interface:

```bash
python3 .agents/skills/writing-ikan-rules/scripts/convert_legado_rules.py INPUT --output OUTPUT_DIR
```

Exit codes:

- `0`: every parsed source is fully converted;
- `2`: processing completed but at least one source is partial or unsupported;
- `1`: no input could be processed, input parsing failed at batch level, or an internal program error occurred.

The CLI prints a compact summary and does not abort the batch for a per-source conversion failure.

## Testing Strategy

Development follows test-driven implementation. Tests use minimal, sanitized fixtures derived from the supplied patterns rather than storing complete third-party rules, credentials, cookies, or large scripts.

Coverage includes:

- all accepted input shapes, including comma-separated objects and a trailing comma;
- deterministic ordering, file naming, IDs, and duplicate-name handling;
- metadata and content-type mapping;
- ordinary GET and POST conversion;
- search, static discovery, dynamic signed discovery, chapter, and content mappings;
- combined filters with nested signed `@js:` addresses;
- known selector conversions and unsupported selector diagnostics;
- capability scanning for login, storage, Java/Android, WebView, and crypto APIs;
- stage disablement and partial/unsupported status calculation;
- validator integration and report serialization;
- CLI exit codes and continuation after one bad source.

No first-release test depends on external network access.

## Security and Data Handling

- The converter never executes source-provided JavaScript.
- It never performs network requests.
- It does not import arbitrary Python modules from input directories.
- Reports use bounded excerpts and must redact obvious authorization, cookie, password, token, and secret values.
- Output directories are explicit and are not deleted or recursively replaced.

## Future Extensions

- Optional live verification as a separate command and report phase.
- Website-specific adapters selected by explicit source fingerprints.
- Additional Legado runtime API rewrites.
- Optional author override and conversion policy configuration.
- A curated compatibility score based on accumulated fixtures and live verification evidence.
