/** Session selection and durable wake delivery for the ra2 game agent. */
import { createUserMessage } from '@deepseek-ai/dsh-llm';
import { SessionId } from '@deepseek-ai/dsh-session';
/** Whether one live Agent's tool view carries this MCP server's tools. */
function carriesMcpTools(ctx, agent, toolPrefix) {
    return ctx.tools.schemas(agent).some(tool => tool.name.startsWith(toolPrefix));
}
/** Render candidate identities for an ambiguity diagnostic. */
function renderCandidates(candidates) {
    return candidates.map(agent => `"${agent.id}"`).join(', ');
}
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
export function selectSession(ctx, targeting, requested) {
    if (requested !== undefined)
        return { sessionId: SessionId(requested) };
    const mounted = ctx.agents.roots().filter(agent => carriesMcpTools(ctx, agent, targeting.mcpToolPrefix));
    const idle = mounted.filter(agent => agent.status === 'idle');
    const only = idle.length === 1 ? idle[0] : undefined;
    if (only !== undefined)
        return { sessionId: only.id };
    const fallback = targeting.fallbackSession;
    if (fallback !== '')
        return { sessionId: SessionId(fallback) };
    if (mounted.length === 0) {
        return {
            error: `没有挂 ${targeting.mcpToolPrefix}* 工具的会话；在请求里带 session，或配置 fallbackSession`,
        };
    }
    if (idle.length === 0) {
        return {
            error: `挂了 ${targeting.mcpToolPrefix}* 工具的会话都在跑（${renderCandidates(mounted)}）；`
                + '在请求里带 session，或配置 fallbackSession',
        };
    }
    return {
        error: `有 ${String(idle.length)} 个空闲候选会话（${renderCandidates(idle)}）；`
            + '在请求里带 session，或配置 fallbackSession',
    };
}
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
export async function deliverWake(ctx, sessionId, request) {
    try {
        const resolved = await ctx.sessionController.resolveAgent(sessionId);
        if ('error' in resolved) {
            return { ok: false, error: `会话 "${sessionId}" 无法解析：${resolved.error.message}` };
        }
        const message = createUserMessage({
            content: [{ type: 'text', text: request.text }],
            source: {
                kind: 'ra2-wake',
                ...request.frame === undefined ? {} : { frame: request.frame },
                ...request.tactic === undefined ? {} : { tactic: request.tactic },
            },
        });
        // followup appends the inbox splice synchronously and wakes the driver.
        resolved.agent.followup(message);
        const flushed = await ctx.sessions.flush(resolved.agent.session);
        if (!flushed) {
            return { ok: false, error: '会话持久化没有确认这条唤醒（没有 session/flush 监听者）' };
        }
        return { ok: true, session: resolved.agent.id };
    }
    catch (error) {
        return { ok: false, error: `唤醒 "${sessionId}" 失败：${error instanceof Error ? error.message : String(error)}` };
    }
}
