# 常见错误与排查

规则的错误应按执行阶段排查，而不是一看到“加载失败”就反复改选择器。一条数据链通常是：

```text
地址评估 → HTTP/WebView 请求 → 响应解码 → 列表选择 → 字段取值 → 分页/下一阶段
```

## 先做的五项检查

1. `host` 是否是纯 URL，而不是 Markdown 链接。
2. 地址请求最终是否到了预期页面，有没有被重定向到登录、验证或 404 页。
3. `*List` 是否能找到节点。
4. 在单个节点内，`*Name` 和 `*Result` 是否都非空。引擎会丢弃名称或 URL 为空的项。
5. 相对 URL 是否应当相对当前页，而不是简单字符串拼接 `host`。

## 发现分类显示 JS 源码或 `${theme.name}`

原因通常是 `discoverUrl` 没有先进入 JS 执行，或者规则并非真正以 `@js:` 开头。

检查：

- `@js:` 前是否只有空白；
- 是否误写成 `@js` / `@JS ` / 全角冒号；
- JS 最终是否返回 `频道::分类::URL` 字符串或列表；
- 字符串内是否误使用并未定义的 `theme`。

当前分类顺序是：`@@DiscoverRule:` → 开头 `@js:` → legacy `::`。

## `FormatException: Unexpected character ... (async() => {`

这意味着 JavaScript 源码被送进了 JSON 解析器，而不是 JS 运行时。

常见原因：

- 字段不支持 JS，却直接放了 JS 源码；
- 应该写 `@js:` 却遗漏了前缀；
- 调用方把 JS 返回的对象又字符串化/二次解析了。

## `Converting object to an encodable object failed: Instance of 'Element'`

表示 HTML `Element` 对象被直接送入 JSON 边界。跨 JS 边界应传字符串、数组或 JSON 对象，不传 Dart/HTML DOM 对象。

优先使用：

```javascript
const html = (await css(result, "article@outerHtml"))[0];
```

或在 JS 之前用 `@text` / `@html` / `@outerHtml` / `@href` 把节点变成字符串。

## `ReferenceError: 'xxx' is not defined`

先检查 JS 作用域：

```javascript
if (condition) {
  let content = "...";
}
return content; // content 在这里不存在
```

将变量声明移到 `if` 外。如果是函数不存在，检查 `loadJs` 是否成功初始化，函数名大小写是否一致。

## `TypeError: not a function`

常见原因：

- 忘记 `await css(...)`，对 Promise 调用 `.join()` / `.map()`；
- 调用未定义的 `loadJs` 函数；
- 把 `httpByte` 返回的数组当作 `{bytes}` 对象；
- 链式 JS 中 `result` 是单字符串，却对它调用了只适用数组的业务函数。

## `SyntaxError: unexpected token '<'`

常见于：

```javascript
JSON.parse(result)
```

但 `result` 实际是 `<!DOCTYPE html>` 开头的错误页/登录页。检查请求 URL、HTTP 状态、Cookie、Referer、User-Agent 和 `fetchMode`。

## HTTP 404 地址里出现 `%40js%3A...`

这表示一整段 `@js:` 被当成 URL 字符串并进行了 URL 编码。

检查：

- JS 是否写在地址字段（如 `contentNextUrl`）而不是普通属性字段；
- 是否真正以 `@js:` 开头；
- 当前应用是否使用已支持该地址 JS 的新规则引擎版本。

## 列表匹配不到，但旧版可以

例如：

```text
.newbook_list&&.articlegeneral
```

当前支持 `&&` 并集。仍无结果时：

1. 检查当前响应是否真的包含这两类节点。
2. 检查是否拿到桌面版页面而规则是移动版选择器，或反之。
3. 检查 User-Agent、Cookie 和重定向后的最终 URL。
4. 分别单独测试 `.newbook_list` 和 `.articlegeneral`。

## 有列表节点，但页面仍说没有内容

作品列表项需要 `name` 和 `result` 同时有效；章节项需要 `chapterName` 和 `chapterResult` 同时有效。

单独测试：

