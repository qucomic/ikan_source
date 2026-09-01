# 完整规则示例

下面示例是结构完整、可导入的 JSON 模板。`example.com` 是占位域名，选择器也是演示结构，必须根据目标站点修改才能获取真实内容。

## 示例一：最小小说规则

```json
{
  "id": "guide-basic-novel",
  "name": "手册示例小说",
  "author": "Ikan",
  "host": "https://www.example.com",
  "contentType": 1,
  "enabled": true,
  "enableSearch": true,
  "searchUrl": "/search?q=$keyword&page=$page",
  "searchNextUrl": "a.next@href",
  "searchList": ".book-list .book-item",
  "searchName": ".title>a@text",
  "searchCover": ".cover@src",
  "searchAuthor": ".author@text",
  "searchDescription": ".description@text",
  "searchResult": ".title>a@href",
  "enableDiscover": true,
  "discoverUrl": "分类::全部::/list/$page\n分类::玄幻::/sort/1/$page\n排行::热门::/top/hot/$page",
  "discoverNextUrl": "a.next@href",
  "discoverList": ".book-list .book-item",
  "discoverName": ".title>a@text",
  "discoverCover": ".cover@src",
  "discoverAuthor": ".author@text",
  "discoverDescription": ".description@text",
  "discoverResult": ".title>a@href",
  "enableMultiRoads": false,
  "chapterList": ".chapter-list li",
  "chapterName": "a@text",
  "chapterResult": "a@href",
  "contentItems": "#content@text"
}
```

说明：

- `chapterUrl` 留空，目录直接请求 `searchResult` / `discoverResult` 得到的详情页。
- `contentUrl` 留空，正文直接请求 `chapterResult`。
- `searchNextUrl` / `discoverNextUrl` 从当前响应提取真实下一页链接。

## 示例二：POST + GBK + JavaScript 小说

```json
{
  "id": "guide-gbk-js-novel",
  "name": "手册示例 GBK 小说",
  "host": "https://www.example.com",
  "contentType": "novel",
  "userAgent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile Safari/604.1",
  "useCryptoJS": true,
  "loadJs": "function cleanTitle(value) { return String(value).replace(/\\s+/g, ' ').trim(); }\nfunction requestSign(value) { return CryptoJS.MD5(value).toString(); }",
  "enableSearch": true,
  "searchUrl": "@js:\n(() => {\n  const ts = String(Date.now());\n  return {\n    url: '/modules/article/search.php',\n    method: 'post',\n    headers: {\n      'Referer': host,\n      'X-Sign': requestSign(keyword + ts)\n    },\n    body: {searchkey: keyword, page: page, ts: ts},\n    requestEncoding: 'gbk',\n    responseEncoding: 'gbk'\n  };\n})()",
  "searchList": ".searchresult>p",
  "searchName": "a@text@js:cleanTitle(result)",
  "searchAuthor": ".author>a@text",
  "searchResult": ">a:nth-child(1)@href",
  "enableDiscover": false,
  "chapterList": "#chapter-list li",
  "chapterName": "a@text",
  "chapterResult": "a@href",
  "contentNextUrl": "@js:\n(() => {\n  const links = result.match(/href=\"([^\"]+)\"[^>]*>下一页/);\n  return links ? links[1] : null;\n})()",
  "contentItems": "#content@html"
}
```

关键点：

- JS 地址对象同时区分 `requestEncoding` 和 `responseEncoding`。
- `loadJs` 函数在会话初始化时注入，其他 JS 可直接调用。
- `a@text@js:cleanTitle(result)` 是链式 JS，对每个标题分别清理。
- `contentNextUrl` 的 `result` 是当前正文分页 HTML。

## 示例三：普通漫画与图片请求头

```json
{
  "id": "guide-basic-manga",
  "name": "手册示例漫画",
  "host": "https://www.example.com",
  "contentType": 0,
  "userAgent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile Safari/604.1",
  "enableSearch": true,
  "searchUrl": "/search?keyword=$keyword&page=$page",
  "searchList": ".manga-card",
  "searchName": ".name@text",
  "searchCover": "img@src@js:({url: result, headers: {Referer: host}})",
  "searchAuthor": ".author@text",
  "searchResult": "a@href",
  "enableDiscover": true,
  "discoverUrl": "分类::全部::/manga/$page",
  "discoverList": ".manga-card",
  "discoverName": ".name@text",
  "discoverCover": "img@src@js:({url: result, headers: {Referer: host}})",
  "discoverAuthor": ".author@text",
  "discoverResult": "a@href",
  "chapterList": "#detail-list-select>li",
  "chapterName": "a@text",
  "chapterCover": "img.chapter-cover@src@js:({url: result, headers: {Referer: host}})",
  "chapterResult": "a@href",
  "contentItems": ".content-img@data-src@js:\n({\n  url: result,\n  headers: {\n    'Referer': host,\n    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile Safari/604.1'\n  }\n})"
}
```

