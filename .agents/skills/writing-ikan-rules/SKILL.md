---
name: writing-ikan-rules
description: Use when creating, updating, reviewing, or debugging ordinary JSON source rules for the Ikan app, including novel, manga, video, search, discover, chapter, content, request, selector, JavaScript, image-transform, or author-ad fields. Do not use for ikan:// subscription encoding.
---

# Writing Ikan Rules

Create one ordinary JSON rule object for the current Ikan engine. Never encode it as `ikan://` or wrap it in a subscription array.

## Workflow

1. Establish the target URL, content type, stages, author, and optional advertising URL. If responses are unavailable, request representative HTML/JSON; never invent selectors or endpoints.
2. Read only the repository references relevant to the task:
   - Start with [`rules/README.md`](../../../rules/README.md) and [`rules/01-fields.md`](../../../rules/01-fields.md).
   - For requests, selectors, or JavaScript, read [`02-address-and-request.md`](../../../rules/02-address-and-request.md), [`03-selectors-and-values.md`](../../../rules/03-selectors-and-values.md), or [`04-javascript.md`](../../../rules/04-javascript.md).
   - Read pagination, images, examples, or troubleshooting references only when those features apply. For combined discover filters, read [`05-pagination-and-session.md`](../../../rules/05-pagination-and-session.md) before drafting `discoverUrl`.
3. For client-rendered or hash-route pages, inspect page scripts and network requests before choosing a fetch mode. Use an accessible underlying HTTP/JSON API when available, including reproducing required signing or encryption with `@js:`/`loadJs`. Use `webview` only when browser state, login, verification, or an unusable API makes direct HTTP impractical; then verify the captured HTML contains the target nodes after asynchronous rendering.
4. Map the flow: search/discover result → directory request → chapter result/payload → content. In the directory response, check whether chapters are partitioned into independent source, route, quality, or play-line containers before deciding `enableMultiRoads`.
5. Draft the smallest rule that supports the requested stages. Set unused search or discover stages explicitly to `false`.
6. Save or present a JSON object, then run:

   ```bash
   python3 .agents/skills/writing-ikan-rules/scripts/validate_rule.py path/to/rule.json
   ```

7. Fix every error. Explain remaining warnings. Deliver the rule with assumptions and a stage test checklist.

## Batch conversion from Legado

For multiple Legado/阅读 source objects, use the offline converter instead of manually rewriting every item:

```bash
python3 .agents/skills/writing-ikan-rules/scripts/convert_legado_rules.py INPUT --output OUTPUT_DIR
```

`INPUT` may be one JSON object, a JSON array, a comma-separated object stream without outer brackets, or a directory containing `.json`/`.txt` files. The converter writes one ordinary Ikan JSON object per source plus `conversion-report.json`.

Report statuses mean:

- `converted`: deterministic offline conversion completed and the static Ikan validator found no errors;
- `partial`: a meaningful reading flow was generated, but one or more requested stages or runtime capabilities need manual work;
- `unsupported`: no complete chapter-to-content reading flow could be generated.

The converter never executes source JavaScript or performs network requests. `converted` is not proof that a website or API currently works; verify search, every discovery mode, directory, content, pagination, headers, authentication, and encryption against real responses before describing the rule as operational. Use the report's field-level diagnostics to finish `partial` candidates manually with this skill.

For Legado CSS/JSoup selectors, preserve semantics instead of copying delimiters:

- Legado `@` between selector nodes means a descendant step. Convert `.r@ul@li` to `.r ul li`; do not use `>` because the next node need not be a direct child. Ikan does not accept `.r@ul@li` as CSS.
- A terminal Legado result index/range such as `a.0`, `li[-1:0]`, or `.item[!0,2]` becomes Ikan's result operation, for example `@css:a@[0]`, `@css:li@[-1:0]`, or `@css:.item@[!0,2]`.
- Preserve terminal readers with Ikan syntax: `#content@ownText` becomes `@css:#content@ownText`, and `#content@p@textNodes` becomes `@css:#content p@textNodes`.
- Preserve top-level Legado `%%` as Ikan's round-robin interleave operator. Do not rewrite it as `&&`.
- Do not use `:nth-of-type(...)` for a terminal Legado result index: it filters by sibling structure and is not equivalent to indexing the complete query result. An index on an intermediate Legado selector step cannot use Ikan's terminal result operation; convert only when the structural form is demonstrably equivalent, otherwise emit a field diagnostic.