```text
searchList -> 应有 N 个节点
对第一个节点执行 searchName -> 非空
对第一个节点执行 searchResult -> 非空
```

目录同理。

## `chapterUrl` 留空后没有章节

`chapterUrl` 留空会正常继承作品详情地址。没有章节通常不是因为留空，而是：

- `searchResult` / `discoverResult` 指向的不是目录页；
- `chapterList` 是错误页面结构；
- 章节在异步 API 或另一个 URL，这时需要填 `chapterUrl`；
- 页面需要 WebView 渲染或登录会话。

## 目录分页一直加载

目录只要 `chapterNextUrl` 返回新且未访问的 URL 就会继续。如果使用纯 `$page` 模板，而服务器对超大页码仍返回重复页，URL 一直不同，引擎不能从 URL 判断已结束。

推荐从页面中取真实下一页链接：

```json
"chapterNextUrl": ".next@href"
```

最后一页没有 `.next` 时自然停止。

## `paginationCycle`

表示下一页请求的 method + URL + body 与已请求页完全相同。检查 `$page` 是否真正参与 URL/body 计算，或下一页选择器是否错取了当前页链接。

## 请求超时，返回详情页再点却成功

超时是请求失败，不是规则语法错误。跨章翻页和详情页点击必须使用同一规则会话和可重试的章节内容提供者。

规则作者仍应检查：

- 站点是否有限速；
- Referer/Cookie/User-Agent 是否在跨章请求中保留；
- JS 是否有超过 5 秒的等待或无限循环。

## 中文乱码

乱码发生在响应解码阶段，与 CSS/XPath 无关。

处理顺序：

1. 检查 HTTP `Content-Type` charset。
2. 检查 HTML `<meta charset="gbk">` 或 XML encoding。
3. 在结构化请求中明确写 `responseEncoding: "gbk"`。
4. 如果搜索词也要 GBK，再写 `requestEncoding: "gbk"`。

不要只写 legacy `encoding: "gbk"` 就假设响应一定按 GBK 解码；它是请求编码别名。

## 图片显示“加载失败”

分三层检查：

1. URL 提取：`contentItems` 是否返回正确 URL 或 `{url,...}`。
2. 图片请求：是否需要 Referer、User-Agent、Cookie，HTTP 状态是否成功。
3. 处理/解码：普通图片字节是否真正是图片；AES key/iv/mode/padding 是否正确；命名 JS 是否返回有效字节和 MIME。

### `Bad GBK encoding 0x...`

这不是 AES 语法错误，而是密文在解密前进入了文本解码。使用结构化 `{url, transform}` 后，图片解析器会要求 binary 响应。完整排查见 [图片请求与变换](06-images-and-transforms.md)。

### AES 后仍无法显示

- key 是 UTF-8 文本还是 hex/base64？
- key 解码后是否为 16/24/32 字节？
- CBC IV 是否为 16 字节？
- 站点是 PKCS7 还是无 padding？
- 密文是否包含自定义头部/前缀，需要先删除？如需要自定义前处理，改用命名 JS。

## WebView 报不支持 POST/body

这是明确约束，不是网络问题。`fetchMode: webview` 只支持 GET 导航。如果某个搜索必须 POST，需要：

- 将整条规则改为 `fetchMode: http`，并通过 HTTP Cookie/请求头满足站点；或
- 使用站点提供的 GET 搜索入口。

不要使用 `@webview:` 企图切换单个地址，该前缀不支持。

## 如何判断是规则问题还是站点问题

- 相同 URL 在当前 User-Agent/Cookie 下也无法访问：先解决网站/网络/验证。
- 请求成功且响应内有目标内容，但 `*List` 为空：选择器问题。
- `*List` 有元素，但所有项被丢弃：`*Name` 或 `*Result` 问题。
- 地址中出现整段 JS 或 `%40js`：地址评估阶段问题。
- JS stack trace 指向 `analyzer.js`：查看 JS 行号、作用域、Promise 和返回类型。
- 图片 URL 可访问但图片解码失败：检查它是否是加密密文、HTML 防盗链响应或 MIME 错误。

