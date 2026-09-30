/**
 * 主持 agent 开一局：给名册里的每个玩家各注册一个 `play_as_<玩家>` 工具，
 * 每个工具建一个**只指挥那一方**的 continuable 子 agent，并给它挂一份自己的
 * RA2 MCP 客户端。
 *
 * 隔离是构造上的，三层：子 agent 只拿到自己那份客户端的工具
 * （`mcp__ra2_<玩家>__*`）；父 preset 留下来的那份（`mcp__ra2__*`）与玩家面裁剪
 * 名单（`playerDeny`）里的工具都被 `tools.restrict` 从它的视野里摘掉；另有一道
 * `tools/execute` 守卫按名字拦执行，覆盖 `restrict` 摘不掉的本层注册与之后才出现的
 * 名字。裁剪名单里的 `play_as_*` 是**按名册动态算出来的**——多一个玩家就自动多一条。
 *
 * 服务端配合：每个玩家一个
 * `python3 -m ra2agent.mcp --player <名册里的名字> --wake-session <子 agent id>`，
 * 由本插件在子 agent 建立时挂上、在子 agent 处置时撤掉。
 *
 * @module @local/ra2-players
 */

import { randomUUID } from 'node:crypto'
import type { Context } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import type { ContentBlock } from '@deepseek-ai/dsh-llm'
import * as McpClient from '@deepseek-ai/dsh-mcp-client'
import { SessionId } from '@deepseek-ai/dsh-session'
import type {} from '@deepseek-ai/dsh-subagent'
import type {} from '@deepseek-ai/dsh-tools'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type { ToolRunContext } from '@deepseek-ai/dsh-tools'
import z from '@deepseek-ai/schemastery'
import {
  checkedPlayerServerName,
  inheritedToolNames,
  mountPlayerClient,
  PlayerClaims,
  playerToolName,
} from './players.ts'
import type { PlayerClientPlan, PlayerClientPlugin, PlayerMount } from './players.ts'
import { readRoster } from './roster.ts'
import type { RosterPlayer } from './roster.ts'

/** Cordis 函数插件名。 */
export const name = 'ra2-players'
/** 注册工具与建子 agent 所需的宿主服务。 */
export const inject = ['tools', 'subagents', 'agents']

/** 插件配置。 */
export interface Config {
  /** 对局名册 JSON 的绝对路径。 */
  readonly rosterPath?: string
  /** 建子 agent 用的 `ctx.subagents` provider 名。 */
  readonly provider?: string
  /** 启动 MCP 服务进程的可执行文件。 */
  readonly mcpCommand?: string
  /** `-m` 之后的 Python 模块名。 */
  readonly mcpModule?: string
  /** MCP 服务进程的工作目录。 */
  readonly mcpCwd?: string
  /** 合并进 MCP 服务进程环境的变量。 */
  readonly mcpEnv?: Record<string, string>
  /** 单次 MCP 工具调用或资源请求的超时（毫秒）。 */
  readonly toolCallTimeoutMs?: number
  /**
   * 上层（主持 agent 继承来的）那份 MCP 客户端的 `serverName`；空串表示
   * 部署里没有这一层，此时不做继承前缀的 deny 与守卫。
   */
  readonly inheritedServerName?: string
  /**
   * 玩家面裁剪名单：这些工具对玩家子 agent 既不可见、也调不动。
   *
   * 自己那 5 个 `mcp__ra2_<自己>__*` 不受影响；名册派生的 `play_as_*` 会**自动**并进
   * 这份名单，不用（也不该）手写。名单里写了这个 session 里根本没有的名字不会让
   * 挂载失败——摘不掉的存在性检查与执行期守卫各管一段，见 README。
   */
  readonly playerDeny?: string[]
}

