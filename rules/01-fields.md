# 规则字段字典

本页按执行阶段列出当前 `Rule` 模型的字段。空字符串通常表示不启用该能力或使用上游默认值。

## 基本字段

| 字段 | 类型 | 作用 |
| --- | --- | --- |
| `id` | String | 规则唯一标识，必填。同 ID 导入时可能覆盖现有规则。 |
| `name` | String | 规则显示名称，必填。 |
| `author` | String | 规则作者。 |
| `host` | String | 站点根地址，也是相对 URL 的基础之一。建议写完整 `https://...`。 |
| `icon` | String | 规则图标 URL，可以是相对地址。 |
| `group` | String | 规则分组。 |
| `contentType` | int/String | 内容类型，见下表。 |
| `enabled` | bool | 规则是否启用，默认 `true`。 |
| `createTime` | int | 创建时间元数据。 |
| `modifiedTime` | int | 修改时间元数据。 |
| `sort` | int | 首次导入时的默认顺序，沿用旧版语义：数值越大越靠前。导入后顺序由用户在规则管理页置顶或拖动调整，重复导入和订阅更新不会覆盖本地顺序。 |
| `viewStyle` | int | 首次导入时的默认显示样式。用户在应用内调整后，重复导入和订阅更新不会覆盖本地选择。 |
| `postScript` | String | 备注/兼容元数据；当前不作为主解析流程的后置脚本执行。 |
| `subscriptionId` | String | 规则所属订阅的内部关联值。 |
| `editProtection` | Object | 规则编辑保护信息，应由应用生成，不建议手写。 |

### `contentType`

| 数字 | 字符串 | 内容 |
| --- | --- | --- |
| `0` | `manga` / `漫画` / `图片` | 漫画图片 |
| `1` | `novel` / `文字` | 小说 |
| `2` | `video` / `视频` | 视频 |
| `3` | `audio` / `音频` | 音频 |
| `4` | `rss` | RSS |
| `5` | `mixed` / `图文` | 混合内容 |

## 全局请求与 JavaScript

| 字段 | 作用 |
| --- | --- |
| `userAgent` | 该规则 HTTP 请求的 User-Agent。 |
| `cookies` | 规则预置 Cookie 字符串，同时作为 JS 的 `cookie` 全局变量。响应 Cookie 会按规则和域名维护会话。 |
| `loginUrl` | 登录入口地址。 |
| `fetchMode` | `http` 或 `webview`。`webview` 用浏览器会话获取渲染后 HTML，可保留验证/Cookie。 |
| `useCryptoJS` | 为 `true` 时预加载内置 CryptoJS。常见可执行字段中出现 `CryptoJS` 时也会自动检测，但新规则只要依赖 CryptoJS 就应明确设为 `true`。 |
| `loadJs` | 当规则会话初始化时执行一次的 JS，用于定义公共函数和常量。 |

