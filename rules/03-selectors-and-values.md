# 选择器与取值规则

取值规则支持 CSS、XPath、JSONPath、正则、JavaScript、模板、结果合并和备选回退。引擎会先编译整条表达式，不会简单地对 JS 源码做全局 `split("||")`。

## CSS

```text
@css:.book-item
.book-item
```

`@css:` 可省略。当规则不以 `//`、`$.` 或其他明确前缀开头时，默认按 CSS 处理。

### 取字段

```text
.title@text
a@href
img@src
img@data-src
#content@html
article@outerHtml
```

| 后缀 | 结果 |
| --- | --- |
| `@text` | 节点文本，默认值 |
| `@html` | 将节点 HTML 转为可读文本，会去掉脚本和纯标签干扰 |
| `@outerHtml` | 原始节点 HTML |
| `@href`、`@src`、`@data-src` | 对应属性 |
| `@abs:href` | **兼容语法**：当前解析为 `href` 属性，真正的绝对 URL 归一化由后续地址/资源流程完成 |

### 直接文本读取

需要区分节点自身文本与后代文本时，使用显式 `@css:`：

```text
@css:#content@ownText
@css:#content>p@textNodes
```

- `@ownText` 返回元素自身的直接文本，不包含子元素文本。
- `@textNodes` 返回元素的直接文本节点；多个匹配元素的结果按正常列表规则合并。

### CSS 查询结果集操作

结果集操作写在完整 CSS 选择器之后、读取器之前：

```text
@css:.item@[0]@text
@css:.item@[0,2,-1]@href
@css:.item@[1:5:2]@text
@css:.item@[!0,2]@text
@css:.item@[-1:0]@text
```

- 单个数字选择一个结果，负数从末尾计数。
- `start:end` 是包含两端的范围，可增加 `step`。
- `!` 排除指定索引或范围。
- `[-1:0]` 将结果倒序。
- 操作针对完整查询结果执行，因此不能写成 `@css:.group@[1]>a`。

CSS 节点内可以使用相对子选择器：

```text
.book-card 作为 searchList
.title>a@text 作为 searchName
.title>a@href 作为 searchResult
```

当字段相对于当前列表节点执行时，选择器开头的 `>` 表示只从当前节点的直接子元素开始匹配，语义相当于以当前节点为作用域的 `:scope > ...`：

```text
>a@text
>h3>a@text
@css:>a@[0]@href
```

- `a@text` 会查询当前节点内任意深度的后代 `a`。
- `>a@text` 只查询当前节点的直接子元素 `a`。
- 前导 `>` 是 Ikan 的相对 CSS 扩展；选择器中间的 `>` 仍是普通 CSS 直接子组合符。

### 当前列表节点本身取值

`searchName`、`discoverName`、`chapterName` 等字段相对当前列表节点执行。
写法取决于列表选择器是否已经选中了目标元素。

列表节点是外层容器时，需要继续选择内部元素：

```json
{
  "chapterList": "#chapters li",
  "chapterName": "a@text",
  "chapterResult": "a@href"
}
```

列表节点已经是目标 `<a>` 时，直接读取当前节点：

```json
{
  "chapterList": "#chapters a",
  "chapterName": "text",
  "chapterResult": "href"
}
```

当前引擎兼容 `@text`、`@html`、`@outerHtml`、`@href` 等前导 `@` 写法，
但新规则统一使用不带前导 `@` 的 `text`、`html`、`outerHtml`、`href`。
前导 `@` 主要用于完整选择器中的取值后缀，例如 `a@text`。

### 结构伪类

规则引擎支持浏览器中最常用的结构伪类：

- 子节点位置：`:first-child`、`:last-child`、`:only-child`、`:nth-child(...)`、`:nth-last-child(...)`
- 同类型位置：`:first-of-type`、`:last-of-type`、`:only-of-type`、`:nth-of-type(...)`、`:nth-last-of-type(...)`
- 简单排除：`:not(...)`

`nth-*` 支持整数、`odd`、`even` 和标准 `An+B` 公式：

```text
.pager>a:last-of-type@href
.book:nth-child(even)
.book:nth-of-type(2n+1)
.book:nth-last-of-type(-n+3)
.book:not(.disabled)
```

位置按元素节点计算，HTML 中的换行和纯文本不会占用序号；`*-of-type`
只在同一父节点下的同标签元素之间计数。

当前不是完整的浏览器 CSS4 实现。`:has(...)`、`:is(...)`、`:where(...)`、
`:hover`、`:active`、`:checked` 以及 `::before` 等伪元素不可用于规则选择器。
遇到这些情况应改用稳定的类名/属性选择器，无法表达时再使用 JavaScript。

### 旧版 CSS 简写

为导入旧规则保留：

```text
class.book-card
tag.a.0@text
tag.a.1@href
tag.img.0@src
```

新规则优先使用标准 CSS 选择器。

## XPath

```text
@xpath://ul[@id="chapter-list"]/li
//ul[@id="chapter-list"]/li
```

`@xpath:` 可省略，以 `//` 开头时会自动识别。

