/**
 * Local HTTP wake bridge: an external process injects one user-role message
 * that opens a turn in a chosen DSH Session.
 *
 * @module @local/ra2-wake
 */
import type { Context } from '@deepseek-ai/cordis';
import z from '@deepseek-ai/schemastery';
/** Cordis function-plugin name. */
export declare const name = "ra2-wake";
/** Host services required before the wake route can register. */
export declare const inject: string[];
/** Wake-bridge configuration. */
export interface Config {
    /** Exact absolute route path; defaults to `/ra2/wake`. */
    readonly path?: string;
    /** Raw request-body ceiling in bytes; defaults to 8192. */
    readonly maxBodyBytes?: number;
    /** MCP server namespace whose tools identify a winnable Session; defaults to `ra2`. */
    readonly mcpServerName?: string;
    /** Session identity used when discovery is ambiguous; `''` (the default) reports the ambiguity instead. */
    readonly fallbackSession?: string;
    /** Credential reference holding the shared secret; `''` (the default) allows loopback-only serving. */
    readonly secretEnv?: string;
}
export declare const Config: z<Config>;
/**
 * Register one local wake endpoint on the injected WebServer.
 *
 * A shared secret is optional; without one, the route refuses to register
 * unless the WebServer is bound to the loopback literal.
 * @param ctx - Host context carrying the WebServer and Session capabilities.
 * @param config - validated wake-bridge configuration.
 * @throws when the configuration is invalid or an unauthenticated route would be exposed off-loopback.
 */
export declare function apply(ctx: Context, config: Config): void;