/**
 * 玩家面默认要裁掉的工具。
 *
 * 前八个是需求指定的；后面四个是「能派生新 agent」的其余入口：
 * `subagent_codex` / `subagent_claude_code` 是 ra2 preset 里关掉的两行
 * `@deepseek-ai/dsh-tool-subagent`（一旦打开就会按它们的 `toolName` 注册），
 * `spawn_teammate` 是 `@deepseek-ai/dsh-experimental-tool-agent-team` 的派生入口，
 * `ralph` 是 `@deepseek-ai/dsh-tool-ralph`（它自己会起 subagent）。
 *
 * **部署自己新增的派生入口必须自己加进来**：任何一份 `@deepseek-ai/dsh-tool-subagent`
 * 行都可以用 `toolName` 改名字，插件没法从注册表里认出「谁是派生入口」。
 */
export const DEFAULT_PLAYER_DENY: readonly string[] = [
  'bash',
  'pwsh',
  'write',
  'edit',
  'subagent',
  'subagent_fork',
  'subagent_codex',
  'subagent_claude_code',
  'spawn_teammate',
  'workflow',
  'ralph',
  'plugin_manager',
]

/** 默认名册路径。 */
const DEFAULT_ROSTER_PATH = '/home/youthz/ra2-agent/config/match.json'
/** 默认子 agent provider：`spawn` 是全能力 in-process provider，且支持 continuable。 */
const DEFAULT_PROVIDER = 'spawn'
/** 默认 MCP 服务命令。 */
const DEFAULT_MCP_COMMAND = 'python3'
/** 默认 MCP 服务模块。 */
const DEFAULT_MCP_MODULE = 'ra2agent.mcp'
/** 默认 MCP 服务工作目录，同时是 `ra2agent` 的导入根。 */
const DEFAULT_MCP_CWD = '/home/youthz/ra2-agent'
/** 上层那份客户端在本仓 ra2 preset 里用的 serverName。 */
const DEFAULT_INHERITED_SERVER_NAME = 'ra2'
/** `dsh-mcp-client` 的 `serverName` 语法，插件加载时先自己校验一遍。 */
const SERVER_NAME_PATTERN = /^[A-Za-z0-9_-]{1,32}$/

export const Config: z<Config> = z.object({
  rosterPath: z.string().default(DEFAULT_ROSTER_PATH),
  provider: z.string().default(DEFAULT_PROVIDER),
  mcpCommand: z.string().default(DEFAULT_MCP_COMMAND),
  mcpModule: z.string().default(DEFAULT_MCP_MODULE),
  mcpCwd: z.string().default(DEFAULT_MCP_CWD),
  mcpEnv: z.dict(String).default({}),
  toolCallTimeoutMs: z.number().default(60_000),
  inheritedServerName: z.string().default(DEFAULT_INHERITED_SERVER_NAME),
  playerDeny: z.array(String).default([...DEFAULT_PLAYER_DENY]),
})

/** 加载时定下来、之后每次调用共用的事实。 */
export interface ResolvedConfig {
  /** 名册路径。 */
  readonly rosterPath: string
  /** 子 agent provider 名。 */
  readonly provider: string
  /** MCP 服务命令。 */
  readonly mcpCommand: string
  /** MCP 服务模块。 */
  readonly mcpModule: string
  /** MCP 服务工作目录。 */
  readonly mcpCwd: string
  /** MCP 服务环境变量。 */
  readonly mcpEnv: Record<string, string>
  /** 单次 MCP 调用超时（毫秒）。 */
  readonly toolCallTimeoutMs: number
  /** 上层那份客户端的 serverName；空串表示没有这一层。 */
  readonly inheritedServerName: string
  /** 配置里给的玩家面裁剪名单；名册派生的 `play_as_*` 由 {@link effectivePlayerDeny} 并进来。 */
  readonly playerDeny: readonly string[]
}

/**
 * 校验 schema 表达不了的事实。
 * @param config - 装载进来的配置。
 * @returns 补齐默认值并校验过的配置。
 * @throws {Error} 路径、provider、命令或者 serverName 不合法。
 */
