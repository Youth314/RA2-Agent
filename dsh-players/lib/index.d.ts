/**
 * 主持 agent 开一局：给名册里的每个玩家各注册一个 `play_as_<玩家>` 工具，
 * 每个工具建一个**只指挥那一方**的 continuable 子 agent，并给它挂一份自己的
 * RA2 MCP 客户端。
 *
 * 隔离是构造上的：子 agent 的工具表里只有它自己那一份客户端的工具
 * （`mcp__ra2_<玩家>__*`），父 preset 留下来的那一份（`mcp__ra2__*`，连的是
 * 没有 `--player` 的默认服务）在它建立时被 deny 掉，另有一道按前缀拦执行的守卫。
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
}
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
}
/**
 * 校验 schema 表达不了的事实。
 * @param config - 装载进来的配置。
 * @returns 补齐默认值并校验过的配置。
 * @throws {Error} 路径、provider、命令或者 serverName 不合法。
 */
export declare function resolveConfig(config: Config): ResolvedConfig;
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
