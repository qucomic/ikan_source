# 分页、上下文与会话

规则有四种不同分页：搜索分页、发现分页、章节目录分页和同一章正文分页。它们的输入、触发方式和停止条件不完全相同。

## 搜索分页

### 方式一：`searchUrl` 自带 `$page`

```json
"searchUrl": "/search?q=$keyword&page=$page"
```

`searchNextUrl` 留空时，如果 `searchUrl` 含 `$page` 或 `searchPage`，引擎会在用户请求下一页时重新评估 `searchUrl`。

### 方式二：从当前响应取下一页

```json
"searchNextUrl": "a.next@href"
```

`searchNextUrl` 看起来像 CSS/XPath/JSONPath/JS 规则时，会对当前页响应解析。相对链接以当前搜索页为 `baseUrl` 解析：

```html
<a class="next" href="page-2.html">下一页</a>
```

当前页是 `https://example.com/search/index.html` 时，下一页为 `https://example.com/search/page-2.html`。

如果选择器返回多个值，引擎只使用第一个非空 URL。选择器应精确命中“下一页”，不要同时命中“上一页”等链接。

`searchNextUrl` 的 `@js:` 属于页内取值规则，应返回下一页 URL 字符串，不要返回请求对象。

### 方式三：`searchNextUrl` 是模板

```json
"searchNextUrl": "/search?q=$keyword&page=$page"
```

当它不像选择器时，按地址模板执行。

## 发现分页

发现分页与搜索分页类似：

```text
分类::全部::/list/$page
```

```json
"discoverNextUrl": ".next@href"
```

- `discoverNextUrl` 留空且当前分类 URL 含 `$page` / `searchPage` / `{{page}}` 时，下一页重新评估该分类 URL。
- `discoverNextUrl` 是选择器时，从当前发现响应提取。
- 结构化首页请求可以是 POST，后续页仍可以根据页内链接转为 GET。
- `discoverNextUrl` 的 `@js:` 应返回 URL 字符串，不返回请求对象。

## 发现 `@js:` 分类

`discoverUrl` 以 `@js:` 开头时，会先执行 JS，然后把返回值归一化为分类字符串列表，最后按 legacy `::` 解析：

```javascript
@js:
(() => {
  const categories = [
    ["玄幻", 1],
    ["都市", 2]
  ];
  return categories.map(item =>
    `分类::${item[0]}::/sort/${item[1]}_$page/`
  ).join("\n");
})()
```

允许返回：

- 单个字符串；
- 字符串/对象的嵌套列表；
- 结构化请求对象（将保存为分类的请求值）；
- `null` 表示无分类。

错误的旧行为是在执行 JS 前就对源码按 `::` 拆分。当前分类器先检查 `@@DiscoverRule:`，再检查开头 `@js:`，最后才走 legacy 字符串。

## 新版发现瀑布流 `@@DiscoverRule:`

用多行筛选器生成组合地址：

```javascript
@js:
`${host}/booklist?${params.join("&")}`
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
        {"option": "漫画", "value": "1"}
      ]
    },
    {
      "name": "排序",
      "key": "sort",
      "option": "最新",
      "value": "new",
      "options": [
        {"option": "最新", "value": "new"},
        {"option": "热门", "value": "hot"}
      ]
    }
  ]
}
```

瀑布流地址表达式可使用：

- `host`：规则域名；
- `rules`：当前每一行选中的 `{name,key,option,value}`；
- `values.筛选键`：按 `key` 读取该行当前选中的值，例如
  `values.area`、`values.year`；
- `params`：形如 `key=value` 的参数列表。

可返回 URL 字符串，也可返回带 `url` / `headers` 的请求对象。瀑布流配置 JSON 中 `rules` 也兼容别名 `list`。

瀑布流表达式可以直接使用动态页码。应用会保留分页表达式，在实际发送请求时
按当前页计算，因此 GET URL 和 POST body 都可以自动翻页：

```javascript
`${host}/booklist?category=${values.category}&page=${page}`
```

支持以下分页写法：

- `${page}`、`$page`、`{{page}}`、`searchPage`；
- `${page - 1}`、`${page + 1}`；
- `${page * 20}`、`${(page - 1) * 20}`；
- 受限算术还支持整数、括号及 `+ - * / %`，不会执行任意 JavaScript。

例如从 0 开始并使用偏移量的 POST JSON 接口：

```javascript
({
  url: `${host}${group.api}`,
  method: "post",
  headers: {"Content-Type": "application/json"},
  body: `{
    "channel": "${group.channel}",
    "genre": "${values.genre}",
    "page": ${page - 1},
    "offset": ${(page - 1) * 20},
    "limit": 20
  }`
})
```

`discoverNextUrl` 留空时，只要组合请求中含分页表达式，应用就会复用当前
分组和筛选组合生成下一页完整请求。若网站通过响应返回下一页链接，或下一页
算法无法用页码表达式描述，再填写 `discoverNextUrl`；非空时它仍具有更高优先级。

### 分组组合筛选

当电影、电视剧、动漫等一级频道需要各自独立的组合筛选时，将顶层
`rules` 改为 `groups`。每个分组拥有自己的 `rules`：

