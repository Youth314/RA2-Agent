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
/** 名册里的一方。 */
export interface RosterPlayer {
    /** 名册里的名字；同时是 `--player` 的取值。 */
    readonly name: string;
}
/** 校验过的名册。 */
export interface Roster {
    /** 名册里的全部玩家，保持文件里的顺序。 */
    readonly players: readonly RosterPlayer[];
}
/** 名册不可用：文件读不了、不是 JSON、或者结构不符合约定。 */
export declare class RosterError extends Error {
    readonly name = "RosterError";
    constructor(message: string, options?: {
        readonly cause?: unknown;
    });
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
export declare function parseRoster(source: string, path: string): Roster;
/**
 * 从磁盘读取并校验名册。
 * @param path - 名册文件的绝对路径。
 * @returns 校验过的名册。
 * @throws {RosterError} 文件不存在或读不了，或者内容不符合约定。
 */
export declare function readRoster(path: string): Roster;
