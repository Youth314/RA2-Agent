/** Bounded request intake and JSON responses for one local wake route. */
/**
 * Request-level refusal. Its message is safe to return to the caller because
 * it never echoes request content.
 */
export class WakeHttpError extends Error {
    status;
    name = 'WakeHttpError';
    constructor(status, message) {
        super(message);
        this.status = status;
    }
}
/**
 * Whether Content-Type names JSON with at most one UTF-8 charset parameter.
 * @param value - raw `content-type` header value.
 * @returns true when the request declares plain JSON.
 */
export function isJsonContentType(value) {
    if (value === undefined)
        return false;
    const parts = value.split(';').map(part => part.trim());
    const [mediaType, parameter, ...extra] = parts;
    if (mediaType?.toLowerCase() !== 'application/json')
        return false;
    if (parameter === undefined)
        return true;
    return extra.length === 0 && /^charset=(?:utf-8|"utf-8")$/i.test(parameter);
}
/** Parse a decimal Content-Length or reject an ambiguous header. */
function contentLength(request) {
    const value = request.headers['content-length'];
    if (value === undefined)
        return undefined;
    if (!/^(0|[1-9]\d*)$/.test(value))
        throw new WakeHttpError(400, 'Content-Length 不是十进制字节数');
    const length = Number(value);
    if (!Number.isSafeInteger(length))
        throw new WakeHttpError(413, '请求体过大');
    return length;
}
/**
 * Read one request body as exact, bounded UTF-8 text.
 * @param request - incoming request before any parser consumes it.
 * @param maxBodyBytes - positive byte ceiling.
 * @returns the decoded body after EOF.
 * @throws {WakeHttpError} for an invalid length, excessive bytes, invalid UTF-8, or an aborted stream.
 */
export async function readBoundedUtf8Body(request, maxBodyBytes) {
    const declared = contentLength(request);
    if (declared !== undefined && declared > maxBodyBytes) {
        request.resume();
        throw new WakeHttpError(413, `请求体超过上限 ${String(maxBodyBytes)} 字节`);
    }
    const chunks = [];
    let size = 0;
    try {
        for await (const raw of request) {
            const chunk = Buffer.isBuffer(raw) ? raw : Buffer.from(raw);
            size += chunk.byteLength;
            if (size > maxBodyBytes) {
                request.resume();
                throw new WakeHttpError(413, `请求体超过上限 ${String(maxBodyBytes)} 字节`);
            }
            chunks.push(chunk);
        }
    }
    catch (error) {
        if (error instanceof WakeHttpError)
            throw error;
        throw new WakeHttpError(400, '请求体读取中断');
    }
    if (!request.complete)
        throw new WakeHttpError(400, '请求体读取中断');
    try {
        return new TextDecoder('utf-8', { fatal: true }).decode(Buffer.concat(chunks, size));
    }
    catch {
        // TextDecoder is the only statement in the try; the body must be valid UTF-8.
        throw new WakeHttpError(400, '请求体不是合法 UTF-8');
    }
}
/**
 * Send one JSON body exactly once.
 * @param response - response owning the socket.
 * @param status - HTTP status code.
 * @param body - JSON-serializable value.
 */
export function sendJson(response, status, body) {
    const text = JSON.stringify(body);
    response.writeHead(status, {
        'content-type': 'application/json; charset=utf-8',
        'content-length': Buffer.byteLength(text),
    });
    response.end(text);
}