export function resolveConfig(config: Config): ResolvedConfig {
  const rosterPath = config.rosterPath ?? DEFAULT_ROSTER_PATH
  if (!rosterPath.startsWith('/')) {
    throw new Error(`ra2-players: rosterPath 必须是绝对路径，收到 ${JSON.stringify(rosterPath)}`)
  }
  const mcpCwd = config.mcpCwd ?? DEFAULT_MCP_CWD
  if (!mcpCwd.startsWith('/')) {
    throw new Error(`ra2-players: mcpCwd 必须是绝对路径，收到 ${JSON.stringify(mcpCwd)}`)
  }
  const provider = config.provider ?? DEFAULT_PROVIDER
  if (provider === '') throw new Error('ra2-players: provider 不能是空串')
  const mcpCommand = config.mcpCommand ?? DEFAULT_MCP_COMMAND
  if (mcpCommand === '') throw new Error('ra2-players: mcpCommand 不能是空串')
  const mcpModule = config.mcpModule ?? DEFAULT_MCP_MODULE
  if (mcpModule === '') throw new Error('ra2-players: mcpModule 不能是空串')
  const inheritedServerName = config.inheritedServerName ?? DEFAULT_INHERITED_SERVER_NAME
  if (inheritedServerName !== '' && !SERVER_NAME_PATTERN.test(inheritedServerName)) {
    throw new Error(`ra2-players: inheritedServerName 必须匹配 [A-Za-z0-9_-]{1,32} 或者是空串，收到 ${JSON.stringify(inheritedServerName)}`)
  }
  const timeout = config.toolCallTimeoutMs ?? 60_000
  if (!Number.isFinite(timeout) || timeout <= 0) {
    throw new Error(`ra2-players: toolCallTimeoutMs 必须是正的有限数，收到 ${String(timeout)}`)
  }
  const playerDeny = config.playerDeny ?? [...DEFAULT_PLAYER_DENY]
  for (const name of playerDeny) {
    if (name === '' || name.trim() !== name) {
      throw new Error(`ra2-players: playerDeny 里的 ${JSON.stringify(name)} 不是非空、无首尾空白的工具名`)
    }
  }
  return {
    rosterPath,
    provider,
    mcpCommand,
    mcpModule,
    mcpCwd,
    // `ra2agent` 是 src 布局，`python3 -m ra2agent.mcp` 要能从工作目录导入它；
    // 显式配了 PYTHONPATH 就以配置为准。
    mcpEnv: { PYTHONPATH: `${mcpCwd}/src`, ...config.mcpEnv },
    toolCallTimeoutMs: timeout,
    inheritedServerName,
    playerDeny: [...new Set(playerDeny)],
  }
}

/**
 * 最终生效的玩家面裁剪名单：配置项，加上**按名册动态算出来**的 `play_as_*`。
 *
 * 名册里有几个玩家就有几条 `play_as_*`；加一个玩家不用改配置。玩家自己也不该拿得到
 * 这些工具——它要是能调 `play_as_beta`，等 Beta 那个 agent 一结算就能认领对面，
 * 等于造一个对面的人来绕过隔离。
 * @param playerDeny - 配置里给的名单（已经校验过）。
 * @param players - 名册里的玩家。
 * @returns 去重后保持顺序的名单：配置项在前，`play_as_*` 在后。
 */
export function effectivePlayerDeny(
  playerDeny: readonly string[],
  players: readonly RosterPlayer[],
): string[] {
  const names = [...playerDeny]
  for (const player of players) names.push(playerToolName(player.name))
  return [...new Set(names)]
}

/** 一次 `play_as_*` 调用的入参。 */
export interface PlayArgs {
  /** 交给这个子 agent 的初始任务。 */
  readonly task: string
  /** 界面显示的短标签。 */
  readonly description: string
}

/** 调用现场里本插件需要的那几个字段。 */
export interface PlayCall {
  /** 正在调用的 agent；没有它就没人能当子 agent 的父。 */
  readonly agent?: Agent | undefined
  /** 调用方的取消信号。 */
  readonly signal: AbortSignal
}

