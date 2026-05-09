/**
 * Unit tests for the admin alias API client (D0.5).
 *
 * Mocks `fetch` so the calls don't escape the test runner.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
	createAlias,
	deleteAlias,
	getAlias,
	listAliases,
	updateAlias,
	type Alias,
	type AliasListResponse
} from '../api/admin';
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

const SAMPLE_LIST: AliasListResponse = {
	object: 'list',
	data: [
		{ name: 'smart', provider: 'anthropic-prod', model: 'claude-opus-4-7', fallback: [] },
		{ name: 'fast', provider: 'anthropic-prod', model: 'claude-sonnet-4-6', fallback: [] }
	]
};

const SAMPLE_ALIAS: Alias = {
	name: 'smart',
	provider: 'anthropic-prod',
	model: 'claude-opus-4-7',
	fallback: [{ provider: 'openai-prod', model: 'gpt-4-turbo' }],
	primary_inference_tier: 4
};

describe('admin alias API', () => {
	beforeEach(() => {
		clearSession();
		setSession({ access_token: 'tok', expires_in: 900 });
		vi.restoreAllMocks();
	});

	afterEach(() => {
		global.fetch = realFetch;
	});

	it('listAliases parses the response shape', async () => {
		global.fetch = vi.fn(async () => jsonResponse(200, SAMPLE_LIST)) as unknown as typeof fetch;
		const out = await listAliases();
		expect(out.object).toBe('list');
		expect(out.data.map((a) => a.name)).toEqual(['smart', 'fast']);
	});

	it('getAlias preserves primary_inference_tier', async () => {
		global.fetch = vi.fn(async () => jsonResponse(200, SAMPLE_ALIAS)) as unknown as typeof fetch;
		const out = await getAlias('smart');
		expect(out.primary_inference_tier).toBe(4);
	});

	it('createAlias serializes body as JSON', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(201, SAMPLE_ALIAS));
		global.fetch = fetchSpy as unknown as typeof fetch;
		await createAlias({
			name: 'smart',
			provider: 'anthropic-prod',
			model: 'claude-opus-4-7',
			fallback: []
		});
		const init = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[1];
		expect(init.method).toBe('POST');
		expect(init.body).toBeTruthy();
		const parsed = JSON.parse(init.body as string);
		expect(parsed.name).toBe('smart');
	});

	it('createAlias surfaces 409 as LQAIApiError', async () => {
		global.fetch = vi.fn(async () =>
			jsonResponse(409, {
				detail: { code: 'conflict', message: 'alias already exists' }
			})
		) as unknown as typeof fetch;

		await expect(
			createAlias({
				name: 'smart',
				provider: 'anthropic-prod',
				model: 'claude-opus-4-7'
			})
		).rejects.toBeInstanceOf(LQAIApiError);
	});

	it('updateAlias uses PATCH', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, SAMPLE_ALIAS));
		global.fetch = fetchSpy as unknown as typeof fetch;
		await updateAlias('smart', { provider: 'anthropic-prod', model: 'claude-opus-4-7' });
		const init = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[1];
		expect(init.method).toBe('PATCH');
	});

	it('updateAlias surfaces 404 as LQAIApiError', async () => {
		global.fetch = vi.fn(async () =>
			jsonResponse(404, { detail: { code: 'not_found', message: 'no alias' } })
		) as unknown as typeof fetch;
		await expect(
			updateAlias('ghost', { provider: 'anthropic-prod', model: 'x' })
		).rejects.toBeInstanceOf(LQAIApiError);
	});

	it('deleteAlias issues a DELETE and tolerates 204', async () => {
		const fetchSpy = vi.fn(async () => emptyResponse(204));
		global.fetch = fetchSpy as unknown as typeof fetch;
		await deleteAlias('throwaway');
		const init = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[1];
		expect(init.method).toBe('DELETE');
	});

	it('encodes alias name for URL safety', async () => {
		const fetchSpy = vi.fn(async () => emptyResponse(204));
		global.fetch = fetchSpy as unknown as typeof fetch;
		await deleteAlias('weird/name with space');
		const url = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[0];
		expect(url).toContain('weird%2Fname%20with%20space');
	});

	it('listAliases attaches Authorization header', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, SAMPLE_LIST));
		global.fetch = fetchSpy as unknown as typeof fetch;
		await listAliases();
		const init = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[1];
		const headers = init.headers as Record<string, string>;
		expect(headers.Authorization).toBe('Bearer tok');
	});
});
