/**
 * Unit tests for the admin audit-log API client (D3-coverage).
 *
 * Mocks ``fetch`` so calls don't escape the test runner.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { listAuditLog, type AuditLogPage } from '../api/auditLog';
import { clearSession, setSession } from '../auth/store';

const realFetch = global.fetch;

function jsonResponse(status: number, body: unknown): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json' }
	});
}

const SAMPLE_PAGE: AuditLogPage = {
	items: [
		{
			id: 'a1',
			timestamp: '2026-05-10T20:00:00Z',
			user_id: 'u1',
			action: 'user.login',
			resource_type: 'user',
			resource_id: 'u1',
			privilege_marked: false,
			privilege_basis: null,
			routed_inference_tier: null,
			routed_provider: null,
			ip_address: '127.0.0.1',
			user_agent: 'curl/8',
			request_id: 'req_abc',
			details: null
		}
	],
	next_cursor: '2026-05-10T20:00:00+00:00|a1'
};

describe('audit-log admin API', () => {
	beforeEach(() => {
		clearSession();
		setSession({ access_token: 'tok', expires_in: 900 });
		vi.restoreAllMocks();
	});

	afterEach(() => {
		global.fetch = realFetch;
	});

	it('listAuditLog issues a GET with no query params on empty filters', async () => {
		const spy = vi.spyOn(global, 'fetch').mockResolvedValue(jsonResponse(200, SAMPLE_PAGE));
		const page = await listAuditLog();
		expect(page.items.length).toBe(1);
		expect(page.next_cursor).toBe('2026-05-10T20:00:00+00:00|a1');

		const [url, init] = spy.mock.calls[0];
		expect(String(url)).toMatch(/\/admin\/audit-log$/);
		expect((init as RequestInit).method ?? 'GET').toBe('GET');
	});

	it('listAuditLog encodes filters into the query string', async () => {
		const spy = vi.spyOn(global, 'fetch').mockResolvedValue(jsonResponse(200, SAMPLE_PAGE));
		await listAuditLog({
			privilege_marked: true,
			routed_inference_tier: 4,
			action: 'chat.message_sent',
			user_id: 'u1',
			since: '2026-05-01T00:00:00Z',
			until: '2026-05-10T23:59:59Z',
			limit: 100,
			cursor: 'ts|id'
		});
		const url = String(spy.mock.calls[0][0]);
		expect(url).toContain('privilege_marked=true');
		expect(url).toContain('routed_inference_tier=4');
		expect(url).toContain('action=chat.message_sent');
		expect(url).toContain('user_id=u1');
		expect(url).toContain('since=2026-05-01');
		expect(url).toContain('until=2026-05-10');
		expect(url).toContain('limit=100');
		expect(url).toContain('cursor=ts');
	});

	it('listAuditLog skips null filters', async () => {
		const spy = vi.spyOn(global, 'fetch').mockResolvedValue(jsonResponse(200, SAMPLE_PAGE));
		await listAuditLog({
			privilege_marked: null,
			routed_inference_tier: null,
			action: null,
			user_id: null,
			since: null,
			until: null,
			cursor: null,
			limit: 50
		});
		const url = String(spy.mock.calls[0][0]);
		expect(url).not.toContain('privilege_marked');
		expect(url).not.toContain('routed_inference_tier');
		expect(url).not.toContain('action=');
		expect(url).not.toContain('user_id=');
		expect(url).not.toContain('since=');
		expect(url).not.toContain('until=');
		expect(url).not.toContain('cursor=');
		expect(url).toContain('limit=50');
	});

	it('listAuditLog encodes privilege_marked=false explicitly', async () => {
		const spy = vi.spyOn(global, 'fetch').mockResolvedValue(jsonResponse(200, SAMPLE_PAGE));
		await listAuditLog({ privilege_marked: false });
		const url = String(spy.mock.calls[0][0]);
		expect(url).toContain('privilege_marked=false');
	});
});