/** 一次 `play_as_*` 的结果，也是工具的规范返回值。 */
export interface PlayResult {
  /** 建出来的玩家子 agent id；`send_message` 用它继续对话。 */
  readonly subagentId: string
  /** 这个子 agent 指挥的玩家名。 */
  readonly player: string
}

/** 建玩家子 agent 需要的、加载时定下来的东西。 */
export interface PlayerRuntime {
  /** 插件自己的 ctx。 */
  readonly ctx: Context
  /** 加载时解析好的配置。 */
  readonly resolved: ResolvedConfig
  /** 玩家 → 子 agent 的进程内认领表。 */
  readonly claims: PlayerClaims
}

/**
 * 给子 agent 的初始 prompt。
 * @param playerName - 玩家名。
 * @param task - 主持 agent 给的任务。
 * @returns 一段文本。
 */
export function initialPrompt(playerName: string, task: string): string {
  return [
    `你是 ${playerName}。这一局里你只指挥 ${playerName} 这一方。`,
    `你的 RA2 MCP 客户端已经用名册里 ${playerName} 那份游戏目录与探针端口启动，`
    + '你的工具只连到这一方。对手的工具你既看不到也调不到，不要试图指挥对手。',
    '',
    '开局前先读 skill ra2-play：单位、造价、克制与玩家的黑话都在它指向的 codex/ 里。',
    '一切对局动作都经过技法层——status 看局势，tactics 挑技法，call 下达，cancel 撤销；'
    + '没有直接向引擎下命令的工具。',
    '需要更多信息或阶段性结论时，用 send_message 回报主持 agent。',
    '',
    `你的任务：${task}`,
  ].join('\n')
}

/**
 * 一名玩家那一份 MCP 客户端的挂载方案。
 * @param player - 名册里的一方。
 * @param resolved - 加载时解析好的配置。
 * @param deny - 最终生效的玩家面裁剪名单。
 * @returns 命名、玩家面名单、配置与继承前缀。
 */
function clientPlanFor(player: RosterPlayer, resolved: ResolvedConfig, deny: readonly string[]): PlayerClientPlan {
  const serverName = checkedPlayerServerName(player.name, resolved.inheritedServerName)
  return {
    serverName,
    inheritedServerName: resolved.inheritedServerName,
    deny,
    configure: childId => McpClient.Config({
      transport: 'stdio',
      serverName,
      command: resolved.mcpCommand,
      args: [
        '-m', resolved.mcpModule,
        '--roster', resolved.rosterPath,
        '--player', player.name,
        '--wake-session', childId,
      ],
      env: resolved.mcpEnv,
      cwd: resolved.mcpCwd,
      toolCallTimeoutMs: resolved.toolCallTimeoutMs,
      failOnStartupError: true,
      // 让它自动重连（DSH 的默认就是重连，此前这里显式关掉了）。玩家的 MCP 进程
      // **就是那一侧的自动层与事件侦测**：进程一死，那一侧既没人指挥、开局/矿车/电力
      // 也全停（实测 Beta 侧因进程消失整侧瘫痪，重派 agent 后工具面仍是 Not connected）。
      // 开着重连，DSH 会按退避把服务再拉起来。
      reconnect: { enabled: true },
    }),
  }
}

/**
 * 建一个只指挥这名玩家的 continuable 子 agent。
 *
 * 顺序是硬要求：先自己生成 childId 并写进认领表，**再**调 `startContinuable`。
 * 子 agent 的 `agent/created` 可能在 `startContinuable` 返回之前就触发，而挂载
 * 只认表里的 childId。失败时把这次认领回滚。
 * @param runtime - 插件 ctx、解析好的配置与认领表。
 * @param player - 名册里的一方。
 * @param args - 任务与显示标签。
 * @param call - 调用方的 agent 与取消信号。
 * @returns 子 agent 的 id 与玩家名。
 * @throws {Error} 调用者不是 agent、继承的那份客户端不在，或者建立子 agent 失败。
 */
