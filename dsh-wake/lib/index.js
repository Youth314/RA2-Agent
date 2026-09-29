/**
 * Local HTTP wake bridge: an external process injects one user-role message
 * that opens a turn in a chosen DSH Session.
 *
 * @module @local/ra2-wake
 */
import { timingSafeEqual } from 'node:crypto';
import { credentialRef } from '@deepseek-ai/dsh-credentials';
import z from '@deepseek-ai/schemastery';
import { deliverWake, selectSession } from "./binding.js";
import { isJsonContentType, readBoundedUtf8Body, sendJson, WakeHttpError } from "./http.js";
/** Cordis function-plugin name. */
export const name = 'ra2-wake';
/** Host services required before the wake route can register. */
export const inject = ['webServer', 'sessions', 'agents', 'tools', 'sessionController'];
/** Request header carrying the configured shared secret. */
const SECRET_HEADER = 'x-ra2-wake-secret';
/** Default route path; a deployment overrides it through `path`. */
const DEFAULT_PATH = '/ra2/wake';
/** Default raw-body ceiling in bytes; large enough for one sentence with game context. */
const DEFAULT_MAX_BODY_BYTES = 8192;
/** Default MCP server namespace of the ra2 game tools. */
const DEFAULT_MCP_SERVER_NAME = 'ra2';
/** `serverName` grammar enforced by `@deepseek-ai/dsh-mcp-client`, reused for the tool prefix. */
const MCP_SERVER_NAME_PATTERN = /^[A-Za-z0-9_-]{1,32}$/;
export const Config = z.object({
    path: z.string().default(DEFAULT_PATH),
    maxBodyBytes: z.number().step(1).min(1).max(1_048_576).default(DEFAULT_MAX_BODY_BYTES),
    mcpServerName: z.string().default(DEFAULT_MCP_SERVER_NAME),
    fallbackSession: z.string().default(''),
    secretEnv: z.string().default(''),
});
/** Validate route, namespace, and fallback facts the schema cannot express. */
function resolveConfig(config) {
    const path = config.path ?? DEFAULT_PATH;
    if (!path.startsWith('/') || path === '/' || path.endsWith('/')
        || path.includes('?') || path.includes('#')) {
        throw new Error('ra2-wake path must be an absolute non-root pathname without a trailing slash, query, or fragment');
    }
    const mcpServerName = config.mcpServerName ?? DEFAULT_MCP_SERVER_NAME;
    if (!MCP_SERVER_NAME_PATTERN.test(mcpServerName)) {
        throw new Error('ra2-wake mcpServerName must match [A-Za-z0-9_-]{1,32}');
    }
    const fallbackSession = (config.fallbackSession ?? '').trim();
    if (fallbackSession !== (config.fallbackSession ?? '')) {
        throw new Error('ra2-wake fallbackSession must not carry surrounding whitespace');
    }
    const secretEnv = (config.secretEnv ?? '').trim();
    if (secretEnv !== '') {
        try {
            credentialRef(secretEnv);
        }
        catch (error) {
            throw new Error(`ra2-wake secretEnv is not a credential reference: ${String(error)}`);
        }
    }
    return {
        path,
        maxBodyBytes: config.maxBodyBytes ?? DEFAULT_MAX_BODY_BYTES,
        secretEnv,
        targeting: { mcpToolPrefix: `mcp__${mcpServerName}__`, fallbackSession },
    };
}
/** Parse and bound one wake request body. */
function parseWakeRequest(body) {
    let parsed;
    try {
        parsed = JSON.parse(body);
    }
    catch {
        // JSON.parse is the only statement in the try; no other failure is normalized.
        throw new WakeHttpError(400, '请求体不是合法 JSON');
    }
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new WakeHttpError(400, '请求体必须是 JSON 对象');
    }
    const record = parsed;
    const text = record['text'];
    if (typeof text !== 'string' || text.trim() === '') {
        throw new WakeHttpError(400, 'text 必须是非空字符串');
    }
    const frame = record['frame'];
    if (frame !== undefined && (typeof frame !== 'number' || !Number.isSafeInteger(frame))) {
        throw new WakeHttpError(400, 'frame 必须是整数');
    }
    const tactic = record['tactic'];
    if (tactic !== undefined && typeof tactic !== 'string') {
        throw new WakeHttpError(400, 'tactic 必须是字符串');
    }
    const session = record['session'];
    if (session !== undefined && typeof session !== 'string') {
        throw new WakeHttpError(400, 'session 必须是字符串');
    }
    return {
        text,
        ...frame === undefined ? {} : { frame: frame },
        ...tactic === undefined || tactic === '' ? {} : { tactic: tactic },
        ...session === undefined || session.trim() === '' ? {} : { session: session.trim() },
    };
}
/** Compare the presented secret with the configured one without leaking length-independent timing. */
function secretMatches(expected, presented) {
    const left = Buffer.from(expected, 'utf8');
    const right = Buffer.from(presented, 'utf8');
    return left.byteLength === right.byteLength && timingSafeEqual(left, right);
}
/** Require the configured shared secret on one request. */
async function assertSecret(ctx, request, secretEnv) {
    const credentials = ctx.get('credentials');
    if (credentials === undefined) {
        throw new WakeHttpError(503, `secretEnv 配置为 ${secretEnv}，但 credentials 服务不可用`);
    }
    const credential = await credentials.resolve(credentialRef(secretEnv));
    if (credential === undefined || credential.value === '') {
        throw new WakeHttpError(503, `共享密钥 ${secretEnv} 不可用`);
    }
    const presented = request.headersDistinct[SECRET_HEADER];
    if (presented?.length !== 1 || presented[0] === undefined) {
        throw new WakeHttpError(401, `缺少 ${SECRET_HEADER} 请求头`);
    }
    if (!secretMatches(credential.value, presented[0])) {
        throw new WakeHttpError(401, '共享密钥不匹配');
    }
}
/**
 * Create the wake route handler.
 * @param ctx - Host context carrying Agent, Session, tool, and persistence services.
 * @param config - load-time resolved route and targeting values.
 * @returns an HTTP handler that answers after delivery is acknowledged.
 */
