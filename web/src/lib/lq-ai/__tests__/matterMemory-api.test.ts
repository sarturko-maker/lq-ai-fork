/**
 * Unit tests for the matter-memory API helpers (C3c-2).
 *
 * Mocks `fetch` so calls don't escape the test runner (mirrors
 * projects-attach-api.test.ts): jsonResponse helper + setSession to satisfy the
 * auth header; inspect the Request init to confirm method, URL encoding, and
 * body shape; confirm the typed response parses through.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { readMatterMemory, revertWiki } from '../api/matterMemory';
import type { MatterMemoryRead, WikiRevertResponse } from '../types';
import { clearSession, setSession } from '../auth/store';

const realFetch = global.fetch;

function jsonResponse(status: number, body: unknown): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json' }
	});
}

const SAMPLE_MEMORY: MatterMemoryRead = {
	project_id: 'proj-abc123',
	wiki: { content_md: '# Summary\n\nAcme MSA renewal.', char_count: 27, version_count: 2 },
	facts: [
		{
			id: 'fact-1',
			body_md: 'Governing law is England & Wales.',
			fact_type: 'term',
			source_citation: 'MSA §18.2',
			author: 'agent',
			valid_at: '2026-05-01T00:00:00Z',
			created_at: '2026-05-02T00:00:00Z'
		}
	],
	corrections: [
		{
			id: 'corr-1',
			body_md: 'The counterparty entity is Acme UK Ltd, not Acme Inc.',
			trust: 'pinned',
			created_at: '2026-05-03T00:00:00Z'
		}
	],
	log: [
		{
			id: 'snap-1',
			kind: 'wiki_snapshot',
			created_at: '2026-05-04T00:00:00Z',
			run_id: 'run-deadbeef-0001',
			author: 'agent',
			fact_type: null,
			source_citation: null,
			superseded: false,
			body_preview: 'Prior summary…'
		}
	],
	log_total: 5
};

const SAMPLE_REVERT: WikiRevertResponse = {
	reverted_to_snapshot_id: 'snap-1',
	snapshotted_prior: true,
	wiki: { content_md: 'Prior summary', char_count: 13, version_count: 3 }
};

describe('matter memory API', () => {
	beforeEach(() => {
		clearSession();
		setSession({ access_token: 'test-token', expires_in: 900 });
		vi.restoreAllMocks();
	});

	afterEach(() => {
		global.fetch = realFetch;
	});

	it('readMatterMemory GETs /matters/{id}/memory and parses the composite', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, SAMPLE_MEMORY));
		global.fetch = fetchSpy as unknown as typeof fetch;

		const result = await readMatterMemory('proj-abc123');

		expect(result.project_id).toBe('proj-abc123');
		expect(result.wiki.version_count).toBe(2);
		expect(result.facts).toHaveLength(1);
		expect(result.corrections[0].trust).toBe('pinned');
		expect(result.log[0].kind).toBe('wiki_snapshot');
		expect(result.log_total).toBe(5);

		const [url, init] = fetchSpy.mock.calls[0] as unknown as [string, RequestInit];
		expect(url).toContain('/matters/proj-abc123/memory');
		expect(init.method ?? 'GET').toBe('GET');
	});

	it('readMatterMemory URL-encodes the project id', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, SAMPLE_MEMORY));
		global.fetch = fetchSpy as unknown as typeof fetch;

		await readMatterMemory('a/b c');

		const [url] = fetchSpy.mock.calls[0] as unknown as [string, RequestInit];
		// encodeURIComponent('a/b c') === 'a%2Fb%20c'
		expect(url).toContain('/matters/a%2Fb%20c/memory');
	});

	it('revertWiki POSTs the revert URL with {snapshot_id} and parses the response', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, SAMPLE_REVERT));
		global.fetch = fetchSpy as unknown as typeof fetch;

		const result = await revertWiki('proj-abc123', 'snap-1');

		expect(result.reverted_to_snapshot_id).toBe('snap-1');
		expect(result.snapshotted_prior).toBe(true);
		expect(result.wiki.version_count).toBe(3);

		const [url, init] = fetchSpy.mock.calls[0] as unknown as [string, RequestInit];
		expect(url).toContain('/matters/proj-abc123/memory/wiki/revert');
		expect(init.method).toBe('POST');
		const body = JSON.parse(init.body as string);
		expect(body).toEqual({ snapshot_id: 'snap-1' });
	});
});
