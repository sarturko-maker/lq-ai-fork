/**
 * Unit tests for the user-facing teams API client (D8.1a + D8.1c).
 *
 * Mocks `fetch` so the calls don't escape the test runner. Mirrors
 * the user-skills client tests for auth-header coverage + URL shape
 * regressions.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { getMyTeam, listMyTeams } from '../api/teams';
import type { Team, TeamSummary } from '../types';
import { clearSession, setSession } from '../auth/store';
import { LQAIApiError } from '../api/client';

const realFetch = global.fetch;

function jsonResponse(status: number, body: unknown): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json' }
	});
}

const SAMPLE_SUMMARY: TeamSummary = {
	id: 'a1a1a1a1-1111-1111-1111-111111111111',
	slug: 'contracts',
	name: 'Contracts',
	description: null,
	created_by_user_id: 'b2b2b2b2-2222-2222-2222-222222222222',
	member_count: 3,
	caller_role: 'admin',
	created_at: '2026-05-10T22:00:00Z',
	updated_at: '2026-05-10T22:00:00Z'
};

const SAMPLE_TEAM: Team = {
	...SAMPLE_SUMMARY,
	members: []
};

describe('teams API', () => {
	beforeEach(() => {
		clearSession();
		setSession({ access_token: 'tok', expires_in: 900 });
		vi.restoreAllMocks();
	});

	afterEach(() => {
		global.fetch = realFetch;
	});

	it('listMyTeams default fetches /teams without role filter', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, [SAMPLE_SUMMARY]));
		global.fetch = fetchSpy as unknown as typeof fetch;
		const out = await listMyTeams();
		expect(out).toHaveLength(1);
		expect(out[0].caller_role).toBe('admin');
		const url = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[0];
		expect(url.endsWith('/teams')).toBe(true);
	});

	it('listMyTeams appends ?role=admin when filtered', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, []));
		global.fetch = fetchSpy as unknown as typeof fetch;
		await listMyTeams('admin');
		const url = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[0];
		expect(url).toContain('/teams?role=admin');
	});

	it('listMyTeams attaches Authorization header', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, []));
		global.fetch = fetchSpy as unknown as typeof fetch;
		await listMyTeams();
		const init = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[1];
		const headers = init.headers as Record<string, string>;
		expect(headers.Authorization).toBe('Bearer tok');
	});

	it('getMyTeam encodes the id', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, SAMPLE_TEAM));
		global.fetch = fetchSpy as unknown as typeof fetch;
		await getMyTeam('id with space');
		const url = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[0];
		expect(url).toContain('id%20with%20space');
	});

	it('getMyTeam surfaces 404 as LQAIApiError', async () => {
		global.fetch = vi.fn(async () =>
			jsonResponse(404, { detail: 'team not found' })
		) as unknown as typeof fetch;
		try {
			await getMyTeam('ghost');
			throw new Error('expected throw');
		} catch (e) {
			expect(e).toBeInstanceOf(LQAIApiError);
			expect((e as LQAIApiError).status).toBe(404);
		}
	});
});
