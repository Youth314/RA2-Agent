/**
 * 玩家身份派生、进程内认领表，以及玩家 scope 里的客户端挂载与玩家面裁剪。
 *
 * 隔离是构造上的，三层：
 *
 * 1. 每个玩家子 agent 只拿到自己那一份 MCP 客户端注册在**它自己的 scope 层**里的
 *    工具（`mcp__ra2_<玩家>__*`）；别的 agent 看不到这一份。
 * 2. 继承面被 `tools.restrict` 剪掉：上层那份客户端（`mcp__<inheritedServerName>__*`）
 *    加上玩家面名单里的工具，都从模型视野里消失。
 * 3. 一道 `tools/execute` 守卫按名字拦执行。它不受第 2 层的限制——`restrict` 只能
 *    过滤**继承面**，摘不掉注册在这个 agent 本层的工具（例如 `tool-subagent` 打开了
 *    `modelSelectionSettings` 之后按 agent 注册的 `subagent`），也拦不住第 2 层之后
 *    才出现的名字。守卫两样都管。
 *
 * @module @local/ra2-players/players
 */
import type { Context } from '@deepseek-ai/cordis';
import type { Config as McpClientConfig } from '@deepseek-ai/dsh-mcp-client';
import type { Scope, ScopeKey } from '@deepseek-ai/dsh-scope';
import { SessionId } from '@deepseek-ai/dsh-session';
/** 可作为玩家 scope 主体传进来的一方；只需要身份和作为 scope key 的对象同一性。 */
export interface PlayerScopeSubject extends ScopeKey {
    /** 子 agent 的 id，等于它的 session id。 */
    readonly id: SessionId;
}
/** 可挂载的 MCP 客户端插件；生产用 `@deepseek-ai/dsh-mcp-client` 的命名空间。 */
export interface PlayerClientPlugin {
    /** Cordis 插件名，只用于诊断。 */
    readonly name?: string;
    /** 这个客户端要求的服务。 */
    readonly inject?: string[];
    /**
     * 挂载一个客户端实例。
     * @param ctx - 玩家 scope 的 ctx。
     * @param config - 该实例的传输与命名配置。
     */
    apply(ctx: Context, config: McpClientConfig): unknown;
}
/** 一名玩家的一份客户端挂载方案。 */
export interface PlayerClientPlan {
    /** 这一份客户端的 `serverName`；它的工具名以 `mcp__<serverName>__` 开头。 */
    readonly serverName: string;
    /**
     * 上层（主持 agent 继承来的）那份客户端的 `serverName`。
     * 空串表示部署里没有这一层，此时不装继承前缀守卫。
     */
    readonly inheritedServerName: string;
    /**
     * 玩家面名单：这些名字对玩家子 agent 既不可见、也调不动。
     *
     * 与「继承面 MCP deny」是两份名单，两份都生效；名单里写了这个 scope 里根本没有的
     * 名字不会让挂载失败（见 {@link mountPlayerClient}）。
     */
    readonly deny: readonly string[];
    /**
     * 用子 agent 的 childId 配出插件配置。
     * @param childId - 子 agent 的 id，也是唤醒要投递到的会话。
     * @returns 校验过的 MCP 客户端配置。
     */
    readonly configure: (childId: SessionId) => McpClientConfig;
}
/** 一次玩家客户端挂载的结果。 */
export interface PlayerMount {
    /** 承载这次挂载的 scope；处置它就等于卸载客户端、守卫与限制。 */
    readonly scope: Scope;
    /** 成功用 `tools.restrict` 从模型视野里摘掉的名字。 */
    readonly hidden: readonly string[];
    /**
     * 名字确实存在，但 `restrict` 摘不掉（注册在这个 agent 的**本层**），
     * 只能靠执行期守卫拦的名字。
     */
    readonly guardOnly: readonly string[];
    /** 名单里有、但挂载时这个 scope 里根本没有的名字。 */
    readonly absent: readonly string[];
    /** 卸载这一份客户端、守卫与限制。 */
    dispose(): Promise<void>;
}
/**
 * 把名册里的名字折成工具名与 serverName 用的片段。
 *
 * 名字里出现 `[a-z0-9_]` 之外的字符时在这里报错：与其生成一个非法的工具名，
 * 不如让插件加载失败。
 * @param name - 名册里的名字。
 * @returns 小写化的名字。
 * @throws {Error} 名字折不出合法片段。
 */
export declare function playerSlug(name: string): string;
/**
 * 一名玩家对应的工具名。
 * @param name - 名册里的名字。
 * @returns 形如 `play_as_alpha` 的工具名。
 */
export declare function playerToolName(name: string): string;
/**
 * 一名玩家那一份 MCP 客户端的 `serverName`。
 * @param name - 名册里的名字。
 * @returns 形如 `ra2_alpha` 的 serverName。
 */
export declare function playerServerName(name: string): string;
/**
 * 校验一名玩家派出的 serverName。
 * @param name - 名册里的名字。
 * @param inheritedServerName - 上层那份客户端的 serverName。
 * @returns 该玩家的 serverName。
 * @throws {Error} serverName 不合法，或者与上层那份撞名。
 */
