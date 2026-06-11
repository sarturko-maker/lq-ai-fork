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
 * Consume a streaming response body, dispatching `onPart` per part.
 * Resolves when the stream ends — `[DONE]`, EOF, or abort. TRANSPORT
 * failures reject; the caller falls back to polling (the stream is
 * animation, polling is the contract).
 */
export async function consumeUIMessageStream(
	body: ReadableStream<Uint8Array>,
	callbacks: UIMessageStreamCallbacks
): Promise<void> {
	// TextDecoderStream's writable is typed as WritableStream<BufferSource> in
	// the lib.dom types, not WritableStream<Uint8Array>; a single cast through
	// unknown is the standard workaround for this interop pinch.
	const reader = body
		.pipeThrough(new TextDecoderStream() as unknown as ReadableWritablePair<string, Uint8Array>)
		.pipeThrough(new EventSourceParserStream())
		.getReader();

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
		reader.releaseLock();
	}
}
