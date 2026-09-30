/**
 * 玩家身份派生、进程内认领表，以及玩家 scope 里的 MCP 客户端挂载。
 *
 * 隔离是构造上的：每个玩家子 agent 只拿到自己那一份 MCP 客户端注册在**它自己
 * 的 scope 层**里的工具（`mcp__ra2_<玩家>__*`）；上层那份客户端继承下来的工具
 * （`mcp__<inheritedServerName>__*`）在它启动时被逐个 deny 掉，另外还有一道按
 * 前缀拦执行的守卫兜底。别的 agent 看不到这一份，这一份也看不到别的玩家的。
 *
 * @module @local/ra2-players/players
 */
import { createScope } from '@deepseek-ai/dsh-scope';
import { SessionId } from '@deepseek-ai/dsh-session';
/** 名册名字里允许出现的字符，小写之后。 */
const SLUG_PATTERN = /^[a-z0-9_]+$/;
/** `dsh-mcp-client` 对 `serverName` 的语法要求，原样复用。 */
const SERVER_NAME_PATTERN = /^[A-Za-z0-9_-]{1,32}$/;
/**
 * 把名册里的名字折成工具名与 serverName 用的片段。
 *
 * 名字里出现 `[a-z0-9_]` 之外的字符时在这里报错：与其生成一个非法的工具名，
 * 不如让插件加载失败。
 * @param name - 名册里的名字。
 * @returns 小写化的名字。
 * @throws {Error} 名字折不出合法片段。
 */
export function playerSlug(name) {
    const slug = name.toLowerCase();
    if (!SLUG_PATTERN.test(slug)) {
        throw new Error(`ra2-players: 玩家名 ${JSON.stringify(name)} 折成小写后是 ${JSON.stringify(slug)}，`
            + '含 [a-z0-9_] 之外的字符，派不出合法工具名——改名册里的名字，或者改这里的约定');
    }
    return slug;
}
/**
 * 一名玩家对应的工具名。
 * @param name - 名册里的名字。
 * @returns 形如 `play_as_alpha` 的工具名。
 */
export function playerToolName(name) {
    return `play_as_${playerSlug(name)}`;
}
/**
 * 一名玩家那一份 MCP 客户端的 `serverName`。
 * @param name - 名册里的名字。
 * @returns 形如 `ra2_alpha` 的 serverName。
 */
export function playerServerName(name) {
    return `ra2_${playerSlug(name)}`;
}
/**
 * 校验一名玩家派出的 serverName。
 * @param name - 名册里的名字。
 * @param inheritedServerName - 上层那份客户端的 serverName。
 * @returns 该玩家的 serverName。
 * @throws {Error} serverName 不合法，或者与上层那份撞名。
 */
