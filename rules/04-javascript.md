# JavaScript 规则

JavaScript 用于选择器无法表达的计算、动态地址、签名、数据整形和自定义字节变换。当前移动端使用 QuickJS 运行规则脚本。

## 基本写法

```javascript
@js:
(() => {
  return result.trim();
})()
```

异步代码：

```javascript
@js:
(async () => {
  const values = await css(result, ".item@text");
  return values;
})()
```

JS 规则可返回：

- `string` / `number` / `boolean`
- `null`
- JSON 对象
- 数组（包含上述值）
- Promise，包括 `async` IIFE 的结果

地址字段只接受 URL 字符串、请求对象或 `null`。发现 `discoverUrl` 的 JS 可以返回字符串、列表或请求对象。漫画 `contentItems` 可以返回图片 URL 或结构化图片对象。

## 保留全局变量

每次执行前，应用会更新以下变量：

| 变量 | 含义 |
| --- | --- |
| `result` | 当前输入。地址规则中通常是上游结果；取值规则中是当前响应或当前链式值。 |
| `lastResult` | 上游阶段的结果。例如正文解析时可用于保留章节入口。 |
| `baseUrl` | 当前页完整地址。 |
| `host` | 规则的 `host`。 |
| `page` | 当前页码，从 1 开始。 |
| `pageSize` | 当前页大小上下文。 |
| `cookie` | 规则 Cookie 上下文。 |
| `keyword` | 搜索词；非搜索阶段通常是空字符串。 |

注意：

- JS 中写 `keyword`、`page`、`result`，不写 `$keyword`、`$page`、`$result`。
- 不要自行覆盖这些保留名称作为持久全局状态，它们会在下次执行前刷新。
- `result` 的类型取决于执行位置，可能是字符串、JSON、数组或字节数组。需要时先用 `Array.isArray(result)` 或 `typeof result` 判断。

## 链式 JS 与独立 JS

### 链式 JS：逐值执行

```javascript
img@data-src@js:({ url: result, headers: { Referer: host } })
```

CSS 先得到图片 URL 列表，JS 对每个 URL 执行一次，每次 `result` 是单个字符串。

### 独立 JS：自行获取列表

```javascript
@js:
(async () => {
  const urls = await css(result, "img@data-src");
  return urls.map(url => ({ url }));
})()
```

此时 JS 只执行一次，`result` 是当前整个页面响应。

### JS 后继续解析

旧版规则允许在 JS 后继续追加 JSONPath、CSS 或 XPath，新版同样保留这种多阶段执行：

```javascript
@js:
const jsonText = decodePayload(result);
jsonText
@json:$..url
```

这里不是把 `@json:` 当作 JavaScript。引擎会先执行前面的 JS，再把其返回值作为
下一阶段的 `result`。因此 JS 必须返回后续分析器能够读取的字符串、对象或列表。

## 选择器 API

```javascript
const titles = await css(result, ".title@text");
const links = await xpath(result, "//a/@href");
const names = await jsonpath(result, "$.data.items[*].name");
```

| API | 返回 |
| --- | --- |
| `css(input, rule)` | `Promise<Array<string>>` |
| `xpath(input, rule)` | `Promise<Array<string>>` |
| `jsonpath(input, rule)` | `Promise<Array<string>>` |

这些 API 是异步的，必须 `await`。错误写法：

```javascript
const title = css(result, ".title@text").join("");
```

正确写法：

```javascript
const title = (await css(result, ".title@text")).join("");
```

## HTTP API

```javascript
const text = await http.get("/api/data");
const text2 = await http.post("/api/search", {q: keyword}, {Referer: host});
const response = await http.request({
  url: "/api/data",
  method: "GET",
  headers: {Referer: host},
  encoding: "gbk"
});
const bytes = await httpByte("/binary/file", {Referer: host});
```

API 详细返回值见 [地址与请求](02-address-and-request.md#js-中发请求)。

## `loadJs`

`loadJs` 在一个规则执行会话初始化时执行一次，适合放公共函数：

```json
"loadJs": "function normalizeTitle(value) {\n  return String(value).replace(/\\s+/g, ' ').trim();\n}\nfunction buildSign(value) {\n  return CryptoJS.MD5(value).toString();\n}"
```

其他字段直接调用：

```javascript
@js:normalizeTitle(result)
```

约定：

- `loadJs` 中只定义函数和必要常量，不要在初始化阶段发送与当前页相关的请求。
- 共享全局变量只在同一显式规则流/会话内可见，不同规则不共享 JS 全局对象。
- 搜索、发现和作品详情流各自拥有受管理的会话；作品的目录与正文会显式共享同一作品流会话。
- 会话离开对应流程后会释放，不能当作永久数据库。

## CryptoJS

两种方式可启用：

```json
"useCryptoJS": true
```

或在规则中直接使用 `CryptoJS`。常见用法：

```javascript
const md5 = CryptoJS.MD5(result).toString();
const sha256 = CryptoJS.SHA256(result).toString();
const base64 = CryptoJS.enc.Base64.stringify(CryptoJS.enc.Utf8.parse(result));
```

对漫画图片的标准 AES-CBC/ECB 解密，不建议在 JS 里手动跨桥传递大量字节，请使用 [原生 AES 图片变换](06-images-and-transforms.md#原生-aes解密推荐)。

## 命名 JS 图片处理器

这是专门的图片字节变换约定，不是普通选择器 JS。在 `loadJs` 中定义具名函数：

```javascript
function decodeImage(context) {
  const bytes = new Uint8Array(context.bytes);
  // 按站点算法修改 bytes
  return {
    bytes: Array.from(bytes),
    mimeType: "image/webp"
  };
}
```

`contentItems` 只返回函数名和参数：

```javascript
img@data-src@js:({
  url: result,
  transform: {
    type: "js",
    handler: "decodeImage",
    args: {version: 1}
  }
})
```

完整约定见 [命名 JavaScript 图片变换](06-images-and-transforms.md#命名-javascript-图片变换)。

## 安全和资源限制

- 默认 JS 执行超时约 5 秒。超时后该运行时会被终止，不继续在后台运行。
- 内存、栈、桥调用次数和未完成 Promise 数量都有上限。
- 不提供文件系统读取能力。
- 禁止相对路径、绝对路径、`file:`、HTTP/HTTPS 和动态外部模块导入。
- 不要依赖计时器或脱离当前 Promise 的后台任务。

## 常见 JS 错误

### `ReferenceError: content is not defined`

变量只在声明它的块内有效：

```javascript
// 错误
if (title) {
  let content = await css(result, "a@href");
}
return content;
```

```javascript
// 正确
let content;
if (title) {
  content = await css(result, "a@href");
} else {
  content = await css(result, "html");
}
return content;
```

### `TypeError: not a function`

通常是：

- 没有 `await css(...)`；
- 调用了未在 `loadJs` 定义的函数；
- 把 `httpByte` 返回的字节数组当成 `{bytes: ...}` 对象。

### `Unexpected token '<'`

通常不是 JS 源码有 `<`，而是把 HTML 响应传给了 `JSON.parse`。先检查 HTTP 状态、响应内容和是否被验证/登录页重定向。
