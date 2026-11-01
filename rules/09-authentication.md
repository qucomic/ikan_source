# 规则认证 v1

本协议用于站点账号，不是 iKan 账号系统。每条规则只保存一个当前会话；密码默认不落盘，仅在用户主动开启记住密码后加密保存。新凭据写入平台安全存储，规则 JSON 只保存认证方法。

## 编辑器位置

移动端和桌面端均可在“编辑规则 → 登录认证 → 认证配置 auth（JSON）”编辑完整认证对象；旁边的帮助按钮解释协议字段。已有 `auth` 会自动带入，保存时使用编辑后的 JSON，留空或填写 `{}` 可移除配置。非法 JSON、非对象、不支持的协议版本和错误的顶层结构会阻止保存并保留原规则。

此处只填写认证方法，不填写实际密码或 Token；实际凭据仍通过“登录规则”独立安全保存。更新客户端代码后需重新进入编辑页创建新控制器。

## 最小 API 登录

以下 `auth` 对象可放入普通 iKan 规则。示例使用 example.com，实际地址需根据目标站点配置。

```json
{
  "version": 1,
  "entries": [{
    "id": "password",
    "type": "api",
    "label": "账号登录",
    "fields": [
      {"name": "email", "label": "邮箱"},
      {"name": "password", "label": "密码", "secret": true}
    ],
    "request": {"url": "https://api.example.com/auth/sign-in", "method": "POST"},
    "success": {"path": "code", "equals": 200},
    "extract": [{"name": "accessToken", "source": "body", "path": "data.token", "required": true}]
  }],
  "inject": [{
    "header": "authorization",
    "template": "{{accessToken}}",
    "origins": ["https://api.example.com"],
    "pathPrefix": "/"
  }],
  "check": {
    "request": {"url": "https://api.example.com/users/profile"},
    "success": {"path": "code", "equals": 200}
  },
  "expired": {"status": 401}
}
```

`version` 当前仅支持 `1`，其他版本明确报错。入口为 `api`、`manual`、`webview`；多个入口由用户选择。API 登录无需 `loginUrl`，`fields` 的 `name` 是提交字段名。登录请求在计算动态头后合并表单字段，以 JSON 编码提交；显式 Content-Type 保留原值，仅缺失时补默认类型（部分站点会严格检查 charset 大小写）；`encoding: "form"` 改用 UTF-8 表单编码，保留引号、`&`、中文等输入。`request` 使用现有 URL / 请求对象 / `@js:` 地址语义，支持 `loadJs` 和 CryptoJS。不要在 JS 中拼接密码字符串。

## 提取与前置请求

提取项使用 `name` 标识内部凭据，`required` 默认为 `true`。`persist: false` 表示只用于本次流程；普通登录提取默认持久化，前置请求默认临时。

| `source` | 配置 | 来源 |
| --- | --- | --- |
| `body` | `path` | 客户端认证请求的 JSON 响应体 |
| `header` | `key`，可选 `path` | 客户端认证响应头，名称不区分大小写；`path` 可解析头内 JSON |
| `cookie` | `key` | API 响应的 Set-Cookie，或受控 WebView 当前允许来源的 Cookie |
| `localStorage` | `key`，可选 `path` | 受控 WebView 当前允许来源 |
| `sessionStorage` | `key`，可选 `path` | 受控 WebView 当前允许来源 |
| `manual` | `name` 对应字段 | 原生界面手动输入 |

`path` 支持点路径（`data.token`）和 JSONPath（`$.data.token`）。存储值为 JSON 字符串时，可先读取 `key`，再通过 `path` 读取内部字段。必需凭据为空时禁止完成登录。

顶层 `prepare` 是最多 5 个顺序请求：每项包含 `request`、可选 `success` 和 `extract`。前置请求的 Cookie 保存在对应规则会话，提取的 CSRF 等临时值可通过 `{{csrfToken}}` 注入下一请求的头或 body。凭据引用由客户端在脚本求值结束后替换，不作为 JS 全局变量提供。认证请求总是有超时上限。

`manual` 入口声明 `fields` 与 `extract`，例如一个 `name: "accessToken"` 的密码型输入框和同名提取项。`webview` 入口声明 `url`、精确 `origins` 与提取项；用户点击“完成登录”触发提取。WebView 在允许来源内读取，阻止跳转到未声明来源。不同规则使用隔离的临时浏览器会话。iOS/macOS 从当前私有 WebView 的 Cookie 仓库读取，可包含 HttpOnly；Android/Windows 当前只读取当前页可见 Cookie，不能提取 HttpOnly，界面会提示切换接口或手动凭据。客户端不会退回读取全局 Cookie 仓库。系统外部浏览器和第三方网页任意 fetch/XHR 的响应不属于可提取来源。网站的短信、扫码、验证码可由用户在网页登录中完成，原生 API 多步骤挑战不在本期范围。

