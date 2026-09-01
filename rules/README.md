# 规则手册总览

规则是一个 JSON 对象。它不保存内容，而是保存获取内容的方法：地址、请求方式、列表节点、字段选择器、分页链接和必要的 JavaScript。

## 从页面到内容的四个阶段

| 阶段 | 地址字段 | 列表字段 | 关键输出 |
| --- | --- | --- | --- |
| 搜索 | `searchUrl` | `searchList` | `searchName` + `searchResult` |
| 发现 | `discoverUrl` | `discoverList` | `discoverName` + `discoverResult` |
| 目录 | `chapterUrl` | `chapterList` | `chapterName` + `chapterResult` |
| 正文 | `contentUrl` | 无单独列表字段 | `contentItems` |

前一阶段的结果会成为后一阶段的输入：

- 搜索/发现的 `*Result` 是作品详情地址。
- 目录阶段可在 `chapterUrl` 中使用该地址；`chapterUrl` 留空则直接请求它。
- `chapterResult` 是每个章节节点解析出的章节结果，可以是地址、ID 或供 `contentUrl` 使用的结构化字符串。
- `chapterPayload` 可从当前章节节点提取已经随目录响应返回的正文原始数据。
- `chapterPayload` 有有效结果时不发送正文请求，`contentItems` 直接解析该结果；否则正文阶段使用 `contentUrl`，其留空时请求 `chapterResult`。

## 三类规则表达式

### 1. 地址规则

用在 `searchUrl`、`chapterUrl`、`contentUrl` 等字段，返回 URL、请求对象或跳过请求。

```text
/search?q=$keyword&page=$page
```

```javascript
@js:
({
  url: "/search",
  method: "post",
  body: { q: keyword, page },
  headers: { "X-Client": "ikan" }
})
```

详见 [地址与请求规则](02-address-and-request.md)。

### 2. 取元素规则

用在 `searchList`、`discoverList`、`chapterList` 等列表字段，返回元素或 JSON 节点列表。

```text
.book-list > li
//ul[@id="chapter-list"]/li
$.data.items[*]
```

### 3. 取值规则

用在 `searchName`、`chapterResult`、`contentItems` 等字段，返回文字、属性、HTML、URL、列表或结构化对象。

```text
.title@text
a@href
#content@html
$.data.name
```

详见 [选择器与取值](03-selectors-and-values.md)。

## 选择器是相对谁执行的

- `searchList` / `discoverList` / `chapterList` 相对整个响应执行。
- `searchName`、`searchAuthor`、`searchResult` 等相对当前 `searchList` 元素执行。
- `discover*` 字段相对当前 `discoverList` 元素执行。
- `chapterName`、`chapterResult`、`chapterPayload`、`chapterLock` 相对当前 `chapterList` 元素执行；`chapterResult` 与 `chapterPayload` 至少填写一个。
- `contentItems` 相对正文请求响应执行；存在 `chapterPayload` 时则相对其结果执行。
- 选择器后链式的 `@js:` 相对前一阶段返回的每个值分别执行。

## 学习路线

- 刚开始写规则：[字段字典](01-fields.md) → [选择器](03-selectors-and-values.md) → [完整示例](07-examples.md)。
- 需要 POST、请求头或 GBK：[地址与请求](02-address-and-request.md)。
- 需要计算、解密或 API 组装：[JavaScript 规则](04-javascript.md)。
- 搜索/目录/正文有下一页：[分页与会话](05-pagination-and-session.md)。
- 漫画图片需要 Referer 或 AES 解密：[图片与变换](06-images-and-transforms.md)。
- 已经出错：[常见错误与排查](08-troubleshooting.md)。

## 推荐写法与兼容写法

文档使用两种标记：

- **推荐**：当前类型化规则引擎的清晰写法，例如结构化请求对象、结构化图片对象。
- **旧版兼容**：为导入 ESO/Ikan 旧规则保留的写法，例如 `@headers{...}` 图片后缀、`searchKey`、`searchPage`。新规则可以使用，但不建议继续扩展这类字符串协议。
