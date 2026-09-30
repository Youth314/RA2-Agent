# dsh-players

主持 agent 开一局 1v1 的那一半：名册里的每个玩家各得一个 `play_as_<玩家>` 工具，
调用它就给那个玩家建一个**只指挥它那一方**的 continuable 子 agent，并给这个子 agent
挂上**它自己那一份** RA2 MCP 客户端。

隔离是构造上的：每个玩家子 agent 的工具表里只有自己那一份客户端的工具
（`mcp__ra2_alpha__*`）；父 preset 留给它的那一份（`mcp__ra2__*`，连的是没有
`--player` 的默认探针端口，也就是 Alpha）和**玩家面裁剪名单**里的工具（`bash`、
`subagent`、`play_as_*` 等）在它建立时被拿掉。子 agent 手里根本没有对方的工具，
也没有能绕过去的路，不是靠指令约定。

| 文件 | 是什么 |
|---|---|
| `src/index.ts` | 插件：Config、读名册、注册 `play_as_*` 工具、在 `agent/created` 里挂客户端 |
| `src/players.ts` | 玩家名派生、进程内认领表、玩家 scope 的客户端挂载、玩家面裁剪与守卫 |
| `src/roster.ts` | `config/match.json` 的读取与校验 |
| `cordis.patch.yml` | bundle patch：往 profile 里插一行 `ra2-players` |
| `lib/` | `src/` 的编译产物（`npm run build`），loader 实际加载的就是它 |
| `tests/players.test.ts` | 测试（真 ToolRuntime + 真 AgentLoop + 真 scope 链，替身 provider 与客户端） |

---

## 隔离是怎么构造出来的

先看漏在哪。子 agent 继承父的 preset（`packages/subagent/subagent-in-process-driver`
的 `preset-inheritance.spec.ts`：child 跑在父的 preset 上），而 ra2 preset 里本来就有一行

```yaml
- id: mcp-ra2
  name: '@deepseek-ai/dsh-mcp-client'
  config: { serverName: ra2, command: python3, args: ['-m', 'ra2agent.mcp'] }   # 没有 --player
```

`composeFrom` 把子 agent 的 scope 挂到父 preset 那一代的 scope 下面，于是这份客户端
的工具 `mcp__ra2__*` 出现在子 agent 的**继承面**里。它连的是默认探针端口 14521，也就是
Alpha——Beta 的子 agent 照样能指挥 Alpha。这就是泄漏。

**还有两条绕过路**，第 3、4 层就是堵它们：

- `play_as_*` 是 profile 级注册的，玩家也看得见。玩家调 `play_as_beta` 会被「已有在跑的」
  拒掉，但那只是时序：Beta 一结算，Alpha 就能认领 Beta 再用 `send_message` 指挥它——
  等于造一个对面的人。
- `subagent` 更彻底：玩家建个普通子 agent，那个**孙 agent 继承 ra2 preset**，挂上 preset 里
  那行没有 `--player`、没有 `--port` 的 `mcp-ra2`（`DEFAULT_PORT` = 14521 = Alpha）。
- `bash` 最根本：探针就是个 TCP 口，`Client(port=14521)` 直连对面。

本插件按四层堵：

1. **每个玩家一个 serverName**：`ra2_alpha` / `ra2_beta`，工具名 `mcp__ra2_alpha__*`。
   不沿用 `ra2`——靠同层注册去遮蔽继承来的同名工具太隐晦，也不好验证。这一份客户端挂
   在**子 agent 自己的 scope 层**里（key 就是 agent 对象，和 agent-loop 建 agent scope
   用的同一个 key），所以别的 agent 看不到它，`tools.restrict` 也过滤不到它
   （限制只作用于继承面）。
2. **建子 agent 时传 `toolFilter: { deny: [...继承来的 mcp__ra2__* 名字] }`**：名单由
   `ctx.tools.schemas(caller)` 现算。`ToolRestriction` 是精确名匹配
   （`CompiledToolRestriction` 用 `ReadonlySet<string>`，没有通配），所以必须逐个列全。
   这份名单进子 agent 的**描述符**，随会话持久化，冷恢复时会重新生效
   （`continuation.coldResume` 用 `descriptor.toolFilter`）。
3. **子 agent 建立时按它自己的视野剪一遍**（`agent/created`，不依赖调用者视角）：
   继承来的 `mcp__ra2__*`，加上玩家面名单里的名字，逐个 `tools.restrict({ deny })`。
   `restrict` 只过滤继承面、不碰本层注册，所以第 1 层挂进来的工具不受影响。