export async function startPlayerAgent(
  runtime: PlayerRuntime,
  player: RosterPlayer,
  args: PlayArgs,
  call: PlayCall,
): Promise<PlayResult> {
  const parent = call.agent
  if (parent === undefined) {
    throw new Error(`ra2-players: ${player.name} 需要一个调用者 agent 才能建子 agent（exec.agent 是空的）`)
  }
  // deny 名单按调用者视角算：子 agent 继承的是同一个 preset，看到的是同一份
  // 上层客户端。这份名单进 toolFilter，随描述符持久化，冷恢复时仍然生效。
  const inherited = inheritedToolNames(runtime.ctx, parent, runtime.resolved.inheritedServerName)
  if (runtime.resolved.inheritedServerName !== '' && inherited.length === 0) {
    throw new Error(
      `ra2-players: 在 ${parent.id} 的工具表里看不到任何 mcp__${runtime.resolved.inheritedServerName}__* 工具，`
      + '于是无法证明子 agent 不会继承那份客户端。请先让上层挂好并连上它'
      + `（ra2 preset 里的 mcp-${runtime.resolved.inheritedServerName} 行）；`
      + '确实没有这一层时，把 inheritedServerName 配成空串。',
    )
  }
  // deny 要生效，provider 必须把 toolFilter 交给子 agent 的组装过程；不支持的
  // provider 会把它丢掉，那就等于没有隔离。
  if (inherited.length > 0) {
    const provider = runtime.ctx.subagents.getProvider(runtime.resolved.provider)
    if (provider !== undefined && !provider.capabilities.toolFilter) {
      throw new Error(
        `ra2-players: provider "${runtime.resolved.provider}" 不支持 toolFilter，`
        + `没法把继承来的 ${runtime.resolved.inheritedServerName} 客户端从子 agent 手里拿掉，拒绝开工`,
      )
    }
  }

  const childId = SessionId(randomUUID())
  runtime.claims.claim(player.name, childId, candidate => runtime.ctx.agents.get(candidate) !== undefined)
  try {
    const started = await runtime.ctx.subagents.startContinuable({
      provider: runtime.resolved.provider,
      label: args.description,
      childId,
      request: {
        prompt: [{ type: 'text', text: initialPrompt(player.name, args.task) }] as ContentBlock[],
        parent,
        ...inherited.length === 0 ? {} : { toolFilter: { deny: inherited } },
      },
      signal: call.signal,
    })
    return { subagentId: started.childId, player: player.name }
  } catch (error: unknown) {
    runtime.claims.release(childId)
    throw error
  }
}

/**
 * 工具描述：从模型视角说清什么时候用它、它返回什么。
 * @param playerName - 玩家名。
 * @param provider - 子 agent provider 名。
 * @returns 一段模型可见的说明。
 */
function toolDescription(playerName: string, provider: string): string {
  return `为 ${playerName} 开一个玩家 agent（provider ${provider}），它只指挥 ${playerName} 这一方。`
    + `它自己那一份 RA2 MCP 客户端连的是名册里 ${playerName} 的游戏实例，`
    + '对手的工具它既看不到也调不到。'
    + '调用立刻返回子 agent 的 id，不等它打完；之后用 send_message 继续给它任务。'
    + `同一个玩家同一时刻只能有一个在跑的玩家 agent：${playerName} 那个还没结算时再调这个工具会被拒绝，`
    + '请改用 send_message。'
}

/**
 * 装载插件：读名册（读不了就在这里失败），给每个玩家注册一个工具，
 * 并在 `agent/created` 里给认领过的子 agent 挂上它自己的 MCP 客户端。
 * @param ctx - 带 `tools`、`subagents`、`agents` 的上下文。
 * @param config - 插件配置。
 * @throws {Error} 配置非法、名册读不了、玩家名派不出工具名，或者两名玩家撞名。
 */
export function apply(ctx: Context, config: Config): void {
  mountPlayers(ctx, config, McpClient)
}