## Non-obvious Rules

| Situation | Required form |
| --- | --- |
| Ordinary GET template | Use `$keyword` and `$page`, for example `/search?q=$keyword&page=$page`. |
| POST, body, dynamic headers, or computed URL | Use `@js:` and return a URL or request object. Inside JavaScript use `keyword` and `page` without `$`. |
| Search/discover value fields | Evaluate relative to the current `*List` item. |
| Chapter value fields | Evaluate relative to the current `chapterList` item. |
| Current list node value | When `*List` already selects the target element, use `text`, `href`, `src`, or another field name directly. Use `a@text`/`a@href` only when `a` is a descendant. Leading forms such as `@text` and `@href` are compatibility aliases, not canonical output. |
| Embedded chapter content | Use `chapterPayload`; otherwise let `contentUrl` use `chapterResult`. |
| Multi-road chapters | Set `enableMultiRoads: true` only when the directory contains independent road containers. `chapterRoads` selects each container; `chapterRoadName` and `chapterList` run relative to that container, then chapter value fields run relative to each `chapterList` item. |
| Relative URLs | Prefer engine resolution against the current `baseUrl`/`host`; add JavaScript only when the API requires ID-to-URL construction. |
| Dynamic page | Inspect scripts/network first. Prefer its usable HTTP/JSON API; treat WebView as the fallback and verify post-render DOM timing. |
| Combined discover filters | Use `@@DiscoverRule:` with `rules` or `groups`. Its address expression is a restricted template evaluator, not general JavaScript: build the request directly with `host`, `params.join("&")`, `values`, `page`, and an optional simple request object. |
| Combined filters requiring `loadJs` signing | Let the `@@DiscoverRule` template expand all selected `values` into a string beginning with nested `@js:`. The request evaluator then runs that inner script with the current `page` and the rule execution session, so it can call `apiRequest()` or another `loadJs` helper for every page. |
| Independent dynamic categories with per-page signing | Ordinary `discoverUrl @js:` must return legacy category strings whose address is a nested `@js:` expression, such as `分类::名称::@js:apiRequest(...)`. Preserve `${page}` for the nested evaluation; do not return `{title, url, headers}` objects from the outer script. |
| Author advertising | `adUrl` is an HTTPS URL returning the documented advertising JSON, not an image URL. |
| Images needing headers or transforms | Return structured image objects as documented in `rules/06-images-and-transforms.md`. |
| CSS pseudo-classes | Use the structural pseudo-classes documented in `rules/03-selectors-and-values.md`. Do not assume full browser CSS4 support; the validator rejects unsupported pseudo-classes and pseudo-elements. |
| CSS result operations | Use `@css:selector@[...]@reader`. Operations apply after the complete CSS query; they cannot be inserted between selector steps. |

## Output Contract

- Output valid, pretty-printed JSON with no comments or placeholders.
- Include stable `id`, `name`, `host`, and `contentType`.
- Keep `searchResult` as the work result and `chapterResult` as the chapter result. Build downstream API URLs in `chapterUrl` or `contentUrl` when IDs must be converted.
- Static inspection is not proof of success. List app checks for requests, pagination, selectors, URLs, headers, content order, and authentication.
- For every enabled stage, verify one real `*List` item produces all required value fields; a non-empty list alone does not prove that mapped items survive validation.

### Combined discover contract

When the website allows multiple filter rows to apply together, generate this shape and make each `key` the exact verified query parameter. Preserve bracketed names such as `filter[country]`; do not simplify them to `country`.

```javascript
@js:
`${host}/comics?${params.join("&")}&page=${page}`
@@DiscoverRule:
{"rules":[...]}
```

Use `${values.key}` or `${values['filter[key]']}` when a value must occupy a fixed path or an explicitly encoded parameter. A simple `{url, method, headers, body}` request object is also supported.

If the combined request needs a signing function from `loadJs`, the restricted outer template must return a nested `@js:` address. It expands the selected values first; the normal address evaluator then fills `${page}` and executes the inner script, allowing the helper to return a URL or request object with signed query parameters, headers, or body.