## 可选注册入口与记住账号密码

在 `auth` 内配置可选 `registration`，与登录 `entries` 分开：

```json
"registration": {
  "url": "https://example.com/register",
  "origins": ["https://example.com"]
}
```

配置有效时，登录页显示“注册账号”；未配置时隐藏。URL 必须是允许来源内的绝对 HTTPS 地址；`origins` 精确包含协议、域名和端口，不能填写任意路径。需要跨来源验证时显式列出各来源。客户端使用独立临时 WebView，限制页面导航、禁止新窗口，不注入现有登录凭据；不拦截或提取注册网络响应、不读取注册密码、不自动判定成功、不自动登录，用户完成后返回登录。此配置不会把注册来源加入 Token 注入范围。未确认注册网页时，不要臆造注册链接。

API 原生表单提供两个客户端开关，不新增规则字段：记住账号默认开启，记住密码默认关闭。只有登录成功后才保存勾选的字段；下次仅预填，密码仍隐藏，不自动提交。开关变化可立即删除对应已保存字段，不会捕获尚未提交的输入。字段值使用独立 `login-forms` 安全存储命名空间，按规则与登录入口隔离，并绑定登录目标；不出现在规则、导出文件、脚本或日志中。退出登录和删除规则会清理该规则所有记忆表单。网页、手动 Token 入口不展示这两个开关。

密码默认不持久化的约定仍有效，用户主动开启“记住密码”是唯一的新增例外；页面文案会随开关变化。认证规则编辑器的帮助已同步这些字段。加载更新后的代码后，重新进入登录页以初始化新表单状态。

## 凭据使用与刷新

`inject` 每项指定请求头 `header`、`template`、精确 HTTPS `origins` 和可选 `pathPrefix`。原值使用 `{{accessToken}}`，Bearer 使用 `Bearer {{accessToken}}`，Cookie 可使用 `header: "cookie"` 与模板 `sid={{sessionId}}; csrf={{csrfToken}}`。多个凭据可组合在一个模板。只允许在声明的协议、域名、端口和路径范围发送，CDN 要独立配置。规则认证配置/来源变化会使旧凭据失配，需要重新登录。

执行顺序是“生成实际请求及动态签名 → 客户端注入凭据 → 发送”。动态头与认证头同名时拒绝发送，防止静默覆盖。常规内容/认证 HTTP 请求携带认证头时不自动重定向（包括同源），规则应提供最终 HTTPS 地址；无认证的跨来源跳转会移除原请求头。搜索、发现、目录、正文和图片使用统一认证请求通道；图片对象仅声明图片真正需要的独立头，不复制 API authorization。

`check` 包含 `request`、`success`；提取完凭据后检测通过才保存。条件可指定 HTTP `status` 或响应体 `path` + `equals` / `nonEmpty`。HTTP 非 2xx 总是失败。`expired` 使用同一条件格式，仅在明确匹配时认为失效；不要把所有 403 或解析错误定义为未登录。

可选 `refresh` 同样包含 `request`、`success`、`extract`。同一规则并发请求共享一次刷新，晚到的旧 Token 响应复用更新后的凭据。自动重放最多一次，仅 GET/HEAD；POST 登录、购买等有副作用的操作不自动重放。存在动态签名时需声明 `retryRequest`，它是一个重新求值的请求地址规则；`result` 是原请求 `{url, method, headers, body}`，必须重新生成 time/nonce/signature。未提供重签入口时不自动重放，原请求返回调用方。刷新不循环重试；网络错误不直接删除凭据。

原生视频在线播放通过本机回环代理接入认证：播放器只收到随机能力地址，不收到站点凭据。直链媒体按流转发 Range/If-Range、HEAD 和状态信息；HLS 主清单、子清单、分片、初始化资源及密钥 URL 均重写到代理，以最终清单地址解析相对路径。每个实际资源和每次重定向均重新按明确来源范围取得凭据；跨来源不沿用原请求头，拒绝 HTTPS 降级。该通道不把 Token 写入媒体 URL、下载恢复描述或缓存索引，播放器销毁、切换来源或初始化失败时关闭代理。当前单个 HLS 清单上限 2 MiB、每个播放会话最多映射 16384 个资源；不支持需要额外播放器协议的 DRM。

直链下载、HLS 清单/分片/密钥下载和在线播放代理共用资源认证管线。流式资源仅依据明确的 HTTP `expired.status` 触发刷新，不读取二进制正文判断业务码；含正文条件的失效配置在此通道不触发刷新。同一规则共享一次刷新，GET/HEAD 在刷新后重新取得凭据并最多重放一次，保留 Range；POST 不自动重放。动态签名仍须由规则提供可重新求值的请求逻辑，不能将旧时间戳写死在媒体头中。