/**
 * `apply` 的实现体，客户端插件由调用方给：生产传 `@deepseek-ai/dsh-mcp-client`，
 * 测试传替身，免得为了验一条隔离规则去起真的 MCP 服务进程。
 * @param ctx - 带 `tools`、`subagents`、`agents` 的上下文。
 * @param config - 插件配置。
 * @param client - 要挂进每个玩家 scope 的 MCP 客户端插件。
 * @throws {Error} 配置非法、名册读不了、玩家名派不出工具名，或者两名玩家撞名。
 */
export function mountPlayers(ctx: Context, config: Config, client: PlayerClientPlugin): void {
  const resolved = resolveConfig(config)
  // 名册读不了就在这里失败：宁可插件不加载，也不要静默地一个工具都不注册。
  const roster = readRoster(resolved.rosterPath)
  const runtime: PlayerRuntime = { ctx, resolved, claims: new PlayerClaims() }
  const plans = new Map<string, PlayerClientPlan>()
  const mounted = new Map<string, PlayerMount>()
  const deny = effectivePlayerDeny(resolved.playerDeny, roster.players)

  for (const player of roster.players) {
    // 玩家名到工具名/serverName 的派生在这里全部校验完：名字不合法、serverName
    // 太长、与上层撞名，都在加载时失败，而不是等到模型去调它。
    plans.set(player.name, clientPlanFor(player, resolved, deny))
  }
  ctx.logger.info(`ra2-players: 玩家面裁剪名单 ${deny.length} 条：${deny.join(', ')}`)

  ctx.on('agent/created', async ({ agent }) => {
    const playerName = runtime.claims.playerOf(agent.id)
    // 命中认领表才挂：别的 agent（主持 agent、别人的子 agent）在这里直接放过。
    if (playerName === undefined) return
    const plan = plans.get(playerName)
    if (plan === undefined) return
    // 冷恢复会为同一个 childId 再建一个 agent 对象；先把上一次那份卸掉。
    const previous = mounted.get(agent.id)
    if (previous !== undefined) {
      mounted.delete(agent.id)
      await previous.dispose()
    }
    const mount = await mountPlayerClient(ctx, agent, plan, client)
    mounted.set(agent.id, mount)
    ctx.logger.info(
      `ra2-players: ${playerName} 的子 agent ${agent.id} 已挂上 ${plan.serverName}；`
      + `视野里摘掉 ${String(mount.hidden.length)} 条、只拦执行 ${String(mount.guardOnly.length)} 条`
      + `${mount.guardOnly.length === 0 ? '' : `（${mount.guardOnly.join(', ')}）`}`
      + `${mount.absent.length === 0 ? '' : `、名单里不存在 ${mount.absent.join(', ')}`}`,
    )
    agent.ctx.effect(() => async () => {
      mounted.delete(agent.id)
      await mount.dispose()
    }, `ra2-players: ${playerName}`)
  })

  for (const player of roster.players) {
    const toolName = playerToolName(player.name)
    ctx.effect(() => ctx.tools.register(defineTool({
      name: toolName,
      description: toolDescription(player.name, resolved.provider),
      parameters: {
        description: {
          type: 'string',
          required: true,
          description: 'A short (3-5 word) description of the delegated task, for display.',
        },
        task: {
          type: 'string',
          required: true,
          description: `交给 ${player.name} 的玩家 agent 的初始任务：要它做什么、达到什么算成功。`
            + '它会拿到自己的游戏实例，按技法层自己决定怎么打。',
        },
      },
      output: {
        schema: {
          type: 'object',
          additionalProperties: false,
          properties: {
            subagentId: { type: 'string', required: true, description: '玩家子 agent 的 id，用 send_message 继续给它任务。' },
            player: { type: 'string', required: true, description: '这个子 agent 指挥的玩家名。' },
          },
        },
        render: (_args, value) => [{
          type: 'text',
          text: `已为 ${value.player} 建立玩家 agent ${value.subagentId}，初始任务已受理。用 send_message 继续给它任务。`,
        }],
      },
      execute: (args: PlayArgs, exec: ToolRunContext) => startPlayerAgent(runtime, player, args, {
        agent: exec.agent,
        signal: exec.signal,
      }),
    })), `ra2-players: ${toolName}`)
  }
}
