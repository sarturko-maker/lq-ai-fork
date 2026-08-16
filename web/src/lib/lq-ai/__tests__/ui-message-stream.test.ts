import { describe, expect, it } from 'vitest';
import {
	consumeUIMessageStream,
	normalizeUIMessageFrame,
	type UIMessagePart
} from '../sse/ui-message-stream';

function bodyFrom(frames: string[]): ReadableStream<Uint8Array> {
	const encoder = new TextEncoder();
	return new ReadableStream<Uint8Array>({
		start(controller) {
			for (const frame of frames) controller.enqueue(encoder.encode(frame));
			controller.close();
		}
	});
}

describe('normalizeUIMessageFrame', () => {
	it('parses a part and passes the terminator through', () => {
		expect(normalizeUIMessageFrame('{"type":"finish"}')).toEqual({ type: 'finish' });
		expect(normalizeUIMessageFrame('[DONE]')).toBe('[DONE]');
	});

	it('skips malformed payloads instead of throwing', () => {
		expect(normalizeUIMessageFrame('{nope')).toBeNull();
		expect(normalizeUIMessageFrame('"just a string"')).toBeNull();
		expect(normalizeUIMessageFrame('{"no_type":true}')).toBeNull();
	});
});

describe('consumeUIMessageStream', () => {
	it('dispatches parts in wire order and fires onDone at [DONE]', async () => {
		const parts: UIMessagePart[] = [];
		let done = false;
		await consumeUIMessageStream(
			bodyFrom([
				'data: {"type":"start","messageId":"r1"}\n\n',
				'data: {"type":"reasoning-delta","id":"b1","delta":"thinking"}\n\n',
				': ping\n\n', // heartbeat comment — must be ignored
				'data: {"type":"data-step","id":"s1","data":{"seq":1}}\n\n',
				'data: {"type":"finish"}\n\n',
				'data: [DONE]\n\n'
			]),
			{
				onPart: (p) => parts.push(p),
				onDone: () => {
					done = true;
				}
			}
		);
		expect(parts.map((p) => p.type)).toEqual(['start', 'reasoning-delta', 'data-step', 'finish']);
		expect(done).toBe(true);
	});

	it('survives frames split across chunks', async () => {
		const parts: UIMessagePart[] = [];
		await consumeUIMessageStream(
			bodyFrom(['data: {"type":"text-delta","id":"a","del', 'ta":"Hello"}\n\ndata: [DONE]\n\n']),
			{ onPart: (p) => parts.push(p) }
		);
		expect(parts).toEqual([{ type: 'text-delta', id: 'a', delta: 'Hello' }]);
	});

	it('ends cleanly on EOF without [DONE]', async () => {
		const parts: UIMessagePart[] = [];
		await consumeUIMessageStream(bodyFrom(['data: {"type":"start-step"}\n\n']), {
			onPart: (p) => parts.push(p)
		});
		expect(parts).toEqual([{ type: 'start-step' }]);
	});

	it('resolves via the stall watchdog when the connection goes silent (blackholed TCP)', async () => {
		// A stream that delivers one part and then never sends another byte and
		// never closes — the silently-dropped-connection failure mode. Without
		// the watchdog this hangs forever; with it, consume resolves like EOF
		// so the caller reconciles and falls back to polling.
		const encoder = new TextEncoder();
		const body = new ReadableStream<Uint8Array>({
			start(controller) {
				controller.enqueue(encoder.encode('data: {"type":"start","messageId":"r1"}\n\n'));
				// never close, never error
			}
		});
		const parts: UIMessagePart[] = [];
		let done = false;
		await expect(
			Promise.race([
				consumeUIMessageStream(
					body,
					{
						onPart: (p) => parts.push(p),
						onDone: () => {
							done = true;
						}
					},
					1 // stall cutoff 1ms; the 5s check interval dominates the wait
				),
				new Promise((_, reject) =>
					setTimeout(() => reject(new Error('watchdog never fired')), 15_000)
				)
			])
		).resolves.toBeUndefined();
		expect(parts).toEqual([{ type: 'start', messageId: 'r1' }]);
		expect(done).toBe(false); // EOF-style end, not [DONE]
	}, 20_000);

	it('REJECTS on a transport failure — the contract the polling fallback relies on', async () => {
		const encoder = new TextEncoder();
		const body = new ReadableStream<Uint8Array>({
			start(controller) {
				controller.enqueue(encoder.encode('data: {"type":"reasoning-delta","id":"b","delta":"x"}\n\n'));
				controller.error(new Error('connection reset'));
			}
		});
		// The rejection is the load-bearing contract (the component's catch
		// falls back to polling on it). Whether parts enqueued just before
		// the cut still flush is up to the decoder pipeline — not asserted.
		await expect(
			consumeUIMessageStream(body, { onPart: () => undefined })
		).rejects.toThrow('connection reset');
	});
});
