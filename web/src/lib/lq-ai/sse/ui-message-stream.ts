/**
 * AI SDK UI Message Stream v1 consumer — F0-S7 (ADR-F006 wire spec).
 *
 * Parses the SSE stream from `GET /api/v1/agents/runs/{id}/stream`:
 * `data: <json>` lines whose payloads discriminate on `type`
 * (text-* / reasoning-* / tool-* / data-* / start / finish / error),
 * terminated by `data: [DONE]`. Spec-only — no Vercel runtime; the
 * server's emitter is hand-rolled the same way (api/app/agents/stream).
 *
 * Deliberately loose typing: the agents surface consumes a handful of
 * part types and IGNORES the rest (forward compatibility — the spec
 * allows parts we don't render). Nothing durable derives from any part
 * except `data-step` / `data-run`, which mirror settled rows
 * (ADR-F004: settled rows decide, streams animate).
 */
import { EventSourceParserStream } from 'eventsource-parser/stream';
import type { ParsedEvent } from 'eventsource-parser';

/** One stream part. `type` discriminates; consumers narrow per type. */
export interface UIMessagePart {
	type: string;
	[key: string]: unknown;
}

/**
 * Normalise one SSE `data:` payload: a part object, `'[DONE]'` for the
 * terminator, or null for anything unusable (malformed JSON, missing
 * `type`) — unusable frames are SKIPPED, never fatal: the settled rows
 * carry the truth regardless.
 */
export function normalizeUIMessageFrame(data: string): UIMessagePart | '[DONE]' | null {
	if (data === '[DONE]') return '[DONE]';
	let parsed: unknown;
	try {
		parsed = JSON.parse(data);
	} catch {
		return null;
	}
	if (typeof parsed !== 'object' || parsed === null) return null;
	const part = parsed as Record<string, unknown>;
	if (typeof part.type !== 'string') return null;
	return part as UIMessagePart;
}

export interface UIMessageStreamCallbacks {
	/** Every well-formed part, in wire order. */
	onPart: (part: UIMessagePart) => void;
	/** The `[DONE]` terminator arrived (clean end). */
	onDone?: () => void;
}

/**
 * Stall watchdog cutoff: end the stream if NO bytes arrive for this long.
 * The server pings every 15s (`_STREAM_HEARTBEAT_SECONDS`), so a healthy
 * connection is never silent for more than ~15s even mid-model-turn; 45s
 * (three missed pings) means the transport is dead. Chosen after a live
 * run whose TCP connection was silently blackholed (no FIN/RST — a
 * Crostini/port-forward failure mode): `reader.read()` hung forever,
 * the poll fallback never engaged (it triggers on error, not silence),
 * and the UI froze while the run completed server-side.
 */
export const STREAM_STALL_TIMEOUT_MS = 45_000;

/** How often the watchdog checks for silence. */
const STALL_CHECK_INTERVAL_MS = 5_000;

/**
 * Consume a streaming response body, dispatching `onPart` per part.
 * Resolves when the stream ends — `[DONE]`, EOF, abort, or the stall
 * watchdog cutting a silent connection. TRANSPORT failures reject; the
 * caller falls back to polling (the stream is animation, polling is the
 * contract). A watchdog-cut stream resolves like EOF: the caller's
 * clean-end path reconciles against the settled thread and re-opens a
 * fresh stream if the run is still live.
 *
 * The watchdog watches BYTES, before SSE parsing: the server's
 * keep-alive pings are SSE comments (`: ping`), which
 * EventSourceParserStream swallows — a watchdog on parsed events would
 * falsely fire during a healthy connection's long quiet model turn.
 *
 * Known benign false-fire: a backgrounded/frozen tab can suspend JS long
 * enough that `lastByteAt` goes stale while the transport stayed healthy;
 * on resume the watchdog cuts a live stream. Self-healing — the clean-EOF
 * recovery reconciles and re-opens — so a spurious cut costs one
 * reconnect, never data.
 */
export async function consumeUIMessageStream(
	body: ReadableStream<Uint8Array>,
	callbacks: UIMessageStreamCallbacks,
	stallTimeoutMs: number = STREAM_STALL_TIMEOUT_MS
): Promise<void> {
	let lastByteAt = Date.now();
	const liveness = new TransformStream<Uint8Array, Uint8Array>({
		transform(chunk, controller) {
			lastByteAt = Date.now();
			controller.enqueue(chunk);
		}
	});

	// TextDecoderStream's writable is typed as WritableStream<BufferSource> in
	// the lib.dom types, not WritableStream<Uint8Array>; a single cast through
	// unknown is the standard workaround for this interop pinch.
	const reader = body
		.pipeThrough(liveness)
		.pipeThrough(new TextDecoderStream() as unknown as ReadableWritablePair<string, Uint8Array>)
		.pipeThrough(new EventSourceParserStream())
		.getReader();

	// Cancelling the reader propagates upstream through the pipe chain and
	// resolves the pending read() with { done: true } — the loop ends as a
	// clean EOF rather than an error, which is exactly the recovery path
	// we want (reconcile + re-poll), and never rejects the caller.
	const stallTimer =
		stallTimeoutMs > 0
			? setInterval(
					() => {
						if (Date.now() - lastByteAt > stallTimeoutMs) {
							void reader.cancel().catch(() => undefined);
						}
					},
					// Never check less often than the cutoff itself (keeps a
					// short test cutoff responsive; production uses 45s/5s).
					Math.min(STALL_CHECK_INTERVAL_MS, stallTimeoutMs)
				)
			: null;

	try {
		while (true) {
			const { value, done } = await reader.read();
			if (done) break;
			if (!value) continue;
			const frame = normalizeUIMessageFrame((value as ParsedEvent).data ?? '');
			if (frame === '[DONE]') {
				callbacks.onDone?.();
				return;
			}
			if (frame !== null) callbacks.onPart(frame);
		}
	} finally {
		if (stallTimer !== null) clearInterval(stallTimer);
		reader.releaseLock();
	}
}