```javascript
@js:
({
  url: `${host}${group.path}?${params.join("&")}`,
  headers: {Referer: host}
})
@@DiscoverRule:
{
  "groups": [
    {
      "id": "movie",
      "name": "电影",
      "path": "/vod/movie",
      "rules": [
        {
          "name": "题材",
          "key": "genre",
          "value": "all",
          "options": [
            {"option": "全部", "value": "all"},
            {"option": "动作片", "value": "action"},
            {"option": "喜剧片", "value": "comedy"}
          ]
        },
        {
          "name": "地区",
          "key": "area",
          "value": "all",
          "options": [
            {"option": "全部", "value": "all"},
            {"option": "美国", "value": "usa"},
            {"option": "日本", "value": "japan"}
          ]
        }
      ]
    },
    {
      "id": "anime",
      "name": "动漫",
      "path": "/vod/anime",
      "rules": [
        {
          "name": "类型",
          "key": "type",
          "value": "all",
          "options": [
            {"option": "全部", "value": "all"},
            {"option": "日漫", "value": "jp"},
            {"option": "国漫", "value": "cn"}
          ]
        }
      ]
    }
  ]
}
```

分组表达式除 `host`、`rules`、`params` 外，还可使用：

- `group.id`：当前一级频道的稳定标识；
- `group.name`：当前一级频道显示名称；
- `group.path`：示例中的频道路径；
- `group.自定义字段`：分组对象中除 `rules` / `list` 外的字符串或数值字段。

当网站使用固定位置参数而不是查询参数时，可通过 `values.筛选键` 将选中值
放到对应位置：

```javascript
`${host}/vodshow/${values.type}-${values.area}-${values.sort}------${page}---${values.year}.html`
```

应用会在第一行显示一级频道，只显示当前频道的筛选行，并分别保留每个
频道上次选中的组合。顶层 `rules` 的原有单组写法继续兼容。

## 章节目录分页

```json
"chapterNextUrl": ".right>a@href"
```

目录加载流程：

1. 请求第 1 页。
2. 立即解析并追加当前页章节。
3. 将已加载页数和当前章节列表通知 UI。
4. 用 `chapterNextUrl` 从当前页找下一页。
5. 只要下一页非空且未访问过，就继续。

**章节目录没有固定 20 页上限**。它通过已访问 URL 集合停止循环，并按章节 URL 去重。

如果站点每页及页间都按“最新章节在前”返回，请设置：

```json
"chapterSourceOrder": "desc"
```

应用会保留加载中的来源顺序，待完整目录加载结束后再整体转换为旧到新的规范阅读顺序。
`@css:...@[-1:0]` 只反转一页中的一次选择结果，不能表达跨分页的完整目录倒序。

`chapterNextUrl` 也可以是地址模板：

```json
"chapterNextUrl": "/book/$result/catalog/$page"
```

但如果网站在最后一页仍对任意页码返回不同 URL 的重复内容，纯 `$page` 模板无法自动知道何时结束。优先使用页面真实“下一页”链接。

当 `chapterNextUrl` 是 CSS、XPath、JSONPath 或 `@js:` 取值规则时，它针对当前目录页响应执行；相对链接以当前目录分页地址为 `baseUrl` 解析。返回多个值时只使用第一个非空 URL。

## 正文内部分页

用于“一章被分成 1_2.html、1_3.html”的网站：

普通页面可以直接用 CSS 读取下一页：

```json
"contentNextUrl": "a.next@href"
```

需要根据链接文字或页面结构判断时可以使用 JavaScript：

```json
"contentNextUrl": "@js:\n(() => {\n  const m = result.match(/href=\"([^\"]+)\"[^>]*>下一页/);\n  return m ? m[1] : null;\n})()"
```

CSS、XPath、JSONPath 和 `@js:` 取值规则都针对当前正文分页响应执行。相对链接以当前分页地址为 `baseUrl` 解析；若返回多个值，只使用第一个非空 URL。此处 JS 的 `result` 是当前正文分页的 HTML，`baseUrl` 是当前分页地址，`page` 是即将请求的页码。

当前实现的保护条件：

- `contentNextUrl` 返回 `null` / 空字符串时停止；
- 下一页 URL 与当前 URL 相同时停止；
- 新页 `contentItems` 为空时停止；
- **同一章正文分页当前最多读取 20 页**。这是正文分页的保护上限，不是章节目录分页上限。

## 分页循环检测

搜索和发现流会记录请求签名，签名包括 method、URL 和 body。如果下一页产生完全相同的请求，会报 `paginationCycle`，而不是无限重试。

目录分页使用已访问 URL 停止循环。所以分页规则必须真正产生新的下一页地址。

## `result` 与 `lastResult`

理解原则：

- **地址规则**：`result` 通常是上一阶段的 URL/结果。
- **解析规则**：`result` 是当前响应、当前列表节点或链式上一步的单个值。
- `lastResult` 保留上游流程结果，使当前规则即使把 `result` 换成 HTML/子节点，仍可获得上游地址。

例如章节页可能同时包含“立即阅读”内容和下一级链接，`contentItems` 可以根据页面是否有内容选择当前 `result` 或 `lastResult`。

## JS 会话范围

- `loadJs` 在会话初始化时执行一次。
- 每次规则执行前，保留全局变量会被刷新。
- 一个作品的目录加载和正文加载可以共享显式作品流会话，因此目录 JS 设置的全局变量可供后续正文 JS 使用。
- 不同规则和并发流程不共享全局对象。
- 离开对应流程后会话会被销毁，不要用 JS 全局变量保存永久登录信息。登录 Session 应由 Cookie 会话管理。