4. **一道 `tools/execute` 守卫**（在玩家 scope 里注册），按名字拦执行：
   - 本玩家的工具只能由这个 agent 调，别的 agent 调就抛 `... belongs to another Session`
     （照抄 `browser-use-runtime/src/mcp.ts` 的先例）；
   - `mcp__*` 里不属于本玩家的一律拒绝——包括第 3 层之后才出现的名字（上层客户端重连
     后重新列工具）和**任何别的 MCP 服务器**；
   - 玩家面名单里的任何名字一律拒绝。它不看注册层，所以第 3 层摘不掉的本层注册
     （见下）也拦得住。

**第 3 层的硬限制**：`tools.restrict` 只作用于**继承面**（global + 祖先层）。注册在 agent
**自己那一层**的工具摘不掉，写进 deny 还会直接抛 `unknown global tool`。真实部署里就有
这种工具：ra2 preset 的 `tool-subagent` 行开了 `modelSelectionSettings: true`，
`tool-subagent` 于是对每个 agent 用 `candidate.ctx.inject(...)` 注册 `subagent`——它在
**每个 agent 自己的层**里。所以 **`subagent` 会留在玩家子 agent 的视野里，但调不动**
（第 4 层拒绝）。其余名单项（`bash` / `write` / `edit` / `subagent_fork` / `workflow` /
`plugin_manager` / `play_as_*` …）都是继承面或 profile 级的，看得见这一层就摘得掉。

**装载时**就会失败的有：名册读不了 / 玩家名折不出 `[a-z0-9_]` / 两个名字折出同一个工具名 /
派出的 serverName 不合法（含超过 32 字符）或与上层撞名 / `playerDeny` 里有空名字。
**调用时**会失败的有：调用者看不见上层那份客户端（这时无法证明隔离，除非把
`inheritedServerName` 配成空串）/ provider 不支持 `toolFilter`。这几种都直接报错，不会静默地
少一条防护。

**边界**：被挡住的是**游戏通道**。子 agent 仍然是完整的编码 agent，`bash`、文件读写、
`subagent` 之类通用工具照旧可用；本插件不限制、也不打算限制它们。

---

## 玩家面裁剪（`playerDeny`）

玩家子 agent 拿到的是一份**裁剪过**的工具表。名单是两份合起来的：

- `playerDeny`（Config，可改），默认：

  ```
  bash, pwsh, write, edit, subagent, subagent_fork, subagent_codex,
  subagent_claude_code, spawn_teammate, workflow, ralph, plugin_manager
  ```

- **按名册动态算出来的** `play_as_*`：名册里有几个玩家就几条。加一个玩家不用改配置。

前八个是需求指定的；后四个是「能派生新 agent」的其余入口（`subagent_codex` /
`subagent_claude_code` 是 preset 里关掉的那两行 `dsh-tool-subagent` 的 `toolName`，
`spawn_teammate` 是 `dsh-experimental-tool-agent-team`，`ralph` 是 `dsh-tool-ralph`）。

**保留**（不在名单里的都保留）：玩家自己那 5 个 `mcp__ra2_<自己>__*`、`read`、`glob`、
`grep`、`skill`、`todo_write`、`send_message`、`ask_user_question`、`web_fetch`、
`web_search`、`list_agents`、`present`。

名单里写了一个**这个 session 里根本没有的**名字不会让任何东西失败（真实部署里就会发生：
Linux 上 `pwsh` 是 disabled 的，prewired 的默认名单里却有它）。挂载时按名字逐个问 registry：
摘得掉就摘，摘不掉（本层注册）就归给执行期守卫，压根不存在就记一笔。挂载报告里是三个清单，
日志里一行 `ra2-players: <玩家> 的子 agent … 已挂上 …` 会写清楚各多少条。

**部署自己新增的派生入口要自己加进 `playerDeny`**：任何一行
`@deepseek-ai/dsh-tool-subagent` 都能用 `toolName` 改名字，插件没法从注册表里认出
「谁是派生入口」。已知能派生新 agent 的入口就是上面那批 + `play_as_*`。

---

## 服务端配合（必须）

每个玩家一个服务进程：

```
python3 -m ra2agent.mcp --roster <名册> --player <名册里的名字> --wake-session <子 agent id>
```

本插件在子 agent 建立时挂上它、在子 agent 处置时撤掉。`--player` 让服务进程从名册取自己
那份游戏目录与探针端口（`ra2agent.mcp.resolve_player`）；`--wake-session` 让它的唤醒只投回
它自己那个会话。**少任何一半都不成立**：没有 `--player` 的进程谁都能指挥，没有
`--wake-session` 的唤醒会由 `dsh-wake` 去猜候选会话。

