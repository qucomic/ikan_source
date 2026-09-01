# 地址与请求规则

地址规则用在 `searchUrl`、`searchNextUrl`、`discoverNextUrl`、`chapterUrl`、`contentUrl` 和部分分页场景。它的任务不只是返回一个 URL，还可以描述 method、headers、body 和编码。

## 普通 URL 模板

最简单的地址就是字符串：

```text
/search?q=$keyword&page=$page
```

支持的模板变量：

| 推荐写法 | 兼容写法 | 含义 |
| --- | --- | --- |
| `$keyword` | `${keyword}`、`{{key}}`、`searchKey` | 搜索词 |
| `$page` | `${page}`、`{{page}}`、`searchPage` | 当前页码，从 1 开始 |
| `$pageSize` | `${pageSize}` | 页大小上下文，当前规则流通常为 20 |
| `$result` | `${result}` | 上游结果，例如详情地址或章节地址 |
| `$lastResult` | `${lastResult}` | 地址模板中与上游结果对应 |
| `$host` | `${host}`、`{{host}}` | 规则 `host` |
| `$baseUrl` | `${baseUrl}` | 当前页地址 |

模板只替换一次。如果 `keyword` 本身是字符串 `$page`，它不会再被当作页码变量继续替换。

### 相对 URL

```text
../page/2.html
/book/123
//cdn.example.com/cover.jpg
```

- `/book/123` 相对当前域名解析。
- `../page/2.html` 相对当前页目录解析。
- `//cdn...` 是协议相对地址，图片资源会按 HTTPS 归一化；页面地址建议直接写完整 `https://`。

## 结构化请求对象

**推荐**在需要 POST、请求头或编码时返回对象：

```javascript
@js:
(() => {
  return {
    url: "/api/search",
    method: "post",
    headers: {
      "Referer": host,
      "X-Requested-With": "XMLHttpRequest"
    },
    body: {
      keyword: keyword,
      page: page
    },
    requestEncoding: "utf-8",
    responseEncoding: "utf-8"
  };
})()
```

| 属性 | 类型 | 说明 |
| --- | --- | --- |
| `url` | String | 必填。可以是相对 URL。 |
| `method` | String | 默认 `GET`，会转为大写。 |
| `headers` | Object | 键值将转为字符串，header 名按不区分大小写处理。 |
| `body` | String/Object/List/JSON 标量 | 请求体。字符串按文本发送，其他值作为 JSON 数据保存。 |
| `requestEncoding` | String | URL/请求体编码，支持 UTF-8 和 GBK 系列。 |
| `encoding` | String | **旧版兼容**：`requestEncoding` 的别名，不等于响应解码。 |
| `responseEncoding` | String | 强制响应文本解码，如 `gbk`。 |
| `skip` | bool | `true` 表示显式跳过当前请求。 |

JavaScript 返回的 URL 字符串或对象不会再执行 `$page` / `${keyword}` 模板替换。在 JS 里应当直接用模板字符串计算：

```javascript
@js:`/search?q=${encodeURIComponent(keyword)}&page=${page}`
```

## 静态 JSON 请求对象

不用 JavaScript 也可以在地址字段中写 JSON 字符串：

```json
{
  "url": "/api/search?q=${keyword}",
  "method": "post",
  "headers": {"Content-Type": "application/json"},
  "body": {"keyword": "${keyword}", "page": "${page}"}
}
```

静态 JSON 中的字符串会递归执行 legacy 模板替换；JS 返回对象不会。

## 跳过请求

以下返回值会创建“跳过请求”：

```javascript
@js:null
```

```javascript
@js:({ skip: true })
```

```javascript
@js:({ url: null })
```

空规则 `""` 与返回 `null` 的含义不完全相同：字段留空通常表示使用流程默认地址；显式 `null` 表示不发送请求。

## GBK 请求与响应

```javascript
@js:
({
  url: `/search.php?key=${keyword}`,
  method: "post",
  body: { searchkey: keyword },
  requestEncoding: "gbk",
  responseEncoding: "gbk"
})
```

- `requestEncoding: "gbk"` 用于中文 URL 参数和请求体编码。
- GBK 下的对象 body 会按 `application/x-www-form-urlencoded; charset=gbk` 发送。
- `responseEncoding: "gbk"` 用于响应解码。不填时应用会依次参考 HTTP charset、HTML/XML charset 声明、UTF-8 有效性，最后尝试 GBK。
- **旧版 `encoding: "gbk"` 只映射为请求编码**。如果响应也必须 GBK，请明确写 `responseEncoding`。

## WebView 模式

规则顶层写：

```json
"fetchMode": "webview"
```

此模式使用可视浏览器会话加载页面，返回渲染后 HTML，适合需要 JavaScript 渲染、登录 Cookie 或站点验证的 GET 页面。

约束：

- 只支持 GET 导航。
- 不支持带 body 的请求。
- 不会在 WebView 无法表达 POST 时偷偷回退到 HTTP，因为那会丢失已验证的浏览器会话。
- 不要写 `@webview:`。当前地址评估器明确拒绝 `@webview:`、`@web:`、`@http:` 和 `@hetu:` 前缀。

## Cookie 与登录会话

- HTTP 响应中的 `Set-Cookie` 会进入规则会话。
- Cookie 按规则、域名、路径和 Secure 约束隔离，不会发送到无关域名。
- WebView 会话保留浏览器 Cookie 和验证状态。
- JS 中的 `http.*` 也经过同一受控请求层，不是独立的无状态网络库。

## JS 中发请求

```javascript
const text = await http.get("/api/list");
const posted = await http.post("/api/search", { q: keyword }, {
  "X-Requested-With": "XMLHttpRequest"
});
const response = await http.request({
  url: "/api/detail",
  method: "GET",
  headers: { "Referer": host },
  encoding: "gbk"
});
```

- `http(url)` / `http.get(...)` / `http.post(...)` / `http.put(...)` / `http.delete(...)` 返回响应文本。
- `http.request(options)` 返回 `{status, url, headers, body, bytes}`。
- `httpByte(url, headers)` 返回字节数组。普通规则尽量不用它自行处理图片，图片解密应使用 [结构化图片变换](06-images-and-transforms.md)。

## 常见错误

- `url` 没加引号：`var url = https://...` 不是合法 JS，应写 `var url = "https://..."`。
- 把 Markdown 链接当 URL：`[https://a.com](https://a.com)` 不是合法 `host`，必须只保留 `https://a.com`。
- 在 JS 里写 `$keyword`：JS 变量是 `keyword`，`$keyword` 只属于普通地址模板。
- 把地址规则的 `@js:` 源码当 URL：这通常说明该字段没有进入地址评估流程，或误把页内选择器写到地址字段。