```javascript
@js:
`@js:apiRequest('https://api.example.com', '/books', {sort: '${values.sort}', area: '${values.area}', category: '${values.category}', page: ${page}})`
@@DiscoverRule:
{"rules":[...]}
```

Do not write `apiRequest(...)` directly as the outer expression: the waterfall evaluator does not execute arbitrary JavaScript or initialize `loadJs`. Keep `${page}` literal in the outer result so signing runs again for every page. If neither the direct restricted template nor this nested-address form can represent the request, report the engine limitation.

### Independently selectable dynamic categories

Use this form when discovery is a list of separate categories or tags and each page request must be signed by a function from `loadJs`, such as `apiRequest()`. The outer `@js:` builds category definitions; the nested `@js:` runs later with the selected page and creates the final request object.

```json
"discoverUrl": "@js:(() => { const categories = [{title: '玄幻', id: 1}]; return categories.map(item => `分类::${item.title}::@js:apiRequest('/category', {id: ${item.id}, page: \\${page}})`); })()"
```

The JSON text needs `\\${page}` so the outer JavaScript emits the literal `${page}`. Do not call `apiRequest()` in the outer mapping and return `{title, url, headers}`: ordinary discovery normalizes each map to a request string, does not read its `title` as the category label, and evaluates page-dependent signing while the category map is initialized. This can display every category as the default title and freeze pagination at the initialization page.

### Multi-road chapter contract

Use multi-road mode when one directory response contains two or more independent source, route, quality, language, or playback-line containers, each with its own chapter list. Do not enable it merely because the page has decorative tabs, volume headings, or one flat chapter list.

```json
{
  "enableMultiRoads": true,
  "chapterRoads": ".play-lines .line",
  "chapterRoadName": ".line-title@text",
  "chapterList": ".episodes a",
  "chapterName": "text",
  "chapterResult": "href"
}
```

Evaluate fields in this order and scope:

1. `chapterRoads` runs against the complete directory response and returns one node per road.
2. `chapterRoadName` and `chapterList` run separately against each current road node.
3. `chapterName`, `chapterResult`, `chapterPayload`, `chapterCover`, and `chapterLock` run against each current chapter node.

When `enableMultiRoads` is `true`, always provide both `chapterRoads` and `chapterRoadName`. When it is `false`, omit or empty those two fields. Verify at least two real roads independently produce a non-empty name and valid chapters; matching the first road alone is insufficient.

## Common Mistakes

- Serializing a request object into a plain string instead of returning it from `@js:`.
- Using `${keyword}` in an ordinary address or `$keyword` inside JavaScript.
- Enabling a stage while omitting its URL/list/name/result fields.
- Treating `adUrl` as an image address.
- Guessing selectors from a URL without inspecting a response.
- Writing `@text`/`@href` when the current `*List` item is already the target element; generate `text`/`href` instead.
- Selecting WebView for a dynamic shell before checking its underlying API or confirming that asynchronous target nodes exist in the captured HTML.
- Treating the `@@DiscoverRule:` prelude as full JavaScript and constructing queries with declarations, `filter()`, arbitrary `map()`, `push()`, `encodeURIComponent()`, or a custom `query.join()`. These expressions are not executed by the waterfall template evaluator; use `params.join("&")` or direct `values` substitutions.
- Calling `apiRequest()` or another `loadJs` helper directly in the `@@DiscoverRule` prelude. Return a quoted nested `@js:` address so the request evaluator invokes the helper after expanding the selected values and current page.
- Returning `{title, url, headers}` objects from an ordinary dynamic `discoverUrl` to represent independent categories. Return `分类::名称::@js:...` strings and defer page-sensitive signing to the nested `@js:` address.
- Selecting all chapter links globally while `enableMultiRoads` is true. `chapterList` must be relative to the current `chapterRoads` node so chapters do not leak across roads.
- Enabling multi-road mode for volume headings or visual tabs that do not own independent chapter lists, or leaving `chapterRoads`/`chapterRoadName` populated while multi-road mode is disabled.
- Using browser-only selectors such as `:has(...)`, `:hover`, or `::before`; prefer stable classes/attributes or JavaScript when supported structural pseudo-classes are insufficient.
- Producing an array or `ikan://` value when the user requested an ordinary JSON rule.
