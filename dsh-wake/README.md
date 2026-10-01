# dsh-wake

DSH 侧的**唤醒桥**：一个本地 HTTP 路由，外部进程（红警 Agent 的 MCP 服务）POST 一条消息进来，
DSH 就把它当作一条 user 角色消息投进某个会话并**开启一轮**，把那个会话里的模型叫醒。

它解决的是 MCP 通道送不回来的问题：DSH 的 mcp-client 只订阅 `listChanged.tools`，服务端通知
没有转发给插件的路，所以技法层判断「这事得让模型来决定」时，必须走 DSH 侧的入口。

| 文件 | 是什么 |
|---|---|
| `src/index.ts` | 插件：路由注册、Config、请求校验、认证、HTTP 处理 |
| `src/binding.ts` | 会话选择规则与投递（`resolveAgent` → `followup` → `sessions.flush`） |
| `src/http.ts` | 限界请求体读取与 JSON 响应 |
| `cordis.patch.yml` | bundle patch：往 profile 里插一行 `ra2-wake` |
| `lib/` | `src/` 的编译产物（`pnpm run build`），loader 实际加载的就是它 |
| `tests/wake.test.ts` | 测试（真 WebServer + 真 AgentLoop + 脚本化 LLM adapter） |

---

## 接口

```
POST /ra2/wake
Content-Type: application/json
{"text": "基地被打了，3 个建筑在掉血", "frame": 8120, "tactic": "watch_base", "session": ""}
```

| 字段 | 必填 | 含义 |
|---|---|---|
| `text` | 是 | 模型可见的消息正文，非空字符串。措辞归红警那边，DSH 不改写。 |
| `frame` | 否 | 整数，当时的游戏帧。只进会话日志的 source，**不进模型上下文**。 |
| `tactic` | 否 | 发起唤醒的技法名。同上，只进日志。 |
| `session` | 否 | 指定唤醒哪个会话。空串等同不填。填了就**只认它**，不做任何猜测。 |

`frame` / `tactic` 只落进 `user/message` 的 `source`（`{"kind":"ra2-wake", frame, tactic}`），
持久、可回放，但模型看不到。**要模型知道的事必须写进 `text`。**

响应：

| 情况 | 状态码 | 体 |
|---|---|---|
| 投递并持久化确认 | `200` | `{"ok": true, "session": "<实际唤醒了哪个会话>"}` |
| 没会话 / 会话太多 / 解析失败 / flush 没确认 | `200` | `{"ok": false, "error": "<具体原因>"}` |
| 请求本身不合法（空 `text`、非 JSON、超长、Content-Type 不对、方法不对） | `400` / `413` / `415` / `405` | `{"ok": false, "error": "<具体原因>"}` |
| 配了共享密钥但缺失/不符 | `401` | `{"ok": false, "error": "..."}` |
| 配了共享密钥但取不到（credentials 里没有这个引用） | `503` | `{"ok": false, "error": "..."}` |

**判断成功只看 `ok`，不要只看状态码。**「没有可唤醒的会话」是 `200 + ok:false`，
是「没送出去」而不是「送出去了」。对面靠这个决定重试还是记一笔。

请求体上限 `maxBodyBytes`（默认 8192 字节）按**字节**算，声明了 `Content-Length` 就先拒，
流式读的时候再兜一次；超了回 `413`，不会读进内存。

---

## 唤醒哪个会话（绑定规则）

红警的 MCP 进程不知道自己在给哪个 DSH 会话服务，所以绑定只能由 DSH 侧推。规则按顺序：

1. **请求里带了 `session`**：只用它。live agent 直接 followup；普通冷会话通过 sessionController.resolveAgent 恢复。已释放的玩家子 agent 不能按普通冷会话处理，当前专用恢复路径尚未闭合，见[DSH 测试接入审计](../.agents/notes/验证/DSH测试接入审计.md)。失败返回 ok:false。
2. **没带 `session`**：候选 = **当前活着（live）、且工具表里有 `mcp__<mcpServerName>__*` 的顶层会话**
   （`ctx.agents.roots()`，即不是 subagent 子会话），并且 `agent.status === 'idle'`。
   - 恰好 1 个 → 用它。
   - 0 个或 ≥2 个 → 看配置 `fallbackSession`。