`args` 由插件按玩家拼好（`-m <mcpModule> --roster <rosterPath> --player <名字> --wake-session <childId>`），
`command` / `cwd` / `env` 都进 Config。

---

## 工具

每个名册玩家一个，名字是 `play_as_` + 名字小写。

| 参数 | 必填 | 含义 |
|---|---|---|
| `description` | 是 | 3-5 词的显示标签，同时是子 agent 的 label。 |
| `task` | 是 | 交给这个玩家 agent 的初始任务。 |

返回 `{subagentId, player}`：`subagentId` 就是这个子 agent 的会话 id，用 `send_message`
继续给它任务。工具**不等**它打完（`startContinuable` 在初始 prompt 被收下时就返回）。

初始 prompt 明确写了「你是 <玩家名>，只指挥这一方」，并要求它按技法层（status / tactics /
call / cancel）打，需要更多信息时用 `send_message` 回报主持 agent。

---

## 配置

| 字段 | 默认 | 含义 |
|---|---|---|
| `rosterPath` | `/home/youthz/ra2-agent/config/match.json` | 对局名册的绝对路径。读不了 = 插件加载失败。 |
| `provider` | `spawn` | 建 continuable 子 agent 用的 `ctx.subagents` provider。 |
| `mcpCommand` | `python3` | 启动 MCP 服务进程的可执行文件。 |
| `mcpModule` | `ra2agent.mcp` | `-m` 之后的模块名。 |
| `mcpCwd` | `/home/youthz/ra2-agent` | MCP 服务进程的工作目录。 |
| `mcpEnv` | `{}` | 额外的子进程环境变量；没配 `PYTHONPATH` 时自动补 `<mcpCwd>/src`（`ra2agent` 是 src 布局）。 |
| `toolCallTimeoutMs` | `60000` | 单次 MCP 工具调用超时。 |
| `inheritedServerName` | `ra2` | 上层（ra2 preset 的 `mcp-ra2` 行）那份客户端的 serverName。**空串**表示部署里确实没有这一层，此时不做 deny 与继承前缀守卫。 |
| `playerDeny` | 见上 | 玩家面裁剪名单，字符串数组。名册派生的 `play_as_*` 会自动并进来，不用手写；写了不存在的名字不会报错。 |

---

## 装上

profile 是 `web`。**装 bundle 用 profile 自己的包管理器，不要手改 profile 的 `package.json`。**

在 DSH 里让任意一个 agent（Creator/命令权限）执行 plugin_manager 的 `install_bundle`，
target 写 `/home/youthz/ra2-agent/dsh-players`；或者在 GUI 侧栏 **Plugins** 页选
「安装 bundle」，spec 填同一个绝对路径。安装结果里的 `application` 字段决定生效方式
（`applied` 即时生效 / `restart-required` 要重启）。

这是一份 **profile bundle**：`package.json` 的 `dsh.bundle.patch` 指向 `cordis.patch.yml`，
它不属于任何 agent preset，因此 profile 里每个顶层会话都拿得到这些工具——主持 agent 也在内。
上层那份 `mcp-ra2` 行**留着不要动**：主持 agent 是裁判，它自己要用 `game status` 这类门外工具。

自检（不启动游戏也能做）：装好之后看主持 agent 的工具表里有没有 `play_as_alpha`、
`play_as_beta`；调一次 `play_as_alpha`，再看 `list_agents`——应该多出一个子 agent，
且它的工具里只有 `mcp__ra2_alpha__*`。

---

## 开发

```sh
cd /home/youthz/ra2-agent/dsh-players
npm run typecheck   # tsc -p tsconfig.json（对 DSH 已构建的 .d.ts）+ build 配置复查
npm run build       # tsc -p tsconfig.build.json → lib/（loader 加载的是这个，改完 src 必须重新 build）
npm run test        # node + tsx 跑 tests/players.test.ts（19 个用例）
```

三个脚本里的 `tsc` / `tsx` 都写死了 `/home/youthz/deepseek-harness/node_modules/.bin/`，
tsconfig 里的 `@deepseek-ai/*` 也全部指向那个 checkout；换机器或换 checkout 位置要改
`package.json` 的 scripts 与三份 tsconfig。

测试用 DSH 仓库的**源码**（`tsconfig.test.json` → `packages/*/*/src`，由 tsx 的 tsconfig paths
解析），所以要那个 checkout 在、且已经 `pnpm install` 过（测试还引用了仓库里的 `mock-adapter.ts`）。
测试**不起**真的 MCP 服务进程、不碰游戏：`ctx.subagents` 与 MCP 客户端插件是替身，其余
（ToolRuntime、AgentRegistry、AgentLoop、scope 链、`applyChildComposition`）都是真的。

