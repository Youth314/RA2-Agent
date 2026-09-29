/** Session selection and durable wake delivery for the ra2 game agent. */
import type { Context } from '@deepseek-ai/cordis';
import type { ContextFormed } from '@deepseek-ai/dsh-llm';
import { SessionId } from '@deepseek-ai/dsh-session';
declare module '@deepseek-ai/dsh-llm' {
    interface MessageSourceMap {
        /** Programmatic input admitted from one external wake request. */
        'ra2-wake': {
            readonly kind: 'ra2-wake';
            /** Game frame the tactic observed when it decided to wake the model. */
            readonly frame?: number;
            /** Tactic that raised the wake. */
            readonly tactic?: string;
        } & ContextFormed;
    }
}
/** One validated wake request. */
export interface WakeRequest {
    /** Model-visible message text; the ra2 side owns its wording. */
    readonly text: string;
    /** Game frame the tactic observed. */
    readonly frame?: number;
    /** Tactic that raised the wake. */
    readonly tactic?: string;
    /** Explicit Session identity; when present no discovery happens. */
    readonly session?: string;
}
/** Session-selection inputs fixed at plugin load. */
export interface WakeTargeting {
    /** `mcp__<serverName>__` prefix of the MCP tools the target Session must carry. */
    readonly mcpToolPrefix: string;
    /** Session identity used when discovery finds zero or several candidates; `''` disables the fallback. */
    readonly fallbackSession: string;
}
/** One delivery attempt's result, shaped for the HTTP response body. */
export type WakeOutcome = {
    readonly ok: true;
    readonly session: string;
} | {
    readonly ok: false;
    readonly error: string;
};
/** Selected target or the reason no single Session could be chosen. */
type WakeTarget = {
    readonly sessionId: SessionId;
} | {
    readonly error: string;
};
/**
 * Choose the one Session a wake request targets.
 *
 * An explicit request Session wins unconditionally. Otherwise the idle
 * top-level agents carrying this MCP server's tools are candidates: exactly one
 * is used, and zero or several fall back to the configured Session identity.
 * @param ctx - Host context carrying live Agents and the tool registry.
 * @param targeting - MCP tool prefix and configured fallback identity.
 * @param requested - Session identity supplied by the request, if any.
 * @returns the chosen identity, or the reason selection failed.
 */
export declare function selectSession(ctx: Context, targeting: WakeTargeting, requested: string | undefined): WakeTarget;
/**
 * Append one message and open a turn on the chosen Session.
 *
 * The message enters the durable log as a user-role message, so the wake
 * survives reload and compaction like any other admitted input. Delivery is
 * reported successful only after `sessions.flush()` confirms a durability
 * listener committed it.
 * @param ctx - Host context carrying Session resolution and persistence.
 * @param sessionId - Session to wake.
 * @param request - validated wake content.
 * @returns the acknowledged delivery, or the concrete failure.
 */
export declare function deliverWake(ctx: Context, sessionId: SessionId, request: WakeRequest): Promise<WakeOutcome>;
export {};
