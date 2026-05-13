/**
 * Unit tests for the Wave D.2 skill-autocomplete client helper
 * (``GET /api/v1/skills/autocomplete``).
 *
 * Mirrors the test pattern in ``skills-api-inputs.test.ts``: mock
 * ``global.fetch``, set a session so the auth header attaches, and
 * inspect the first call's URL / init shape.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { autocompleteSkills } from '../api/skills';
import type { SkillAutocompleteResponse } from '../types';
import { clearSession, setSession } from '../auth/store';

const realFetch = global.fetch;

function jsonResponse(status: number, body: unknown): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json' }
	});
}

const EMPTY_RESPONSE: SkillAutocompleteResponse = { results: [] };

describe('autocompleteSkills', () => {
	beforeEach(() => {
		clearSession();
		setSession({ access_token: 'tok', expires_in: 900 });
		vi.restoreAllMocks();
	});

	afterEach(() => {
		global.fetch = realFetch;
	});

	it('calls GET /skills/autocomplete with q + limit', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, EMPTY_RESPONSE));
		global.fetch = fetchSpy as unknown as typeof fetch;

		await autocompleteSkills('nda', 5);

		const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
		expect(url).toContain('/api/v1/skills/autocomplete?q=nda&limit=5');
		expect(init.method ?? 'GET').toBe('GET');
	});

	it('URL-encodes the q parameter', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, EMPTY_RESPONSE));
		global.fetch = fetchSpy as unknown as typeof fetch;

		await autocompleteSkills('nda review', 10);

		const url = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[0];
		expect(url).toContain('q=nda%20review');
		expect(url).toContain('limit=10');
	});

	it('defaults limit to 10 when omitted', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, EMPTY_RESPONSE));
		global.fetch = fetchSpy as unknown as typeof fetch;

		await autocompleteSkills('nda');

		const url = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[0];
		expect(url).toContain('limit=10');
	});

	it('returns the parsed SkillAutocompleteResponse shape', async () => {
		const body: SkillAutocompleteResponse = {
			results: [
				{
					slug: 'nda-review',
					slash_alias: null,
					title: 'NDA Review',
					description: 'Review an NDA',
					scope: 'builtin',
					icon: null
				}
			]
		};
		global.fetch = vi.fn(async () => jsonResponse(200, body)) as unknown as typeof fetch;
		const out = await autocompleteSkills('nda');
		expect(out.results).toHaveLength(1);
		expect(out.results[0].slug).toBe('nda-review');
		expect(out.results[0].scope).toBe('builtin');
	});
});
