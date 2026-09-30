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
import type { Context } from '@deepseek-ai/cordis';
import type { Agent } from '@deepseek-ai/dsh-agent';
import z from '@deepseek-ai/schemastery';
import { PlayerClaims } from './players.ts';
import type { PlayerClientPlugin } from './players.ts';
import type { RosterPlayer } from './roster.ts';
/** Cordis 函数插件名。 */
export declare const name = "ra2-players";
/** 注册工具与建子 agent 所需的宿主服务。 */
export declare const inject: string[];
/** 插件配置。 */
export interface Config {
    /** 对局名册 JSON 的绝对路径。 */
    readonly rosterPath?: string;
    /** 建子 agent 用的 `ctx.subagents` provider 名。 */
    readonly provider?: string;
    /** 启动 MCP 服务进程的可执行文件。 */
    readonly mcpCommand?: string;
    /** `-m` 之后的 Python 模块名。 */
    readonly mcpModule?: string;
    /** MCP 服务进程的工作目录。 */
    readonly mcpCwd?: string;
    /** 合并进 MCP 服务进程环境的变量。 */
    readonly mcpEnv?: Record<string, string>;
    /** 单次 MCP 工具调用或资源请求的超时（毫秒）。 */
    readonly toolCallTimeoutMs?: number;
    /**
     * 上层（主持 agent 继承来的）那份 MCP 客户端的 `serverName`；空串表示
     * 部署里没有这一层，此时不做继承前缀的 deny 与守卫。
     */
    readonly inheritedServerName?: string;
    /**
     * 玩家面裁剪名单：这些工具对玩家子 agent 既不可见、也调不动。
     *
     * 自己那 5 个 `mcp__ra2_<自己>__*` 不受影响；名册派生的 `play_as_*` 会**自动**并进
     * 这份名单，不用（也不该）手写。名单里写了这个 session 里根本没有的名字不会让
     * 挂载失败——摘不掉的存在性检查与执行期守卫各管一段，见 README。
     */
    readonly playerDeny?: string[];
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
export declare const DEFAULT_PLAYER_DENY: readonly string[];
export declare const Config: z<Config>;
/** 加载时定下来、之后每次调用共用的事实。 */
export interface ResolvedConfig {
    /** 名册路径。 */
    readonly rosterPath: string;
    /** 子 agent provider 名。 */
    readonly provider: string;
    /** MCP 服务命令。 */
    readonly mcpCommand: string;
    /** MCP 服务模块。 */
    readonly mcpModule: string;
    /** MCP 服务工作目录。 */
    readonly mcpCwd: string;
    /** MCP 服务环境变量。 */
    readonly mcpEnv: Record<string, string>;
    /** 单次 MCP 调用超时（毫秒）。 */
    readonly toolCallTimeoutMs: number;
    /** 上层那份客户端的 serverName；空串表示没有这一层。 */
    readonly inheritedServerName: string;
    /** 配置里给的玩家面裁剪名单；名册派生的 `play_as_*` 由 {@link effectivePlayerDeny} 并进来。 */
    readonly playerDeny: readonly string[];
}
/**
 * 校验 schema 表达不了的事实。
 * @param config - 装载进来的配置。
 * @returns 补齐默认值并校验过的配置。
 * @throws {Error} 路径、provider、命令或者 serverName 不合法。
 */
export declare function resolveConfig(config: Config): ResolvedConfig;
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
export declare function effectivePlayerDeny(playerDeny: readonly string[], players: readonly RosterPlayer[]): string[];
/** 一次 `play_as_*` 调用的入参。 */
export interface PlayArgs {
    /** 交给这个子 agent 的初始任务。 */
    readonly task: string;
    /** 界面显示的短标签。 */
    readonly description: string;
}
/** 调用现场里本插件需要的那几个字段。 */
export interface PlayCall {
    /** 正在调用的 agent；没有它就没人能当子 agent 的父。 */
    readonly agent?: Agent | undefined;
    /** 调用方的取消信号。 */
    readonly signal: AbortSignal;
}
/** 一次 `play_as_*` 的结果，也是工具的规范返回值。 */
export interface PlayResult {
    /** 建出来的玩家子 agent id；`send_message` 用它继续对话。 */
    readonly subagentId: string;
    /** 这个子 agent 指挥的玩家名。 */
    readonly player: string;
}
/** 建玩家子 agent 需要的、加载时定下来的东西。 */
export interface PlayerRuntime {
    /** 插件自己的 ctx。 */
    readonly ctx: Context;
    /** 加载时解析好的配置。 */
    readonly resolved: ResolvedConfig;
    /** 玩家 → 子 agent 的进程内认领表。 */
    readonly claims: PlayerClaims;
}
/**
 * 给子 agent 的初始 prompt。
 * @param playerName - 玩家名。
 * @param task - 主持 agent 给的任务。
 * @returns 一段文本。
 */
export declare function initialPrompt(playerName: string, task: string): string;
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
export declare function startPlayerAgent(runtime: PlayerRuntime, player: RosterPlayer, args: PlayArgs, call: PlayCall): Promise<PlayResult>;
/**
 * 装载插件：读名册（读不了就在这里失败），给每个玩家注册一个工具，
 * 并在 `agent/created` 里给认领过的子 agent 挂上它自己的 MCP 客户端。
 * @param ctx - 带 `tools`、`subagents`、`agents` 的上下文。
 * @param config - 插件配置。
 * @throws {Error} 配置非法、名册读不了、玩家名派不出工具名，或者两名玩家撞名。
 */
export declare function apply(ctx: Context, config: Config): void;
/**
 * `apply` 的实现体，客户端插件由调用方给：生产传 `@deepseek-ai/dsh-mcp-client`，
 * 测试传替身，免得为了验一条隔离规则去起真的 MCP 服务进程。
 * @param ctx - 带 `tools`、`subagents`、`agents` 的上下文。
 * @param config - 插件配置。
 * @param client - 要挂进每个玩家 scope 的 MCP 客户端插件。
 * @throws {Error} 配置非法、名册读不了、玩家名派不出工具名，或者两名玩家撞名。
 */
export declare function mountPlayers(ctx: Context, config: Config, client: PlayerClientPlugin): void;
