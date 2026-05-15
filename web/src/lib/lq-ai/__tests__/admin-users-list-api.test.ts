/**
 * Unit tests for the admin user-list API helper (T5 — Wave B v2).
 *
 * Follows the admin-usage-api.test.ts pattern: mock fetch, assert URL shape
 * and response parsing.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { listUsers } from '../api/admin';
import type { AdminUserListResponse } from '../types';
import { clearSession, setSession } from '../auth/store';
import { LQAIApiError } from '../api/client';

const realFetch = global.fetch;

function jsonResponse(status: number, body: unknown): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json' }
	});
}

const SAMPLE_RESPONSE: AdminUserListResponse = {
	users: [
		{
			id: 'u1',
			email: 'alice@example.com',
			display_name: 'Alice',
			role: 'admin',
			is_admin: true,
			mfa_enabled: true,
			must_change_password: false,
			created_at: '2026-01-01T00:00:00Z',
			last_login_at: '2026-05-11T10:00:00Z',
			deletion_scheduled_at: null
		},
		{
			id: 'u2',
			email: 'bob@example.com',
			display_name: null,
			role: 'member',
			is_admin: false,
			mfa_enabled: false,
			must_change_password: false,
			created_at: '2026-02-01T00:00:00Z',
			last_login_at: null,
			deletion_scheduled_at: null
		}
	],
	total_count: 2,
	limit: 50,
	offset: 0
};

describe('admin listUsers API', () => {
	beforeEach(() => {
		clearSession();
		setSession({ access_token: 'tok', expires_in: 900 });
		vi.restoreAllMocks();
	});

	afterEach(() => {
		global.fetch = realFetch;
	});

	it('parses the response shape and returns users', async () => {
		global.fetch = vi.fn(async () => jsonResponse(200, SAMPLE_RESPONSE)) as unknown as typeof fetch;
		const out = await listUsers();
		expect(out.total_count).toBe(2);
		expect(out.users).toHaveLength(2);
		expect(out.users[0].email).toBe('alice@example.com');
		expect(out.users[0].role).toBe('admin');
		expect(out.users[1].last_login_at).toBeNull();
	});

	it('encodes query params into the URL', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, SAMPLE_RESPONSE));
		global.fetch = fetchSpy as unknown as typeof fetch;
		await listUsers({ role: 'member', email_q: 'bob', limit: 10, offset: 0 });
		const url = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[0];
		expect(url).toContain('/admin/users');
		expect(url).toContain('role=member');
		expect(url).toContain('email_q=bob');
		expect(url).toContain('limit=10');
	});

	it('surfaces 403 as LQAIApiError for non-admin callers', async () => {
		global.fetch = vi.fn(async () =>
			jsonResponse(403, { detail: { code: 'forbidden', message: 'Admin only' } })
		) as unknown as typeof fetch;
		await expect(listUsers()).rejects.toBeInstanceOf(LQAIApiError);
		await expect(listUsers()).rejects.toMatchObject({ status: 403 });
	});
});