```text
//h1/text()
//a[contains(@class, "chapter")]/@href
//*[@class="title"]/text()
//*[@id="content"]/html()
/html/body/main/div[2]/only()
(//div[contains(@class, "item")])[2]/a/text()
//a[contains(@href, "chapter") and contains(normalize-space(.), "下一章")]/@href
```

当前引擎实现的是规则解析所需的 XPath 子集，不是完整的 W3C XPath 引擎。明确支持：

- `/` 子级轴、`//` 后代轴，以及 `/html/body/...` 绝对路径；
- 节点位置 `[2]` 和分组后位置 `(//div)[2]`；
- 属性谓词，如 `[@id="content"]`、`[@data-type="book"]`；
- 属性包含 `contains(@class, "item")`；
- 文本包含 `contains(normalize-space(.), "下一章")`；
- 谓词内的 `and`、`or` 组合；
- `/text()` 取文本、`/@href` 取属性、`/html()` 转换为可读文本、`/only()` 使用兼容的节点内层读取方式。

不要猜测任意 XPath 轴、函数或复杂谓词也能工作。超出以上范围时，改用 CSS 或 `@js:`，并用真实响应验证。

## JSONPath

```text
@json:$.data.items[*]
$.data.items[*]
$..url
```

`@json:` 可省略，前缀大小写不敏感。

对列表中每个 JSON 对象再取值：

```json
"searchList": "$.data.items[*]",
"searchName": "$.name",
"searchResult": "$.url"
```

## 正则取值

**旧版兼容**：以 `:` 开头可从当前文本中取正则匹配：

```text
:第\d+章
```

复杂正则推荐用替换规则或 JS，可读性更高。

## 结果合并 `&&`

`&&` 会执行所有分支并合并结果：

```text
.newbook_list&&.articlegeneral
```

```text
.newbook_title>a@text&&.p2>.blue@text
```

适用于同一页有两种不同卡片结构。它不是 CSS 的“交集”，而是规则结果的并集。

## 交错合并 `%%`

`%%` 会按分支顺序轮流取一个结果，直到所有分支耗尽：

```text
.primary%%.secondary
```

若两边分别返回 `[A1, A2]` 和 `[B1, B2, B3]`，结果为
`[A1, B1, A2, B2, B3]`。它用于保留 Legado 的交错表达式语义，不等同于 `&&`。

## 备选回退 `||`

`||` 会从左到右执行，返回第一个非空结果：

```text
.primary-title@text||h1@text||title@text
```

与 JS 中的 `||` 不冲突：

```javascript
@js:result.name || "未知名称"
```

编译器会识别引号、括号、对象、数组和正则内部的分隔符，不会盲目拆分。

## 链式 JavaScript

```javascript
.bookname>a@href@js:
(() => {
  const parts = result.split("/");
  const id = parts[parts.length - 2];
  return `https://img.example.com/${id}.jpg`;
})()
```

执行顺序：

1. `.bookname>a@href` 先返回 URL 列表。
2. `@js:` 对列表中每个 URL 分别执行一次。
3. 每次 JS 的 `result` 都是当前单个 URL 字符串。
4. 每次 JS 的返回值再合并为最终列表。

如果希望 JS 一次性处理整个列表，请从 `@js:` 开始，在 JS 内主动调用选择器：

```javascript
@js:
(async () => {
  const urls = await css(result, ".content-img@data-src");
  return urls.map(url => ({ url }));
})()
```

也可以把 JS 的返回值继续交给后续分析器。下面的旧版写法仍受支持：

```javascript
@js:
const decoded = decode(result);
decoded
@json:$..url
```

执行顺序是：JS 先执行一次并返回 JSON 字符串或对象，然后 `@json:$..url`
从该返回值中提取所有图片地址。后续阶段标记必须位于 JavaScript 顶层；写在字符串、
正则、对象或函数体内部的 `@json:` 不会被当作阶段分隔符。

## 字符串模板 `{{...}}`

```text
作者：{{.author@text}}
```

多个列表值会按索引组合：

```text
{{@css:.name@text}} - {{@css:.status@text}}
```

如果两个列表长度不同，结果以较短列表为准。

## 正则替换 `##`

格式：

```text
规则##正则##替换文本##是否只替换第一个
```

示例：

```text
.title@text##\s+## ##false
text##book##novel##true
```

- 不写替换文本表示删除匹配内容。
- 最后一段 `true` 表示只替换第一个；`false` 或省略表示全部替换。
- 替换文本支持 `$1` 和 `${1}` 捕获组。
- `##` 会作为顶层语法解析，正则非常复杂时建议改用 JS。

写入 JSON 时，正则中的反斜杠还要再经过一次 JSON 转义。例如过滤
`.txtnav@html` 结果中的 `dingdianzww.org`：

```json
"contentItems": ".txtnav@html##dingdianzww\\.org"
```

JSON 解码后，实际正则是 `dingdianzww\.org`。`@` 是 Ikan 规则分隔符，直接写
`@` 即可；不要写成 `\@`，后者不是合法的 JSON 转义。

## 列表与字符串的差别

- 列表字段使用元素列表。
- 取值字段可以返回多个字符串。
- 当某个内部调用需要单字符串时，多值会用两个空格连接。
- 不要依赖 JS 自动把元素对象转 JSON。跨 JS 边界的 HTML 节点会以 HTML 字符串表示。