3. **fallbackSession 非空**：使用该身份，冷恢复范围同第 1 条。
4. **`fallbackSession` 为空**：回 `200 {"ok": false, "error": ...}`，错误里写清楚是「没有挂 MCP 工具的会话」、
   「挂了 MCP 工具的会话都在跑」还是「有 N 个空闲候选（列出 id）」。

为什么这样：

- **为什么用「工具前缀」而不是「MCP 命令行里有没有 ra2agent.mcp」**：从另一个插件看不到 mcp-client
  行的 `command`/`args`，只看得到它注册进工具表的 `mcp__<serverName>__<tool>` 名字。
  所以判据是 MCP 的 **serverName**（默认 `ra2`），可配置。失败模式：如果哪天 preset 换了 serverName，
  候选会变成 0 个——症状是每次唤醒都回 `ok:false`「没有挂 mcp__ra2__* 工具的会话」，改 `mcpServerName` 即可。
- **为什么只认 live agent**：冷会话的工具还没注册，插件无从知道它挂没挂 MCP。DSH 重启之后、
  还没打开那个会话之前，候选是 0 个——这时要么在请求里带 `session`，要么配 `fallbackSession`。
- **为什么要 idle**：红警是实时游戏，塞给一个正在跑回合的会话，消息要等那一轮结束才轮得到，
  对战术层已经没有意义。所以忙的会话不算候选，并且明确报「都在跑」而不是硬塞。
  注意 `agent.status === 'idle'` 不排除「正在跑一个 maintenance 任务」的会话（那种情况下 status 仍是
  `idle`）；投进去的 followup 不会丢，只是可能等到该任务结束才开轮。
- **为什么多候选要报错而不是随便挑**：一个 MCP 进程可能同时服务多个会话，随便挑会把战术层的
  上下文投到错误的对局里——这是不可回滚的错误，比「这次没叫醒」严重得多。宁可让对面知道你该显式指定。
- **`session` 优先于一切**：显式指定是唯一无歧义的信息源，也是长期来看最省事的用法——
  建议在红警侧记住「我是从哪个会话起的」，或者干脆用 `fallbackSession` 固定一个对局会话。

### 投递语义

```
resolveAgent(sessionId) → followup(createUserMessage(...)) → sessions.flush(agent.session)
```

- 消息以 **user 角色**进入会话历史，因此持久、可回放、可压缩，和 DSH 既有的上下文注入一致。
- `followup` 同步追加 inbox 并唤醒 driver；**flush 返回 true 才回 `ok:true`**。
  flush 为 false（没有任何 `session/flush` 监听者）或抛错时回 `ok:false`，即使消息已经进了 inbox——
  这是有意的：对面需要知道「这条可能没落盘」。
- 响应在确认之后才发出，**不等模型跑完那一轮**。

---

## 认证

判断：**回环 + 强制 `application/json` 足够当默认**，共享密钥是可选项，不是必需。

理由：路由挂在 DSH 自己的 WebServer 上，`host` 只可能是 `127.0.0.1` 或 `0.0.0.0`；
shipped web profile 默认绑 `127.0.0.1`。浏览器里的恶意页面想让本机发这个 POST，
带 `application/json` 的请求是**非简单请求**，必然触发 CORS preflight，而 DSH 的 WebServer
不返回任何放行头——请求根本发不出去。所以「必须是 POST + 必须是 application/json」
本身就是一道有效的 CSRF 防线。

- **`secretEnv` 为空（默认）**：不校验密钥。**此时如果 WebServer 绑的不是 `127.0.0.1`，
  插件在加载时直接抛错**（`ra2-wake refuses to serve an unauthenticated wake route on <host>`），
  整个 profile 那一行起不来，错误信息里写了两条出路。这是有意的「配错就炸」：
  一条能让局域网任何人唤起模型跑一轮的裸路由，比一次启动失败危险得多。
  修法：`--host 127.0.0.1`，或者配 `secretEnv`。