export function checkedPlayerServerName(name, inheritedServerName) {
    const serverName = playerServerName(name);
    if (!SERVER_NAME_PATTERN.test(serverName)) {
        throw new Error(`ra2-players: 玩家 ${JSON.stringify(name)} 派出的 serverName ${JSON.stringify(serverName)} 不符合 [A-Za-z0-9_-]{1,32}`);
    }
    if (serverName === inheritedServerName) {
        throw new Error(`ra2-players: 玩家 ${JSON.stringify(name)} 的 serverName ${JSON.stringify(serverName)} 与上层的 serverName 相同，两份客户端会互相遮蔽`);
    }
    return serverName;
}
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
export function inheritedToolNames(ctx, caller, inheritedServerName) {
    if (inheritedServerName === '')
        return [];
    const prefix = `mcp__${inheritedServerName}__`;
    return ctx.tools.schemas(caller).map(schema => schema.name).filter(name => name.startsWith(prefix)).sort();
}
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
export class PlayerClaims {
    /** childId → 玩家名。挂载只看这张表。 */
    playerByChild = new Map();
    /** 玩家名 → 当前那次认领的 childId。重复调用看这张表。 */
    currentChildByPlayer = new Map();
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
    claim(player, childId, isLive) {
        const current = this.currentChildByPlayer.get(player);
        if (current !== undefined && isLive(SessionId(current))) {
            throw new Error(`ra2-players: ${player} 已经有一个在跑的玩家 agent（id ${current}）——`
                + '同一个玩家同一时刻只能有一个。用 send_message 给那个 agent 追加任务；'
                + '它空闲结算之后，再调一次这个工具才会认领新的 agent。');
        }
        this.playerByChild.set(childId, player);
        this.currentChildByPlayer.set(player, childId);
    }
    /**
     * 撤销一次认领；`startContinuable` 失败时回滚用。
     * @param childId - 要撤销的子 agent id。
     */
    release(childId) {
        const player = this.playerByChild.get(childId);
        this.playerByChild.delete(childId);
        if (player !== undefined && this.currentChildByPlayer.get(player) === childId) {
            this.currentChildByPlayer.delete(player);
        }
    }
    /**
     * 这次 childId 属于哪个玩家。
     * @param childId - 子 agent 的 id。
     * @returns 玩家名，或者 `undefined`（不是本插件建的 agent）。
     */
    playerOf(childId) {
        return this.playerByChild.get(childId);
    }
}
/**
 * 把一名玩家自己的 MCP 客户端挂进某个子 agent 的 scope。
 *
 * 三件事一起做，顺序有讲究：
 * 1. 先数一遍这个子 agent **此刻**继承来的 `mcp__<上层>__*`：这是父 preset 留给
 *    它的那一份客户端（没有 `--player`，连的是默认探针端口）。数完立刻
 *    `tools.restrict({ deny })`，让它们从工具表和提示里一起消失。`restrict` 只
 *    过滤继承面，不碰本层注册，所以下一步挂进来的本玩家工具不受影响。
 * 2. 注册一道 `tools/execute` 守卫：本玩家的工具只能由这个 agent 调；任何
 *    `mcp__<上层>__*` 一律拒绝——覆盖第 1 步之后才出现的名字。
 * 3. 再挂客户端插件，让它的工具注册在这个子 agent 自己的层里。
 *
 * 第 1 步看的是子 agent 自己的继承面，所以它和调用者视角无关；`play_as_*` 里
 * 还有一份按调用者视角算出的 deny 名单进 `toolFilter`，那份会随描述符持久化，
 * 用来兜住「进程重启后冷恢复」这种情况（那时内存里的认领表已经空了）。
 *
 * 挂载失败会把已经建出来的 scope 一并撤掉，并把失败抛给调用者——`agent/created`
 * 里抛出会连带否决这次子 agent 的建立，不会留下一个没有工具的玩家 agent。
 * @param ctx - 带 `tools` 的上下文（插件自己的 ctx）。
 * @param agent - 子 agent 对象本身；它同时是 scope key，所以必须是那一个对象。
 * @param plan - 这一份客户端的命名与配置。
 * @param client - 要挂的 MCP 客户端插件。
 * @returns 承载这次挂载的 scope；处置它就等于卸载这一份客户端、守卫与限制。
 */
export async function mountPlayerClient(ctx, agent, plan, client) {
    const ownPrefix = `mcp__${plan.serverName}__`;
    const inheritedPrefix = plan.inheritedServerName === '' ? '' : `mcp__${plan.inheritedServerName}__`;
    const scope = createScope(ctx, agent);
    try {
        if (inheritedPrefix !== '') {
            const inherited = ctx.tools.schemas(agent).map(schema => schema.name)
                .filter(name => name.startsWith(inheritedPrefix) && !name.startsWith(ownPrefix));
            if (inherited.length > 0)
                scope.ctx.tools.restrict({ deny: inherited });
        }
        scope.ctx.on('tools/execute', async (exec, next) => {
            if (exec.name.startsWith(ownPrefix)) {
                if (exec.agent !== agent) {
                    // 同名但定义不同，说明那是另一个 scope 的注册，交给它自己的守卫处理。
                    if (ctx.tools.get(exec.name, exec.agent) !== ctx.tools.get(exec.name, agent))
                        return next();
                    throw new Error(`${plan.serverName}: 这个玩家工具属于另一个 Session`);
                }
                return next();
            }
            if (inheritedPrefix !== '' && exec.name.startsWith(inheritedPrefix)) {
                throw new Error(`${plan.serverName}: ${exec.name} 来自继承的 ${inheritedPrefix}* 客户端，不属于本玩家，已拒绝`);
            }
            return next();
        });
        await scope.ctx.plugin(client, plan.configure(agent.id));
    }
    catch (error) {
        await scope.dispose();
        throw error;
    }
    return scope;
}
