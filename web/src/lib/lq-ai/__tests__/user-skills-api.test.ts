/**
 * Unit tests for the user-skills API client (D8 / ADR 0012).
 *
 * Mocks `fetch` so the calls don't escape the test runner. Mirrors
 * the shape of saved-prompts-api.test.ts so the shared client
 * regressions surface here too (auth header, URL encoding, error
 * translation).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
	createUserSkill,
	deleteUserSkill,
	getUserSkill,
	listUserSkills,
	updateUserSkill
} from '../api/userSkills';
import type { UserSkill } from '../types';
import { clearSession, setSession } from '../auth/store';
import { LQAIApiError } from '../api/client';

const realFetch = global.fetch;

function jsonResponse(status: number, body: unknown): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json' }
	});
}

function emptyResponse(status: number): Response {
	return new Response(null, { status });
}

const SAMPLE: UserSkill = {
	id: 'cdbd099e-250d-4240-bff3-6e5154bb78e9',
	scope: 'user',
	owner_user_id: '0a4fe1ed-6fff-4f72-a027-6dedeac4fa36',
	slug: 'my-nda-review',
	display_name: 'My NDA Review',
	description: 'Personal NDA workflow',
	version: '1.0.0',
	tags: ['contracts', 'nda'],
	frontmatter_extra: {},
	body: 'You review NDAs with my house style.',
	archived_at: null,
	created_at: '2026-05-10T22:07:37Z',
	updated_at: '2026-05-10T22:07:37Z'
};

describe('user-skills API', () => {
	beforeEach(() => {
		clearSession();
		setSession({ access_token: 'tok', expires_in: 900 });
		vi.restoreAllMocks();
	});

	afterEach(() => {
		global.fetch = realFetch;
	});

	it('listUserSkills returns the array shape', async () => {
		global.fetch = vi.fn(async () => jsonResponse(200, [SAMPLE])) as unknown as typeof fetch;
		const out = await listUserSkills();
		expect(out).toHaveLength(1);
		expect(out[0].slug).toBe('my-nda-review');
		expect(out[0].scope).toBe('user');
	});

	it('listUserSkills attaches Authorization header', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, []));
		global.fetch = fetchSpy as unknown as typeof fetch;
		await listUserSkills();
		const init = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[1];
		const headers = init.headers as Record<string, string>;
		expect(headers.Authorization).toBe('Bearer tok');
	});

	it('createUserSkill POSTs JSON body', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(201, SAMPLE));
		global.fetch = fetchSpy as unknown as typeof fetch;
		const out = await createUserSkill({
			slug: 'my-nda-review',
			display_name: 'My NDA Review',
			description: 'Personal NDA workflow',
			body: 'You review NDAs with my house style.',
			tags: ['contracts', 'nda']
		});
		expect(out.id).toBe(SAMPLE.id);
		const init = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[1];
		expect(init.method).toBe('POST');
		const parsed = JSON.parse(init.body as string);
		expect(parsed.slug).toBe('my-nda-review');
		expect(parsed.tags).toEqual(['contracts', 'nda']);
	});

	it('createUserSkill surfaces 409 as LQAIApiError with status', async () => {
		global.fetch = vi.fn(async () =>
			jsonResponse(409, { detail: 'duplicate slug' })
		) as unknown as typeof fetch;
		try {
			await createUserSkill({
				slug: 'dup',
				display_name: 'Dup',
				description: 'd',
				body: 'b'
			});
			throw new Error('expected throw');
		} catch (e) {
			expect(e).toBeInstanceOf(LQAIApiError);
			expect((e as LQAIApiError).status).toBe(409);
		}
	});

	it('getUserSkill encodes the id', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, SAMPLE));
		global.fetch = fetchSpy as unknown as typeof fetch;
		await getUserSkill('id with space');
		const url = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[0];
		expect(url).toContain('id%20with%20space');
	});

	it('getUserSkill surfaces 404 as LQAIApiError', async () => {
		global.fetch = vi.fn(async () =>
			jsonResponse(404, { detail: { code: 'not_found', message: 'gone' } })
		) as unknown as typeof fetch;
		await expect(getUserSkill('ghost')).rejects.toBeInstanceOf(LQAIApiError);
	});

	it('updateUserSkill uses PATCH and forwards only supplied fields', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, SAMPLE));
		global.fetch = fetchSpy as unknown as typeof fetch;
		await updateUserSkill(SAMPLE.id, { version: '1.1.0' });
		const init = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[1];
		expect(init.method).toBe('PATCH');
		const parsed = JSON.parse(init.body as string);
		expect(parsed).toEqual({ version: '1.1.0' });
	});

	it('deleteUserSkill issues a DELETE and tolerates 204', async () => {
		const fetchSpy = vi.fn(async () => emptyResponse(204));
		global.fetch = fetchSpy as unknown as typeof fetch;
		await deleteUserSkill(SAMPLE.id);
		const init = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[1];
		expect(init.method).toBe('DELETE');
	});

	it('deleteUserSkill surfaces 410 as LQAIApiError with status', async () => {
		global.fetch = vi.fn(async () =>
			jsonResponse(410, { detail: 'already archived' })
		) as unknown as typeof fetch;
		try {
			await deleteUserSkill(SAMPLE.id);
			throw new Error('expected throw');
		} catch (e) {
			expect(e).toBeInstanceOf(LQAIApiError);
			expect((e as LQAIApiError).status).toBe(410);
		}
	});
});