`fetchMode: webview` 当前只支持 GET 导航，不支持带 body 的 POST/PUT 请求。详见 [WebView 模式](02-address-and-request.md#webview-模式)。

## 搜索字段

| 字段 | 作用 |
| --- | --- |
| `enableSearch` | 是否启用搜索，默认 `true`。 |
| `searchUrl` | 首页搜索地址规则，常用 `keyword` 和 `page`。 |
| `searchNextUrl` | 搜索下一页。可以是页面中的链接选择器，也可以是地址模板。 |
| `searchList` | 从搜索响应中取作品节点列表。 |
| `searchName` | 作品名称，必要。 |
| `searchResult` | 作品详情页地址，必要。 |
| `searchTags` | 标签列表。 |
| `searchCover` | 搜索封面。可返回普通 URL、`URL + headers` 对象、原生 AES 或命名 JS 图片资源。 |
| `searchAuthor` | 作者。 |
| `searchStatus` | 连载/完结等状态。 |
| `searchChapter` | 最新章节名。 |
| `searchDescription` | 简介。 |

## 发现字段

`discover*` 的取值规则与同名 `search*` 字段一致。

| 字段 | 作用 |
| --- | --- |
| `enableDiscover` | 是否启用发现，默认 `true`。 |
| `discoverUrl` | 发现分类与地址规则，支持 legacy `::`、`@js:`、`@@DiscoverRule:` 单组组合筛选，以及 `@@DiscoverRule:` + `groups` 分组组合筛选。 |
| `discoverNextUrl` | 发现下一页链接选择器或地址模板。 |
| `discoverList` | 作品节点列表。 |
| `discoverName` | 作品名称，必要。 |
| `discoverResult` | 作品详情页地址，必要。 |
| `discoverTags` | 标签列表。 |
| `discoverCover` | 发现封面。与 `searchCover` 使用同一图片资源协议。 |
| `discoverAuthor` | 作者。 |
| `discoverStatus` | 状态。 |
| `discoverChapter` | 最新章节名。 |
| `discoverDescription` | 简介。 |

### `discoverUrl` 的 legacy 格式

```text
频道::分类::URL
```

```text
分类::全部::/list/$page
分类::玄幻::/sort/1_$page/
排行::总榜::/top/allvisit_$page/
```

两段格式 `频道::URL` 也可用，此时分类名默认为“全部”。多条用换行或 legacy `&&` 分隔。

## 目录字段

| 字段 | 作用 |
| --- | --- |
| `enableMultiRoads` | 是否启用多线路目录。 |
| `chapterUrl` | 目录页地址。留空时直接使用作品详情地址。 |
| `chapterNextUrl` | 目录下一页选择器或地址模板。 |
| `chapterList` | 章节节点列表。 |
| `chapterName` | 章节名称，必要。 |
| `chapterResult` | 章节结果。可以返回地址、ID 或供 `contentUrl` 使用的结构化字符串；与 `chapterPayload` 至少填写一个。 |
| `chapterPayload` | 章节内嵌数据。用于目录响应已经包含正文、图片列表或播放信息的情况；与 `chapterResult` 至少填写一个。 |
| `chapterLock` | 章节锁定状态字符串。 |
| `chapterRoads` | 多线路节点列表。 |
| `chapterRoadName` | 当前线路名称。 |
| `chapterCover` | 章节封面。与搜索/发现封面、漫画正文图片使用同一图片资源协议。 |
| `chapterTime` | 保留/兼容字段；当前主目录映射不消费该值。 |

开启多线路时，先用 `chapterRoads` 得到每条线路，再在当前线路内执行 `chapterRoadName` 和章节规则。

## 正文字段

| 字段 | 作用 |
| --- | --- |
| `contentUrl` | 正文请求地址。仅在 `chapterPayload` 没有有效结果时执行；留空则直接使用 `chapterResult`。返回 `null` 或 `{skip:true}` 可跳过请求。 |
| `contentNextUrl` | 正文内部下一页地址，用于同一章被分成多个网页的情况。 |
| `contentItems` | 小说返回文字列表，漫画返回图片 URL/图片对象，视频返回播放地址。 |

正文输入按以下顺序决定：

1. `chapterPayload` 有有效结果：跳过正文请求，以该结果作为 `contentItems` 的 `result`；
2. 否则 `contentUrl` 非空：执行正文请求；
3. 否则请求 `chapterResult`，保持旧规则兼容。

## 已废弃字段

旧规则中的 `enableUpload`、`searchItems`、`discoverItems` 和
`chapterItems` 会在导入时被静默忽略，新规则导出时也不会包含这些键。
请分别使用 `searchList`、`discoverList` 和 `chapterList` 描述节点列表。

内嵌正文示例：

```json
{
  "chapterList": "$.chapters.*",
  "chapterName": "$.title",
  "chapterResult": "$.id",
  "chapterPayload": "$.payload",
  "contentItems": "$.content"
}
```

正文阶段的变量约定：`result` 是 `chapterPayload` 的结果，`lastResult` 是
`chapterResult`，`baseUrl` 是产生该章节的目录页地址。`chapterPayload` 只提供解析输入，
不会覆盖或改写 `contentItems` 规则。

当 `chapterResult` 为空而 `chapterPayload` 有值时，应用会使用 payload 的稳定字符串作为
兼容章节结果，因此正文阶段的 `lastResult` 也可读取该字符串。建议 payload 很大时仍额外
提供一个简短、稳定且唯一的 `chapterResult`，便于阅读记录和缓存索引。

`searchCover`、`discoverCover`、`chapterCover` 和漫画 `contentItems` 的图片对象格式完全一致，均支持：

- 普通 URL；
- `{url, headers}` 独立请求头；
- `{url, headers, transform: {type: "aes", ...}}` 原生 AES；
- `{url, headers, transform: {type: "js", handler, args}}` 命名 JS。

封面字段只取规则结果中的第一个有效图片资源；漫画 `contentItems` 则保留全部图片资源及顺序。完整格式见 [图片请求、AES 解密与命名 JS](06-images-and-transforms.md)。

## 字段继承要点

- `chapterUrl == ""` 不是错误：目录默认继承作品详情地址。
- `contentUrl == ""` 不是错误：正文默认继承章节地址。
- 地址规则中的 `result` 指当前流程的上游地址；取值规则中的 `result` 指当前响应或当前选中值。