`searchCover`、`discoverCover`、`chapterCover` 和 `contentItems` 使用同一个 `{url, headers}` 格式。封面取第一个有效资源；`contentItems` 先取所有 `data-src`，然后对每个 URL 返回独立图片对象。

## 示例四：原生 AES-CBC 漫画

```json
{
  "id": "guide-aes-manga",
  "name": "手册示例 AES 漫画",
  "host": "https://www.example.com",
  "contentType": "manga",
  "enableSearch": true,
  "searchUrl": "/search?q=$keyword",
  "searchList": ".manga-card",
  "searchName": ".name@text",
  "searchCover": ".cover@data-src@js:\n({\n  url: result,\n  headers: {Referer: host},\n  transform: {\n    type: 'aes',\n    mode: 'cbc',\n    key: 'my2ecret782ecret',\n    iv: 'my2ecret782ecret',\n    padding: 'pkcs7',\n    outputMime: 'image/webp'\n  }\n})",
  "searchResult": "a@href",
  "enableDiscover": false,
  "chapterList": "#detail-list-select>li",
  "chapterName": "a@text",
  "chapterResult": "a@href",
  "contentItems": ".content-img@data-r-src@js:\n({\n  url: result,\n  headers: {\n    'Referer': host,\n    'User-Agent': 'Mozilla/5.0 ...'\n  },\n  transform: {\n    type: 'aes',\n    mode: 'cbc',\n    key: 'my2ecret782ecret',\n    iv: 'my2ecret782ecret',\n    keyEncoding: 'utf8',\n    ivEncoding: 'utf8',\n    padding: 'pkcs7',\n    outputMime: 'image/webp'\n  }\n})"
}
```

这种写法中：

- 应用自己下载图片密文；
- 响应强制按二进制处理；
- 应用原生执行 AES-CBC/PKCS7；
- JS 不传输大量密文，也不需要 `CryptoJS`。
- 同一 AES 对象既可用于封面，也可用于漫画正文图片。

## 示例五：命名 JS 字节变换

```json
{
  "id": "guide-custom-image-manga",
  "name": "手册示例自定义图片处理",
  "host": "https://www.example.com",
  "contentType": 0,
  "loadJs": "function decodeImage(context) {\n  const bytes = new Uint8Array(context.bytes);\n  const key = context.args.xorKey;\n  for (let i = 0; i < bytes.length; i++) {\n    bytes[i] = bytes[i] ^ key;\n  }\n  return {bytes: Array.from(bytes), mimeType: 'image/webp'};\n}",
  "enableSearch": false,
  "enableDiscover": false,
  "chapterList": ".chapter-list li",
  "chapterName": "a@text",
  "chapterResult": "a@href",
  "contentItems": ".content-img@data-src@js:\n({\n  url: result,\n  headers: {Referer: host},\n  transform: {\n    type: 'js',\n    handler: 'decodeImage',\n    args: {xorKey: 23}\n  }\n})"
}
```

这是示意算法。真实规则应将 `decodeImage` 替换为站点实际的纯字节变换。

命名 JS 封面也直接引用同一 handler，例如：

```javascript
.cover@data-src@js:
({
  url: result,
  headers: {Referer: host},
  transform: {
    type: "js",
    handler: "decodeImage",
    args: {xorKey: 23}
  }
})
```

`decodeImage` 必须定义在 `loadJs` 中。收藏恢复时会重新执行 `loadJs`，但不会恢复搜索阶段临时创建的全局变量，所以必要参数必须放在 `args`。

## 示例六：发现瀑布流

`discoverUrl` 字段的内容：

```javascript
@js:
({
  url: `${host}/booklist?${params.join("&")}`,
  headers: {Referer: host}
})
@@DiscoverRule:
{
  "rules": [
    {
      "name": "分类",
      "key": "category",
      "option": "全部",
      "value": "0",
      "options": [
        {"option": "全部", "value": "0"},
        {"option": "玄幻", "value": "1"},
        {"option": "都市", "value": "2"}
      ]
    },
    {
      "name": "状态",
      "key": "status",
      "option": "全部",
      "value": "0",
      "options": [
        {"option": "全部", "value": "0"},
        {"option": "连载", "value": "1"},
        {"option": "完结", "value": "2"}
      ]
    }
  ]
}
```

在 JSON 中使用时，需要将换行和双引号正确转义；在应用的多行规则编辑器中可直接粘贴上述内容。

## 从简单到复杂的编写顺序

1. 先只写 `host + searchUrl + searchList + searchName + searchResult`，确认列表成功。
2. 加上封面、作者、状态和简介。
3. 写目录三件套 `chapterList + chapterName + chapterResult`。
4. 写 `contentItems`，先保证单页正文成功。
5. 最后加分页、POST、GBK、JS、WebView 或图片变换。

这样每次只引入一个新变量，出错时更容易判断是请求、列表还是字段规则的问题。
