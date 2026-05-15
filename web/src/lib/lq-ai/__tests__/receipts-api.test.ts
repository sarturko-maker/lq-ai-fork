/**
 * Unit tests for the chat receipts API helpers.
 *
 * Mocks `fetch` so calls don't escape the test runner. Mirrors the pattern
 * from project-knowledge-bases-api.test.ts: jsonResponse helper + setSession
 * to satisfy the auth header; inspect the Request init to confirm method,
 * URL encoding, and query-string assembly.
 *
 * The export helper also exercises Content-Disposition parsing — the
 * filename must round-trip from the response header to the result object,
 * with a sensible fallback when the header is missing.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
	listChatReceipts,
	exportChatReceiptsJsonl,
	type ReceiptEvent
} from '../api/receipts';
import { clearSession, setSession } from '../auth/store';

const realFetch = global.fetch;

function jsonResponse(status: number, body: unknown): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json' }
	});
}

function jsonlResponse(
	status: number,
	jsonl: string,
	extraHeaders: Record<string, string> = {}
): Response {
	return new Response(jsonl, {
		status,
		headers: { 'content-type': 'application/jsonl', ...extraHeaders }
	});
}

const SAMPLE_EVENTS: ReceiptEvent[] = [
	{
		ts: '2026-05-12T00:00:01Z',
		kind: 'message',
		detail: { id: 'msg-001', role: 'user', content: 'hello' }
	},
	{
		ts: '2026-05-12T00:00:02Z',
		kind: 'inference',
		detail: { provider: 'anthropic', tier: 4 }
	},
	{
		ts: '2026-05-12T00:00:03Z',
		kind: 'audit',
		detail: { action: 'message.created' }
	}
];

describe('receipts api', () => {
	beforeEach(() => {
		clearSession();
		setSession({ access_token: 'test-token', expires_in: 900 });
		vi.restoreAllMocks();
	});

	afterEach(() => {
		global.fetch = realFetch;
	});

	it('listChatReceipts GETs /chats/{id}/receipts without query when event_kinds omitted', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, SAMPLE_EVENTS));
		global.fetch = fetchSpy as unknown as typeof fetch;

		const result = await listChatReceipts('chat-c1');

		// Return shape
		expect(result).toHaveLength(3);
		expect(result[0].kind).toBe('message');
		expect(result[1].kind).toBe('inference');

		// Request shape
		const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
		expect(url).toContain('/api/v1/chats/chat-c1/receipts');
		expect(url).not.toContain('event_kinds');
		expect(init.method).toBe('GET');
	});

	it('listChatReceipts passes event_kinds as CSV query parameter', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, [SAMPLE_EVENTS[0]]));
		global.fetch = fetchSpy as unknown as typeof fetch;

		await listChatReceipts('chat-c1', ['message', 'inference']);

		const [url] = fetchSpy.mock.calls[0] as [string, RequestInit];
		// encodeURIComponent('message,inference') === 'message%2Cinference'
		expect(url).toContain('/api/v1/chats/chat-c1/receipts?event_kinds=message%2Cinference');
	});

	it('exportChatReceiptsJsonl returns jsonl text and parses filename from Content-Disposition', async () => {
		const jsonlBody =
			'{"ts":"2026-05-12T00:00:01Z","kind":"message","detail":{"id":"msg-001"}}\n' +
			'{"ts":"2026-05-12T00:00:02Z","kind":"inference","detail":{"tier":4}}\n';
		const fetchSpy = vi.fn(async () =>
			jsonlResponse(200, jsonlBody, {
				'content-disposition': 'attachment; filename="chat-c1-receipts.jsonl"'
			})
		);
		global.fetch = fetchSpy as unknown as typeof fetch;

		const result = await exportChatReceiptsJsonl('chat-c1');

		expect(result.jsonl).toBe(jsonlBody);
		expect(result.filename).toBe('chat-c1-receipts.jsonl');

		const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
		expect(url).toContain('/api/v1/chats/chat-c1/receipts/export.jsonl');
		expect(init.method).toBe('GET');
		const reqHeaders = (init.headers ?? {}) as Record<string, string>;
		expect(reqHeaders['Authorization']).toBe('Bearer test-token');
	});

	it('exportChatReceiptsJsonl falls back to a default filename when Content-Disposition is missing', async () => {
		const fetchSpy = vi.fn(async () => jsonlResponse(200, '{"kind":"message"}\n'));
		global.fetch = fetchSpy as unknown as typeof fetch;

		// Use a bare uuid-style id (no chat- prefix) so the fallback reads cleanly
		const result = await exportChatReceiptsJsonl('c1');

		expect(result.filename).toBe('chat-c1-receipts.jsonl');
	});

	it('exportChatReceiptsJsonl throws on 403', async () => {
		const fetchSpy = vi.fn(async () =>
			jsonResponse(403, { detail: { code: 'forbidden', message: 'Forbidden' } })
		);
		global.fetch = fetchSpy as unknown as typeof fetch;

		await expect(exportChatReceiptsJsonl('chat-c1')).rejects.toThrow(/403/);
	});
});
