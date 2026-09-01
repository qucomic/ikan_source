# 图片请求、Base64/AES 解码与命名 JS

`discoverCover`、`searchCover`、`chapterCover` 和漫画 `contentItems` 使用同一套图片资源协议。它们可以返回普通图片 URL，也可以返回结构化图片资源。结构化资源将“图片地址”、“该图片独立请求头”和“下载后的字节变换”分开表达。

## 适用字段与结果数量

| 字段 | 结果用法 |
| --- | --- |
| `discoverCover` | 当前发现作品的第一个有效图片资源 |
| `searchCover` | 当前搜索作品的第一个有效图片资源 |
| `chapterCover` | 当前章节的第一个有效图片资源 |
| 漫画 `contentItems` | 全部图片资源，按规则返回顺序显示 |

四个字段都支持以下五种形式：

1. 普通 URL 字符串；
2. `{url, headers}`；
3. `{url, headers, transform: {type: "base64", ...}}`；
4. `{url, headers, transform: {type: "aes", ...}}`；
5. `{url, headers, transform: {type: "js", handler, args}}`。

链式规则（例如 `img@src@js:...`）会对每个选择器结果单独执行 JavaScript，因此其中的 `result` 是单个 URL。封面字段最终取第一个有效对象，漫画正文保留全部对象。

## 处理流程

1. 图片字段从当前作品节点、章节节点或正文响应提取图片 URL。
2. 将相对 URL 相对当前字段所在的响应页归一化。
3. 应用使用图片对象的 `headers` 下载原始字节。
4. 下载明确按 **binary** 处理，不进入 UTF-8/GBK 文本解码。
5. 执行 `transform`：无处理、原生 Base64、原生 AES 或命名 JS。
6. 将处理后字节作为图片解码并显示。

这个顺序很重要。加密图片字节是随机二进制，如果在 AES 之前按 GBK 或 UTF-8 解码，会出现 `Bad GBK encoding 0x...` 或数据损坏。

## 处理结果缓存

带 `transform` 的图片首次显示时需要下载原始响应并执行 Base64、AES 或命名 JS 处理。处理成功后的最终图片字节会进入共享内存缓存和图片磁盘缓存，因此发现页、搜索页、详情页、章节封面与漫画阅读页可以复用同一结果，不会因为切换页面再次下载和解码。

缓存键包含规则 ID、规则修改时间、`loadJs` 内容以及完整图片资源（URL、headers、transform 和 args）。修改规则或处理函数后会自动使用新缓存键。处理失败的结果不会缓存，点击重试仍会重新请求。应用中的“清理图片缓存”和“清理全部缓存”会同时清除这类最终图片缓存。

## 普通图片

```json
"contentItems": ".content-img@src"
```

CSS 返回多个 `src` 时，`contentItems` 的最终结果是图片列表。

封面的普通写法相同：

```json
"discoverCover": ".cover@src",
"searchCover": ".cover@src",
"chapterCover": ".chapter-cover@src"
```

## 图片独立请求头

**推荐：结构化对象**

```javascript
.manga-img@src@js:
({
  url: result,
  headers: {
    "Referer": host,
    "User-Agent": "Mozilla/5.0 ..."
  }
})
```

链式 JS 对每个 `src` 分别执行，此时 `result` 是单个 URL。

对象格式：

```javascript
{
  url: "https://img.example.com/1.webp",
  headers: {
    Referer: "https://www.example.com/"
  }
}
```

**旧版兼容：`@headers` 字符串后缀**

```javascript
img@src@js:
result + "@headers" + JSON.stringify({
  "Referer": host,
  "User-Agent": "Mozilla/5.0 ..."
})
```

新规则不建议再使用该字符串协议，因为对象更容易验证和扩展。

同一对象可直接用于封面。例如搜索封面需要独立 Referer：

```javascript
.cover@data-src@js:
({
  url: result,
  headers: { Referer: host }
})
```

## 原生 Base64 解码（推荐）

如果图片地址返回的响应体不是图片二进制，而是没有
`data:image/...;base64,` 前缀的 Base64 文本，请使用原生 `base64`
变换。它在 Dart 层直接解码，不启动 QJS，也不会跨 JS 桥传递整张图片：