---

## 已知局限

- **`subagent` 会留在玩家子 agent 的视野里，只是调不动**。它在 agent 自己的层里注册，
  `tools.restrict` 摘不掉（这是 `tools.restrict` 的语义，不是配置问题），只有执行期守卫
  拦得住。其余名单项都是继承面/profile 级的，看不见+调不动两样都成立。想让 `subagent`
  连提示里也不出现，只能改 DSH 侧（例如给 `tool-subagent` 加一个「不注册给这个 agent」
  的机制），本插件做不到。
- **名单是黑名单，不是白名单**：部署新增的派生入口（任何一行
  `@deepseek-ai/dsh-tool-subagent` 都可以用 `toolName` 改名）必须自己加进 `playerDeny`。
  更彻底的做法是把继承面改成 `allow`（只留保留名单，其余全裁，fail-closed），本插件没做，
  因为需求要的是一份可改的 deny 名单。
- **一个玩家同时只能有一个在跑的玩家 agent，重复调用被拒绝**（不是"先停掉旧的"）。
  判据是**该玩家的子 agent 还活着**（`ctx.agents.get(childId) !== undefined`），不是
  "它此刻正在跑一个回合"：continuable 子 agent 空闲结算时 Agent 会被处置，那时同一个玩家
  可以重新认领，拿到**新的** childId（也就有一个新的 MCP 服务进程）。被拒绝时错误里会
  带上现有 agent 的 id，并提示改用 `send_message`——追加任务本来就该走那条路。
- **`childId → 玩家` 的映射在进程重启后会丢**，而且**玩家面裁剪也跟着丢**。映射在内存里
  （`PlayerClaims`），不落盘。进程还活着时，冷恢复会重新触发 `agent/created`，裁剪会重新
  挂上；**重启之后**主持 agent 再 `send_message` 冷恢复那个 childId，新进程里没有认领记录，
  既不挂客户端、也不做裁剪。它仍然看不到上层那份 `mcp__ra2__*`（那份 deny 在描述符里，
  随会话持久化），但**会重新拿到 `bash` 等通用工具**。要重新拿到玩家面，重新调一次
  `play_as_<玩家>`（旧 childId 不活着，会认领成功，得到新的 id）。
- **只有游戏通道被挡**：`read` / `glob` / `grep` 是保留的，所以玩家能读对方的游戏目录
  与配置（`D:\Games\ra2probe-b` 里的 `spawn.ini`、`ra2yrcpp.json`）——这是信息面上的
  残留，不等于能指挥对方，但确实是同一台机器上的可见性。要堵就把它们也加进 `playerDeny`。
- **`mcp-resources` 的三个工具（`list_mcp_resources` / `list_mcp_resource_templates` /
  `read_mcp_resource`）不带 `mcp__` 前缀**，守卫的 `mcp__*` 规则覆盖不到；它们带 `server`
  参数，理论上能读别的 server 的资源。这个 profile 里没挂 `mcp-resources`（也不在工具面上），
  真挂了要把这三个名字加进 `playerDeny`。
- **`run_code`（PTC）不算绕过**：嵌套子调用照样经 `resolveExecution` → `get(name, agent)`
  解析，被裁掉的名字在那里就是 `UNKNOWN_TOOL`（读源码确认）。
- **`exec.agent !== agent` 那一支守卫在本组合里不可达**：玩家工具注册在子 agent 自己的
  scope 层里，别的 agent 本来就看不见，也就调不到。它是照抄先例的纵深防御，测试没有
  覆盖到（有用的两条——按名字拦执行、按 `mcp__` 前缀拦外来客户端——都有用例）。
- **只在替身 provider 上端到端验过**：真 provider（`spawn` / `fork`）把 `toolFilter`
  交给 `applyChildComposition` 这条路是**读源码确认**的（`continuation.ts` 的
  `composition` + `descriptor.toolFilter` → `continuation-activation.materializeTracked`
  的 setup → `child-agent.applyChildComposition`）；测试里单独用真的
  `applyChildComposition` 验过效果，但**没有**跑真正的 `startContinuable`。
- **没起过真的 MCP 服务进程，也没启动过游戏**。真进程的行为（`--player` 解析、
  `--wake-session` 投递、`failOnStartupError`）来自 RA2 侧的代码与文档，未在本包里验证。
- **裁剪名单是"建立那一刻"的快照**：之后才注册进来的名字不在 `restrict` 名单里（守卫
  仍然拦执行，但它可能出现在提示里）。上层客户端用 `listChanged: false`（RA2 侧就是），
  实际不会发生。
