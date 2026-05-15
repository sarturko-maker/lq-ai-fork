/**
 * Unit tests for the admin usage API helper (Trust & Privacy — T3).
 *
 * Follows the users-api.test.ts pattern: mock fetch, assert URL shape
 * and response parsing. Two tests: returns shape; 403 throws LQAIApiError.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { getUsage } from '../api/admin';
import type { UsageResponse } from '../types';
import { clearSession, setSession } from '../auth/store';
import { LQAIApiError } from '../api/client';

const realFetch = global.fetch;

function jsonResponse(status: number, body: unknown): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json' }
	});
}

const SAMPLE_USAGE: UsageResponse = {
	rows: [
		{
			group_key: 'anthropic',
			request_count: 42,
			tokens_in_sum: 10000,
			tokens_out_sum: 5000,
			cost_estimate_sum: 0.15
		},
		{
			group_key: 'ollama',
			request_count: 8,
			tokens_in_sum: 2000,
			tokens_out_sum: 800,
			cost_estimate_sum: 0
		}
	],
	group_by: 'provider',
	total_request_count: 50,
	total_tokens_in: 12000,
	total_tokens_out: 5800,
	total_cost_estimate: 0.15
};

describe('admin usage API', () => {
	beforeEach(() => {
		clearSession();
		setSession({ access_token: 'tok', expires_in: 900 });
		vi.restoreAllMocks();
	});

	afterEach(() => {
		global.fetch = realFetch;
	});

	it('getUsage returns the expected response shape', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, SAMPLE_USAGE));
		global.fetch = fetchSpy as unknown as typeof fetch;

		const out = await getUsage({ group_by: 'provider', date_from: '2026-05-11T00:00:00.000Z' });

		expect(out.group_by).toBe('provider');
		expect(out.total_request_count).toBe(50);
		expect(out.rows).toHaveLength(2);
		expect(out.rows[0].group_key).toBe('anthropic');
		expect(out.rows[1].group_key).toBe('ollama');

		const url = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[0];
		expect(url).toContain('/admin/usage');
		expect(url).toContain('group_by=provider');
		expect(url).toContain('date_from=');
	});

	it('getUsage surfaces 403 as LQAIApiError', async () => {
		global.fetch = vi.fn(async () =>
			jsonResponse(403, { detail: { code: 'forbidden', message: 'Admin only' } })
		) as unknown as typeof fetch;

		await expect(getUsage()).rejects.toBeInstanceOf(LQAIApiError);
		await expect(getUsage()).rejects.toMatchObject({ status: 403 });
	});
});