- **`secretEnv` 非空**：每个请求都要带 `x-ra2-wake-secret` 头，值从 `ctx.credentials` 解析
  （credential 引用，不是明文写进 yaml）。比较用 `timingSafeEqual`；缺头或长度不符直接 `401`，
  引用解析不到回 `503`（不是 401——那是对面配置问题，不是对面密钥错）。

---

## 配置

| 字段 | 默认 | 含义 |
|---|---|---|
| `path` | `/ra2/wake` | 精确路由路径。必须是绝对路径、非根、无尾斜杠/查询/片段。 |
| `maxBodyBytes` | `8192` | 请求体字节上限（1 … 1048576）。 |
| `mcpServerName` | `ra2` | 用来识别「挂了红警 MCP」的工具前缀来源，`mcp__<它>__*`。 |
| `fallbackSession` | `''` | 候选为 0 或 ≥2 时用的会话 id。空 = 报错而不是瞎猜。 |
| `secretEnv` | `''` | 存共享密钥的 credential 引用名。空 = 不校验（见上）。 |

---

## 装上

profile 是 `web`。**装 bundle 用 profile 自己的包管理器，不要手改 profile 的 `package.json`。**

推荐：在 DSH 里让任意一个 agent（Creator/命令权限）执行 plugin_manager 的
`install_bundle`，target 写：

```
/home/youthz/ra2-agent/dsh-wake
```

或者在 GUI 侧栏 **Plugins** 页选「安装 bundle」，spec 填同一个绝对路径。

安装结果里的 `application` 字段决定生效方式：

- `applied` —— 配置即时生效，直接试 `POST http://127.0.0.1:3080/ra2/wake`。
- `restart-required` —— **重启 DSH 才生效**。
- `failed` / `cancelled` / `overridden` —— 没装上，看返回的告警/日志。

装完可以自检：

```sh
curl -sS -X POST http://127.0.0.1:3080/ra2/wake \
  -H 'content-type: application/json' \
  -d '{"text":"自检：这条会唤醒一个挂 ra2 MCP 的空闲会话"}'
# → {"ok":true,"session":"..."}  或  {"ok":false,"error":"..."}
```

对面（红警侧）只需要发这一个 POST，并对 `ok:false` 做记录/重试。

---

## 开发

```sh
cd /home/youthz/ra2-agent/dsh-wake
pnpm run typecheck   # tsc -p tsconfig.json（对 DSH 已构建的 .d.ts）+ build 配置复查
pnpm run build       # tsc -p tsconfig.build.json → lib/（loader 加载的是这个，改完 src 必须重新 build）
pnpm run test        # node + tsx 跑 tests/wake.test.ts（12 个用例）
```

三个脚本里的 `tsc` / `tsx` 都写死了 `/home/youthz/deepseek-harness/node_modules/.bin/`，
tsconfig 里的 `@deepseek-ai/*` 也全部指向那个 checkout；换机器或换 checkout 位置要改
`package.json` 的 scripts 与三份 tsconfig。

测试用 DSH 仓库的**源码**（`tsconfig.test.json` → `packages/*/*/src`，由 tsx 的 tsconfig paths 解析），
所以要那个 checkout 在，且它已经 `pnpm install` 过（测试还引用了仓库里的 `mock-adapter.ts`）。

## 已知局限

- **判据是 serverName，不是命令行**：见上「绑定规则」。
- **冷会话不进候选**：只认 live agent；靠 `session` 或 `fallbackSession` 覆盖。
- **`fallbackSession` 写死后，如果那个会话被删了**，每次唤醒都会回 `ok:false`
  且错误来自 `resolveAgent`（`session/not-found`）——不会被静默当成成功。
- **没有做唤醒去重/限流**：同一秒来 10 条就开 10 轮。对面自己保证节奏。
- **没在真实 profile 里端到端跑过**：验证是在隔离的 Cordis 组合里做的（真 WebServer、真
  AgentLoop、真会话日志、真 scope 链），`sessionController.resolveAgent` 用的是 fixture，
  真 MCP 子进程也没有参与。装进 profile 之后的第一件事应该是上面那条 `curl` 自检。
- **没覆盖的路径**：冷会话经 `resolveAgent` resume 起来再唤醒——这条依赖 schedule 的既有先例，
  我没有独立验证。
