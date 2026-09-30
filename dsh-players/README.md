# dsh-players

主持 agent 开一局 1v1 的那一半：名册里的每个玩家各得一个 `play_as_<玩家>` 工具，
调用它就给那个玩家建一个**只指挥它那一方**的 continuable 子 agent，并给这个子 agent
挂上**它自己那一份** RA2 MCP 客户端。

隔离是构造上的：每个玩家子 agent 的工具表里只有自己那一份客户端的工具
（`mcp__ra2_alpha__*`），父 preset 留给它的那一份（`mcp__ra2__*`，连的是没有
`--player` 的默认探针端口，也就是 Alpha）在它建立时被拿掉。子 agent 手里根本没有
对方的工具，不是靠指令约定。

| 文件 | 是什么 |
|---|---|
| `src/index.ts` | 插件：Config、读名册、注册 `play_as_*` 工具、在 `agent/created` 里挂客户端 |
| `src/players.ts` | 玩家名派生、进程内认领表、玩家 scope 的 MCP 挂载与守卫 |
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

本插件按三层堵：

1. **每个玩家一个 serverName**：`ra2_alpha` / `ra2_beta`，工具名 `mcp__ra2_alpha__*`。
   不沿用 `ra2`——靠同层注册去遮蔽继承来的同名工具太隐晦，也不好验证。这一份客户端挂
   在**子 agent 自己的 scope 层**里（key 就是 agent 对象，和 agent-loop 建 agent scope
   用的同一个 key），所以别的 agent 看不到它，`tools.restrict` 也过滤不到它
   （限制只作用于继承面）。
2. **建子 agent 时传 `toolFilter: { deny: [...] }`**：名单是调用者此刻看得见的全部
   `mcp__ra2__*` 名字。`ToolRestriction` 是精确名匹配（`CompiledToolRestriction` 用的是
   `ReadonlySet<string>`，没有通配），所以必须逐个列全，名单由
   `ctx.tools.schemas(caller)` 现算。这份名单进子 agent 的**描述符**，随会话持久化，
   冷恢复时会重新生效（`continuation.coldResume` 用 `descriptor.toolFilter`）。
   `tools.restrict` 只过滤继承面、不碰本层注册，所以第 1 层挂进来的工具不受影响。
3. **两道 `tools/execute` 守卫**（在玩家 scope 里注册）：
   - 本玩家的工具只能由这个 agent 调，别的 agent 调就抛
     `... belongs to another Session`（照抄 `browser-use-runtime/src/mcp.ts` 的先例）；
   - 任何 `mcp__ra2__*`（第 2 层 deny 之后才出现的名字，比如上层客户端重连后重新列工具）
     一律拒绝。

**装载时**就会失败的有：名册读不了 / 玩家名折不出 `[a-z0-9_]` / 两个名字折出同一个工具名 /
派出的 serverName 不合法（含超过 32 字符）或与上层撞名。**调用时**会失败的有：调用者看不见
上层那份客户端（这时无法证明隔离，除非把 `inheritedServerName` 配成空串）/ provider 不支持
`toolFilter`。这几种都直接报错，不会静默地少一条防护。

**边界**：被挡住的是**游戏通道**。子 agent 仍然是完整的编码 agent，`bash`、文件读写、
`subagent` 之类通用工具照旧可用；本插件不限制、也不打算限制它们。

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
npm run test        # node + tsx 跑 tests/players.test.ts（14 个用例）
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

- **一个玩家同时只能有一个在跑的玩家 agent，重复调用被拒绝**（不是"先停掉旧的"）。
  判据是**该玩家的子 agent 还活着**（`ctx.agents.get(childId) !== undefined`），不是
  "它此刻正在跑一个回合"：continuable 子 agent 空闲结算时 Agent 会被处置，那时同一个玩家
  可以重新认领，拿到**新的** childId（也就有一个新的 MCP 服务进程）。被拒绝时错误里会
  带上现有 agent 的 id，并提示改用 `send_message`——追加任务本来就该走那条路。
- **`childId → 玩家` 的映射在进程重启后会丢**。它在内存里（`PlayerClaims`），不落盘。
  重启后：已经挂好的子 agent 不受影响（它们随进程一起没了），持久化的会话仍在，但
  主持 agent 再 `send_message` 冷恢复那个 childId 时，新进程里没有认领记录，
  **不会**给它挂客户端。好在 `toolFilter` 的 deny 是写进描述符的，冷恢复出来的子 agent
  仍然看不到上层那份 `mcp__ra2__*`——它是安全的，只是没有自己那一份工具，也没有游戏
  能力。要重新拿到工具，重新调一次 `play_as_<玩家>`（旧 childId 不活着，会认领成功，
  得到新的 id）。
- **`exec.agent !== agent` 那一支守卫在本组合里不可达**：玩家工具注册在子 agent 自己的
  scope 层里，别的 agent 本来就看不见，也就调不到。它是照抄先例的纵深防御，测试没有
  覆盖到（可覆盖的是前缀守卫那一条，有用例）。
- **只在替身 provider 上端到端验过**：真 provider（`spawn` / `fork`）把 `toolFilter`
  交给 `applyChildComposition` 这条路是**读源码确认**的（`continuation.ts` 的
  `composition` + `descriptor.toolFilter` → `continuation-activation.materializeTracked`
  的 setup → `child-agent.applyChildComposition`）；测试里单独用真的
  `applyChildComposition` 验过效果，但**没有**跑真正的 `startContinuable`。
- **没起过真的 MCP 服务进程，也没启动过游戏**。真进程的行为（`--player` 解析、
  `--wake-session` 投递、`failOnStartupError`）来自 RA2 侧的代码与文档，未在本包里验证。
- **deny 名单是"建立那一刻"的快照**：上层客户端之后新列出来的工具不在名单里，靠第 3 层
  的前缀守卫拦执行；它们仍可能出现在子 agent 的提示里（守卫只拦调用，不改提示）。
  上层客户端用 `listChanged: false`（RA2 侧就是），实际不会发生。