function createWakeHandler(ctx, config) {
    return async (request, response) => {
        try {
            if (request.method !== 'POST') {
                response.setHeader('allow', 'POST');
                throw new WakeHttpError(405, '只接受 POST');
            }
            if (!isJsonContentType(request.headers['content-type'])) {
                throw new WakeHttpError(415, 'content-type 必须是 application/json');
            }
            if (config.secretEnv !== '')
                await assertSecret(ctx, request, config.secretEnv);
            const body = await readBoundedUtf8Body(request, config.maxBodyBytes);
            const wake = parseWakeRequest(body);
            const target = selectSession(ctx, config.targeting, wake.session);
            if ('error' in target) {
                sendJson(response, 200, { ok: false, error: target.error });
                return;
            }
            const outcome = await deliverWake(ctx, target.sessionId, wake);
            if (!outcome.ok)
                ctx.logger.warn(`ra2-wake: ${outcome.error}`);
            sendJson(response, 200, outcome);
        }
        catch (error) {
            if (error instanceof WakeHttpError) {
                sendJson(response, error.status, { ok: false, error: error.message });
                return;
            }
            ctx.logger.warn(`ra2-wake: request failed: ${error instanceof Error ? error.message : String(error)}`);
            sendJson(response, 503, { ok: false, error: 'wake 路由内部错误' });
        }
    };
}
/**
 * Register one local wake endpoint on the injected WebServer.
 *
 * A shared secret is optional; without one, the route refuses to register
 * unless the WebServer is bound to the loopback literal.
 * @param ctx - Host context carrying the WebServer and Session capabilities.
 * @param config - validated wake-bridge configuration.
 * @throws when the configuration is invalid or an unauthenticated route would be exposed off-loopback.
 */
export function apply(ctx, config) {
    const resolved = resolveConfig(config);
    if (resolved.secretEnv === '' && ctx.webServer.host !== '127.0.0.1') {
        throw new Error(`ra2-wake refuses to serve an unauthenticated wake route on ${ctx.webServer.host}; `
            + 'bind the WebServer to 127.0.0.1 or configure secretEnv');
    }
    const route = {
        kind: 'exact',
        path: resolved.path,
        handler: createWakeHandler(ctx, resolved),
    };
    ctx.effect(() => ctx.webServer.register(route), `ra2-wake: ${resolved.path}`);
}