export declare function checkedPlayerServerName(name: string, inheritedServerName: string): string;
/**
 * 调用者此刻能看见的、上层那份客户端留下的工具名。
 *
 * 建子 agent 之前用它算出要给子 agent deny 掉的名字：子 agent 继承父的 preset，
 * 也就继承了这一份客户端，而那份客户端连的是**没有 `--player` 的默认服务**，
 * 谁都能指挥。deny 名单进 `toolFilter`，随描述符持久化，冷恢复时会重新生效。
 * @param ctx - 带 `tools` 的上下文。
 * @param caller - 正在调用 `play_as_*` 的 agent（它自己的 scope key）。
 * @param inheritedServerName - 上层那份客户端的 serverName；空串返回空数组。
 * @returns 排好序的工具名；调用者看不到这一层时为空数组。
 */
export declare function inheritedToolNames(ctx: Context, caller: ScopeKey, inheritedServerName: string): string[];
/**
 * 玩家 → 子 agent 的进程内认领表。
 *
 * 身份必须在 `startContinuable` **之前**写好：`agent/created` 可能在它返回之前
 * 就触发，而挂载只认表里的 childId。认领不会因为子 agent 结算而删除——continuable
 * 子 agent 空闲后会结算（agent 被处置），之后 `send_message` 会冷恢复**同一个**
 * childId，那时还要按这张表把客户端重新挂上。
 *
 * 进程重启后这张表是空的：已经挂好的子 agent 不受影响，但新出现的 agent 归属要
 * 重新认领（见 README 的 Known Limitations）。
 */
export declare class PlayerClaims {
    /** childId → 玩家名。挂载只看这张表。 */
    private readonly playerByChild;
    /** 玩家名 → 当前那次认领的 childId。重复调用看这张表。 */
    private readonly currentChildByPlayer;
    /**
     * 认领一个 childId。
     *
     * 同一玩家已经有一个**活着的**玩家 agent 时拒绝（并说明是谁）；上一个已经
     * 结算（agent 已处置）时，这次调用顶替它。整个判断是同步的：检查与写入之间
     * 没有 await，所以并发调用不会同时通过。
     * @param player - 玩家名。
     * @param childId - 这次调用自己生成的子 agent id。
     * @param isLive - 判断某个 childId 现在是否还有活着的 agent。
     * @throws {Error} 该玩家已有在跑的玩家 agent。
     */
    claim(player: string, childId: SessionId, isLive: (childId: SessionId) => boolean): void;
    /**
     * 撤销一次认领；`startContinuable` 失败时回滚用。
     * @param childId - 要撤销的子 agent id。
     */
    release(childId: SessionId): void;
    /**
     * 这次 childId 属于哪个玩家。
     * @param childId - 子 agent 的 id。
     * @returns 玩家名，或者 `undefined`（不是本插件建的 agent）。
     */
    playerOf(childId: SessionId): string | undefined;
}
/**
 * 把一名玩家自己的 MCP 客户端挂进某个子 agent 的 scope，并做玩家面裁剪。
 *
 * 四件事一起做，顺序有讲究：
 * 1. 先数一遍这个子 agent **此刻**看得见的名字，作为后面「存在性」判断的依据。
 * 2. 剪继承面：上层那份客户端留下的 `mcp__<上层>__*`，加上玩家面名单 `plan.deny`
 *    里的名字，逐个 `tools.restrict({ deny })`，让它们从工具表和提示里一起消失。
 *    `restrict` 只过滤继承面、不碰本层注册，所以下一步挂进来的本玩家工具不受影响；
 *    摘不掉的名字不报错，落进返回报告的 `guardOnly`（见 {@link hideFromInherited}）。
 * 3. 注册一道 `tools/execute` 守卫：本玩家的工具只能由这个 agent 调；`mcp__*` 里
 *    不属于本玩家的、以及 `plan.deny` 里的任何名字，一律拒绝执行。它不区分注册层，
 *    所以本层注册的 `subagent`、以及第 2 步之后才出现的名字都在它的覆盖内。
 * 4. 再挂客户端插件，让它的工具注册在这个子 agent 自己的层里。
 *
 * 第 2 步看的是子 agent 自己的视野，与调用者视角无关；`play_as_*` 里另有一份按调用者
 * 视角算出的 MCP deny 名单进 `toolFilter`，那份随描述符持久化，用来兜住跨进程重启的
 * 冷恢复（那时内存里的认领表已经空了，这份裁剪也不会被重新挂上）。
 *
 * 挂载失败会把已经建出来的 scope 一并撤掉，并把失败抛给调用者——`agent/created`
 * 里抛出会连带否决这次子 agent 的建立，不会留下一个没有工具的玩家 agent。
 * @param ctx - 带 `tools` 的上下文（插件自己的 ctx）。
 * @param agent - 子 agent 对象本身；它同时是 scope key，所以必须是那一个对象。
 * @param plan - 这一份客户端的命名、玩家面名单与配置。
 * @param client - 要挂的 MCP 客户端插件。
 * @returns 挂载结果：scope 与三类名字的清单（可见性摘掉的 / 只能守卫拦的 / 不存在的）。
 */
export declare function mountPlayerClient(ctx: Context, agent: PlayerScopeSubject, plan: PlayerClientPlan, client: PlayerClientPlugin): Promise<PlayerMount>;