```javascript
$.id@js:
({
  url: `https://c2.2thewash.com/comic/${result}/cover.jpg`,
  headers: {
    "Referer": host
  },
  transform: {
    type: "base64",
    outputMime: "image/jpeg"
  }
})
```

漫画正文使用相同写法：

```javascript
.content-img@data-r-src@js:
({
  url: result,
  headers: { "Referer": host },
  transform: {
    type: "base64",
    outputMime: "image/jpeg"
  }
})
```

`base64` 变换会忽略响应文本中的空白字符，也接受完整的 Base64 data
URL。`outputMime` 可省略，此时应用会优先读取 data URL 中的 MIME，再根据解码后的图片字节识别格式。

不要再为这种资源编写 `decodeBase64Image` 命名 JS。命名 JS 适合自定义字节算法，单纯 Base64 解码使用它会产生明显的序列化和内存开销。

## 原生 AES 解密（推荐）

标准 AES-CBC/ECB 不需要 CryptoJS 和 `httpByte`。返回：

```javascript
.content-img@data-r-src@js:
({
  url: result,
  headers: {
    "Referer": host,
    "User-Agent": "Mozilla/5.0 ..."
  },
  transform: {
    type: "aes",
    mode: "cbc",
    key: "my2ecret782ecret",
    iv: "my2ecret782ecret",
    keyEncoding: "utf8",
    ivEncoding: "utf8",
    padding: "pkcs7",
    outputMime: "image/webp"
  }
})
```

### AES 参数

| 参数 | 允许值 | 说明 |
| --- | --- | --- |
| `type` | `aes` | 必填 |
| `mode` | `cbc` / `ecb` | 默认 `cbc` |
| `key` | String | 必填，解码后必须为 16、24 或 32 字节 |
| `iv` | String | CBC 必填，解码后必须为 16 字节；ECB 可省略 |
| `keyEncoding` | `utf8` / `hex` / `base64` | 默认 `utf8` |
| `ivEncoding` | `utf8` / `hex` / `base64` | 默认跟随 `keyEncoding` |
| `padding` | `pkcs7` / `none` | 默认 `pkcs7` |
| `outputMime` | MIME String | 推荐明确写 `image/webp`、`image/jpeg` 或 `image/png` |

注意：

- 密文长度必须是 AES block size（16 字节）的倍数。
- `pkcs7` 会验证并删除末尾 padding；key/iv 错误常会表现为 padding 无效或解密后不是图片。
- 不要把密文先转字符串，也不要让 JS 返回密文文本。

### 整段 JS 生成图片对象列表

```javascript
@js:
(async () => {
  const urls = await css(result, ".content-img@data-r-src");
  return urls.map(url => ({
    url,
    headers: { Referer: host },
    transform: {
      type: "aes",
      mode: "cbc",
      key: "my2ecret782ecret",
      iv: "my2ecret782ecret",
      padding: "pkcs7",
      outputMime: "image/webp"
    }
  }));
})()
```

## 命名 JavaScript 图片变换

只在原生 AES 不能表达站点算法时使用，例如字节乱序、按版本切块、XOR 或多阶段处理。

### 1. 在 `loadJs` 定义具名函数

```javascript
function decodeMangaImage(context) {
  const bytes = new Uint8Array(context.bytes);
  const key = context.args.xorKey;

  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = bytes[i] ^ key;
  }

  return {
    bytes: Array.from(bytes),
    mimeType: "image/webp"
  };
}
```

### 2. 图片字段引用函数名

```javascript
.content-img@data-src@js:
({
  url: result,
  headers: { Referer: host },
  transform: {
    type: "js",
    handler: "decodeMangaImage",
    args: { xorKey: 23 }
  }
})
```

`handler` 必须是合法 JavaScript 标识符，且必须能在 `globalThis` 上找到函数。不能把一整段 JS 源码写入 `handler`。

同样的 `transform` 对象可以由 `discoverCover`、`searchCover` 或 `chapterCover` 返回，不需要另一套封面语法。

### `context` 参数

| 字段 | 内容 |
| --- | --- |
| `context.url` | 当前图片绝对 URL |
| `context.bytes` | 应用已下载的原始字节数组 |
| `context.response.status` | HTTP 状态码 |
| `context.response.url` | 最终响应 URL |
| `context.response.headers` | 响应头对象 |
| `context.response.mimeType` | 响应 MIME，可能为 `null` 或不准确 |
| `context.args` | `transform.args` 中的 JSON 参数 |

函数可返回：

- `Array<number>`，每个数必须在 0...255；
- `Uint8Array`；
- data URL，例如 `data:image/webp;base64,...`；
- `{bytes, mimeType}` 或 `{data, mimeType}`。

**推荐返回 `{bytes: Array.from(bytes), mimeType: "image/webp"}`。**

命名图片处理器不需要调用 `httpByte`。网络请求、请求头、二进制传输、失败重试和缓存都由应用处理。

### 会话与持久化约定

- `handler` 必须定义在规则的 `loadJs` 中，不能只在某次搜索或发现的临时 JS 中定义。
- 处理所需的动态配置必须写入 `transform.args`，不要依赖搜索/发现阶段临时写入的全局变量。
- 图片命名 JS 使用图片专属会话，不复用发现、搜索、详情或正文解析会话；页面切换不会提前释放正在工作的图片会话。
- 收藏会保存完整的 URL、headers 和 transform；旧收藏只有 URL 时仍可读取。
- 重新创建会话后只保证 `loadJs` 中的 handler 和持久化的 `transform.args` 可用，不保证之前流程中的临时全局状态仍存在。

## 错误写法对照

### 在 `contentItems` 中拼“二次 JS”字符串

```javascript
// 不推荐/不是结构化图片协议
return `${url}@js:(async () => { ... })()`;
```

应改为 `{url, transform}` 对象。

### 误解 `httpByte` 返回值

```javascript
// 错误：httpByte 直接返回字节数组，不是 {bytes: ...}
const res = await httpByte(result);
const bytes = new Uint8Array(res.bytes);
```

```javascript
// API 本身的正确类型，但图片变换仍建议用 transform
const bytes = new Uint8Array(await httpByte(result));
```

### `Bad GBK encoding 0x...`

这表示加密二进制被错误当作文本解码。结构化图片 `transform` 会强制使用 binary 响应，因此请确认：

- `contentType` 是 `0` / `manga`；
- `contentItems` 真正返回了 `{url, transform}`，而不是对象的字符串化结果；
- 应用已重新编译/重启，使用了包含 binary 请求契约的新代码。

## 调试 AES 的建议顺序

1. 先保存一份服务器返回的原始密文文件。
2. 在桌面工具中用同一 key/iv/mode/padding 解密，确认能得到有效 PNG/JPEG/WebP。
3. 根据 key/iv 真实表示选择 `utf8`、`hex` 或 `base64`。
4. 检查图片请求是否需要 Referer/User-Agent/Cookie。
5. 最后再检查 `outputMime`。MIME 错误通常不会改变解密字节，但会影响解码和缓存。
