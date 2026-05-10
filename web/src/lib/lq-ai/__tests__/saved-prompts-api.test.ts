/**
 * Unit tests for the saved-prompts API client (D7 / DE-013).
 *
 * Mocks `fetch` so the calls don't escape the test runner. Mirrors
 * the shape of admin-api.test.ts so regressions in the shared client
 * (auth header attachment, error translation, URL encoding) surface
 * here as well.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
	createSavedPrompt,
	deleteSavedPrompt,
	getSavedPrompt,
	listSavedPrompts,
	updateSavedPrompt
} from '../api/savedPrompts';
import type { SavedPrompt } from '../types';
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

const SAMPLE: SavedPrompt = {
	id: '6a00be25-0fcf-4cd1-9d68-7f5c5cae0c1f',
	user_id: '11111111-1111-1111-1111-111111111111',
	name: 'Executive summary',
	prompt_text: 'Summarize for a CEO audience.',
	tags: ['summary', 'exec'],
	created_at: '2026-05-09T12:00:00Z',
	updated_at: '2026-05-09T12:00:00Z'
};

describe('saved prompts API', () => {
	beforeEach(() => {
		clearSession();
		setSession({ access_token: 'tok', expires_in: 900 });
		vi.restoreAllMocks();
	});

	afterEach(() => {
		global.fetch = realFetch;
	});

	it('listSavedPrompts returns the array shape', async () => {
		global.fetch = vi.fn(async () =>
			jsonResponse(200, [SAMPLE])
		) as unknown as typeof fetch;
		const out = await listSavedPrompts();
		expect(out).toHaveLength(1);
		expect(out[0].name).toBe('Executive summary');
		expect(out[0].tags).toEqual(['summary', 'exec']);
	});

	it('listSavedPrompts attaches Authorization header', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, []));
		global.fetch = fetchSpy as unknown as typeof fetch;
		await listSavedPrompts();
		const init = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[1];
		const headers = init.headers as Record<string, string>;
		expect(headers.Authorization).toBe('Bearer tok');
	});

	it('createSavedPrompt POSTs JSON body', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(201, SAMPLE));
		global.fetch = fetchSpy as unknown as typeof fetch;
		const out = await createSavedPrompt({
			name: 'Executive summary',
			prompt_text: 'Summarize for a CEO audience.',
			tags: ['summary', 'exec']
		});
		expect(out.id).toBe(SAMPLE.id);
		const init = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[1];
		expect(init.method).toBe('POST');
		const parsed = JSON.parse(init.body as string);
		expect(parsed.name).toBe('Executive summary');
		expect(parsed.tags).toEqual(['summary', 'exec']);
	});

	it('createSavedPrompt surfaces 422 as LQAIApiError', async () => {
		global.fetch = vi.fn(async () =>
			jsonResponse(422, { detail: { code: 'unprocessable', message: 'bad tags' } })
		) as unknown as typeof fetch;
		await expect(
			createSavedPrompt({ name: '', prompt_text: '' })
		).rejects.toBeInstanceOf(LQAIApiError);
	});

	it('getSavedPrompt encodes the id', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, SAMPLE));
		global.fetch = fetchSpy as unknown as typeof fetch;
		await getSavedPrompt('id with space');
		const url = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[0];
		expect(url).toContain('id%20with%20space');
	});

	it('getSavedPrompt surfaces 404 as LQAIApiError', async () => {
		global.fetch = vi.fn(async () =>
			jsonResponse(404, { detail: { code: 'not_found', message: 'gone' } })
		) as unknown as typeof fetch;
		await expect(getSavedPrompt('ghost')).rejects.toBeInstanceOf(LQAIApiError);
	});

	it('updateSavedPrompt uses PATCH', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, SAMPLE));
		global.fetch = fetchSpy as unknown as typeof fetch;
		await updateSavedPrompt(SAMPLE.id, { name: 'Renamed' });
		const init = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[1];
		expect(init.method).toBe('PATCH');
		const parsed = JSON.parse(init.body as string);
		expect(parsed.name).toBe('Renamed');
	});

	it('deleteSavedPrompt issues a DELETE and tolerates 204', async () => {
		const fetchSpy = vi.fn(async () => emptyResponse(204));
		global.fetch = fetchSpy as unknown as typeof fetch;
		await deleteSavedPrompt(SAMPLE.id);
		const init = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[1];
		expect(init.method).toBe('DELETE');
	});
});