`logout` 可配置远端退出请求。退出先撤销本地凭据、对应 Cookie 和网页会话，取消待完成登录/刷新写回，再尽力远端退出；失败会提示远端会话可能未撤销。删除规则同样清理凭据。安全存储可在重启后恢复会话。

## 旧规则与导出

旧 `cookies` 仍可导入并用于旧规则，已有数据库编码保留兼容字段。新网页登录取得的 Cookie 保存于独立安全会话，不再写入规则。退出后用显式撤销标记防止旧预置 Cookie 自动重新生效。面向用户的规则导出默认删除旧 `cookies`，因此分享文件不携带旧登录态；内部数据库编码显式保留旧字段，以免升级悄悄丢失原账号状态。新 Token、动态 Cookie 和用户选择记住的密码均不进入规则导出。

不要在日志记录原始认证响应、请求 body、Cookie、authorization 或手动凭据。认证失败提示使用受控信息，不显示可能回显密码/Token 的原始服务端文本。

### 声明需要登录的操作

`auth.requiredFor` 是可选字符串数组。例如只限制搜索：

```json
{"version": 1, "requiredFor": ["search"]}
```

支持 `discover`（发现）、`search`（搜索）、`detail`（详情）、`chapter`（目录）、`content`（正文）和 `all`（全部）。多个操作可以组合。省略或空数组沿用旧行为，不会主动拦截。详情当前通过目录请求加载，因此目录请求同时满足 detail 和 chapter 的访问要求。章节 `lock` 的含义与展示不变，不增加 VIP 判断。

同时配置 `auth.entries` 或旧 `loginUrl` 作为登录入口。旧网页登录可仅声明 `auth.version`、`requiredFor` 和可选 `registration`，Cookie 继续由客户端独立保存。要求登录但缺少入口时，客户端提示更新规则。

客户端在请求前检查本地登录凭据；没有凭据时显示“去登录”，已有明确失效状态时显示“重新登录”。登录成功后返回原页面并重试，取消不会触发重试。多来源搜索中只提示受影响来源，其他结果继续显示。不会把通用 403 或 VIP 锁定推断为登录失效；已配置的 `expired` 条件仍用于识别会话失效。


### 网页登录统一到 auth

新规则不再配置顶层 `loginUrl`。验证码网站使用完整 Cookie 会话：

```json
{
  "version": 1,
  "requiredFor": ["search"],
  "entries": [{
    "id": "web", "type": "webview", "label": "网页登录",
    "url": "https://example.com/login",
    "origins": ["https://example.com"],
    "cookieMode": "all"
  }]
}
```

`cookieMode: "all"` 与 `extract` 互斥；不填写实际 Cookie。登录页面提取后独立加密保存，按明确的来源隔离。同来源 HTTPS 网页跳转可以保留；不允许跨来源或降级跳转携带登录会话。普通具名 Cookie / localStorage 提取方式保持不变。

旧 `loginUrl` 在导入、数据库读取及编辑时自动归入 `auth.entries`；已有非空 `entries` 优先，迁移不会改动其配置或 Token 存储范围。旧安全存储中的网页登录 Cookie 可直接继续使用。旧规则预置 Cookie 首次使用时转存安全存储，内部兼容数据暂保留以防迁移失败丢失；退出标记优先，且始终不进入公开导出。编辑页仅显示 auth，不再提供独立登录 URL 或 Cookie 输入框。


### API 登录表单的公开默认值

`auth.entries[].fields[].defaultValue` 是可选字符串，仅用于 API 登录表单的首次预填：

```json
{"id":"password","type":"api","fields":[
  {"name":"username","label":"账号","defaultValue":"public-account"},
  {"name":"password","label":"密码","secret":true,"defaultValue":"public-password"}
]}
```

以上是入口中的表单片段，实际规则仍需配置真实的 request、success 和 extract。默认账号密码是随规则公开分享的信息，仅用于作者有意提供的共享账号；`secret` 只隐藏输入框，不加密规则内容。客户端显示“已填入来源提供的共享账号，可自行修改”，用户可修改或清空，必须主动点击登录。不会自动登录，也不向网页登录表单注入默认值。

已保存的个人表单或记忆开关设置优先：只保存了账号时密码保持为空，不混入共享密码；关闭记忆后重新进入也不补默认值。当前页修改、清空、切换记忆设置都不触发重新预填。作者新增或修改 defaultValue 不会使现有个人表单或认证凭据失效。默认值仅供 UI 使用，认证服务仅提交本次用户确认的表单值。
