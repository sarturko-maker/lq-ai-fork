/**
 * Unit tests for the admin patchUserRole API helper (T5 — Wave B v2).
 *
 * Tests: success 200, and 409 last-admin-demote error path.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { patchUserRole } from '../api/admin';
import type { AdminUserRow } from '../types';
import { clearSession, setSession } from '../auth/store';
import { LQAIApiError } from '../api/client';

const realFetch = global.fetch;

function jsonResponse(status: number, body: unknown): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json' }
	});
}

const UPDATED_ROW: AdminUserRow = {
	id: 'u2',
	email: 'bob@example.com',
	display_name: null,
	role: 'viewer',
	is_admin: false,
	mfa_enabled: false,
	must_change_password: false,
	created_at: '2026-02-01T00:00:00Z',
	last_login_at: null,
	deletion_scheduled_at: null
};

describe('admin patchUserRole API', () => {
	beforeEach(() => {
		clearSession();
		setSession({ access_token: 'tok', expires_in: 900 });
		vi.restoreAllMocks();
	});

	afterEach(() => {
		global.fetch = realFetch;
	});

	it('returns the updated row on success', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, UPDATED_ROW));
		global.fetch = fetchSpy as unknown as typeof fetch;
		const out = await patchUserRole('u2', 'viewer');
		expect(out.role).toBe('viewer');
		expect(out.id).toBe('u2');
		const init = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[1];
		expect(init.method).toBe('PATCH');
		const body = JSON.parse(init.body as string);
		expect(body.role).toBe('viewer');
	});

	it('surfaces 409 as LQAIApiError when demoting the last admin', async () => {
		global.fetch = vi.fn(async () =>
			jsonResponse(409, { detail: { code: 'last_admin', message: 'Cannot demote the last admin' } })
		) as unknown as typeof fetch;
		await expect(patchUserRole('u1', 'member')).rejects.toBeInstanceOf(LQAIApiError);
		await expect(patchUserRole('u1', 'member')).rejects.toMatchObject({
			status: 409,
			code: 'last_admin'
		});
	});
});
