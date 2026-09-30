/**
 * 对局名册（`config/match.json`）的读取与校验。
 *
 * 这里只读**名字**。游戏目录与探针端口不复制过来：它们由
 * `python3 -m ra2agent.mcp --player <名字>` 用同一份名册自己解析
 * （`ra2agent.mcp.resolve_player`）。TS 侧只用名字派生出工具名与 MCP 客户端的
 * `serverName`，所以名册的这个子集是唯一需要在这里校验的事实。
 *
 * @module @local/ra2-players/roster
 */
import { readFileSync } from 'node:fs';
/** 名册不可用：文件读不了、不是 JSON、或者结构不符合约定。 */
export class RosterError extends Error {
    name = 'RosterError';
    constructor(message, options) {
        super(message, options);
    }
}
/** 是不是一个非 null 的普通对象（不是数组）。 */
function isRecord(value) {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
}
/**
 * 校验一份名册文本。
 *
 * 认不出的结构一律报错，不静默忽略——名册读错会让两个玩家共用一份游戏目录，
 * 那比插件不加载危险得多。
 * @param source - `config/match.json` 的文本内容。
 * @param path - 内容的来源路径，只用于诊断。
 * @returns 校验过的名册。
 * @throws {RosterError} 不是 JSON 对象、`players` 不是数组、玩家名字非法或重复。
 */
export function parseRoster(source, path) {
    let parsed;
    try {
        parsed = JSON.parse(source);
    }
    catch (error) {
        // JSON.parse 是这个 try 里唯一的语句，别的失败不该被当成解析失败。
        throw new RosterError(`名册 ${path} 不是合法 JSON`, { cause: error });
    }
    if (!isRecord(parsed)) {
        throw new RosterError(`名册 ${path} 的顶层必须是一个 JSON 对象`);
    }
    const raw = parsed['players'];
    if (!Array.isArray(raw)) {
        throw new RosterError(`名册 ${path} 缺少 players 数组`);
    }
    if (raw.length === 0) {
        throw new RosterError(`名册 ${path} 的 players 是空的：没有玩家就没有 play_as_* 工具`);
    }
    const players = [];
    const seen = new Map();
    for (const [index, entry] of raw.entries()) {
        if (!isRecord(entry)) {
            throw new RosterError(`名册 ${path} 的第 ${String(index + 1)} 个参与者不是 JSON 对象`);
        }
        const name = entry['name'];
        if (typeof name !== 'string' || name === '') {
            throw new RosterError(`名册 ${path} 的第 ${String(index + 1)} 个参与者缺少非空字符串 name`);
        }
        if (name.trim() !== name) {
            throw new RosterError(`名册 ${path} 的参与者名字 ${JSON.stringify(name)} 带了首尾空白`);
        }
        // 工具名与 serverName 都是名字小写后的函数，两个只差大小写的名字会撞在一起。
        const folded = name.toLowerCase();
        const previous = seen.get(folded);
        if (previous !== undefined) {
            throw new RosterError(`名册 ${path} 里 ${JSON.stringify(previous)} 与 ${JSON.stringify(name)} 会派生出同一个工具名`);
        }
        seen.set(folded, name);
        players.push({ name });
    }
    return { players };
}
/**
 * 从磁盘读取并校验名册。
 * @param path - 名册文件的绝对路径。
 * @returns 校验过的名册。
 * @throws {RosterError} 文件不存在或读不了，或者内容不符合约定。
 */
export function readRoster(path) {
    let source;
    try {
        source = readFileSync(path, 'utf8');
    }
    catch (error) {
        // readFileSync 是这个 try 里唯一的语句。
        throw new RosterError(`名册 ${path} 读不了：${error instanceof Error ? error.message : String(error)}`, { cause: error });
    }
    return parseRoster(source, path);
}
