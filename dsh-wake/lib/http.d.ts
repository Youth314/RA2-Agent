/** Bounded request intake and JSON responses for one local wake route. */
import type { IncomingMessage, ServerResponse } from 'node:http';
/**
 * Request-level refusal. Its message is safe to return to the caller because
 * it never echoes request content.
 */
export declare class WakeHttpError extends Error {
    readonly status: 400 | 401 | 405 | 413 | 415 | 503;
    readonly name = "WakeHttpError";
    constructor(status: 400 | 401 | 405 | 413 | 415 | 503, message: string);
}
/**
 * Whether Content-Type names JSON with at most one UTF-8 charset parameter.
 * @param value - raw `content-type` header value.
 * @returns true when the request declares plain JSON.
 */
export declare function isJsonContentType(value: string | undefined): boolean;
/**
 * Read one request body as exact, bounded UTF-8 text.
 * @param request - incoming request before any parser consumes it.
 * @param maxBodyBytes - positive byte ceiling.
 * @returns the decoded body after EOF.
 * @throws {WakeHttpError} for an invalid length, excessive bytes, invalid UTF-8, or an aborted stream.
 */
export declare function readBoundedUtf8Body(request: IncomingMessage, maxBodyBytes: number): Promise<string>;
/**
 * Send one JSON body exactly once.
 * @param response - response owning the socket.
 * @param status - HTTP status code.
 * @param body - JSON-serializable value.
 */
export declare function sendJson(response: ServerResponse, status: number, body: unknown): void;
