/**
 * Unit tests for the LQ.AI API client's auth-attachment + refresh-on-401
 * behaviour. We mock global `fetch` and assert the wire calls.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
	apiRequest,
	LQAIApiError,
	PasswordChangeRequiredError,
	UnauthorizedError
} from '../api/client';
import { clearSession, setSession, getAccessToken } from '../auth/store';

const realFetch = global.fetch;

function mockResponse(
	status: number,
	body: unknown,
	{ contentType = 'application/json' }: { contentType?: string } = {}
): Response {
	const headers = new Headers({ 'content-type': contentType });
	const stringBody =
		contentType.includes('json') && body !== undefined ? JSON.stringify(body) : (body as string);
	return new Response(stringBody, { status, headers });
}

describe('apiRequest', () => {
	beforeEach(() => {
		clearSession();
		vi.restoreAllMocks();
	});

	afterEach(() => {
		global.fetch = realFetch;
	});

	it('attaches the Authorization header when a token is set', async () => {
		setSession({ access_token: 'tok', expires_in: 900 });
		const fetchSpy = vi.fn(async () => mockResponse(200, { ok: true }));
		global.fetch = fetchSpy as unknown as typeof fetch;

		await apiRequest('/users/me');
		expect(fetchSpy).toHaveBeenCalledTimes(1);
		const init = fetchSpy.mock.calls[0][1] as RequestInit;
		const headers = init.headers as Record<string, string>;
		expect(headers.Authorization).toBe('Bearer tok');
	});

	it('throws UnauthorizedError on 401 with no refresh token', async () => {
		setSession({ access_token: 'tok', expires_in: 900 });
		const fetchSpy = vi.fn(async () =>
			mockResponse(401, { detail: { code: 'unauthorized', message: 'no' } })
		);
		global.fetch = fetchSpy as unknown as typeof fetch;

		await expect(apiRequest('/users/me')).rejects.toBeInstanceOf(UnauthorizedError);
		// Session was cleared because refresh failed (no refresh token).
		expect(getAccessToken()).toBeNull();
	});

	it('refreshes once on 401 then retries the original request', async () => {
		setSession({ access_token: 'tok', refresh_token: 'rtok', expires_in: 900 });
		const responses: Response[] = [
			// initial 401 from /users/me
			mockResponse(401, { detail: { code: 'unauthorized', message: 'expired' } }),
			// refresh succeeds
			mockResponse(200, {
				access_token: 'newtok',
				refresh_token: 'newrtok',
				token_type: 'Bearer',
				expires_in: 900
			}),
			// retry of /users/me succeeds
			mockResponse(200, { id: 'u', email: 'a@b' })
		];
		const fetchSpy = vi.fn(async () => responses.shift() as Response);
		global.fetch = fetchSpy as unknown as typeof fetch;

		const out = await apiRequest<{ id: string }>('/users/me');
		expect(out.id).toBe('u');
		expect(fetchSpy).toHaveBeenCalledTimes(3);
		expect(getAccessToken()).toBe('newtok');
	});

	it('throws PasswordChangeRequiredError on 403 with that code', async () => {
		setSession({ access_token: 'tok', expires_in: 900 });
		const fetchSpy = vi.fn(async () =>
			mockResponse(403, {
				detail: { code: 'password_change_required', message: 'rotate' }
			})
		);
		global.fetch = fetchSpy as unknown as typeof fetch;

		await expect(apiRequest('/projects')).rejects.toBeInstanceOf(PasswordChangeRequiredError);
	});

	it('returns undefined on 204 No Content', async () => {
		setSession({ access_token: 'tok', expires_in: 900 });
		const fetchSpy = vi.fn(async () => new Response(null, { status: 204 }));
		global.fetch = fetchSpy as unknown as typeof fetch;

		const out = await apiRequest('/auth/logout', { method: 'POST' });
		expect(out).toBeUndefined();
	});

	it('serialises JSON bodies and sets Content-Type', async () => {
		setSession({ access_token: 'tok', expires_in: 900 });
		const fetchSpy = vi.fn(async () => mockResponse(200, { id: 'p' }));
		global.fetch = fetchSpy as unknown as typeof fetch;

		await apiRequest('/projects', { method: 'POST', body: { name: 'P' } });
		const init = fetchSpy.mock.calls[0][1] as RequestInit;
		expect(init.body).toBe(JSON.stringify({ name: 'P' }));
		const headers = init.headers as Record<string, string>;
		expect(headers['Content-Type']).toBe('application/json');
	});

	it('translates 4xx with a typed code into LQAIApiError carrying the code', async () => {
		setSession({ access_token: 'tok', expires_in: 900 });
		const fetchSpy = vi.fn(async () =>
			mockResponse(400, { detail: { code: 'skill_input_missing', message: 'missing' } })
		);
		global.fetch = fetchSpy as unknown as typeof fetch;

		try {
			await apiRequest('/chats/abc/messages', { method: 'POST', body: {} });
			throw new Error('expected throw');
		} catch (e) {
			expect(e).toBeInstanceOf(LQAIApiError);
			expect((e as LQAIApiError).code).toBe('skill_input_missing');
			expect((e as LQAIApiError).status).toBe(400);
		}
	});
});
