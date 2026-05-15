/**
 * Unit tests for the project knowledge-base attach/detach API helpers.
 *
 * Mocks `fetch` so calls don't escape the test runner. Mirrors the pattern
 * from projects-attach-api.test.ts: jsonResponse helper + setSession to
 * satisfy the auth header; inspect the Request init to confirm method,
 * URL encoding, and body shape.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { attachKnowledgeBase, detachKnowledgeBase } from '../api/projectKnowledgeBases';
import type { Project } from '../types';
import { clearSession, setSession } from '../auth/store';

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

const SAMPLE_PROJECT: Project = {
	id: 'proj-abc123',
	name: 'Acme NDA',
	slug: 'acme-nda',
	description: 'Review the Acme NDA.',
	owner_id: 'user-001',
	privileged: false,
	minimum_inference_tier: null,
	attached_file_ids: [],
	attached_skill_names: [],
	attached_knowledge_base_ids: ['kb-001'],
	created_at: '2026-05-12T00:00:00Z',
	updated_at: '2026-05-12T01:00:00Z'
};

describe('projectKnowledgeBases api', () => {
	beforeEach(() => {
		clearSession();
		setSession({ access_token: 'test-token', expires_in: 900 });
		vi.restoreAllMocks();
	});

	afterEach(() => {
		global.fetch = realFetch;
	});

	it('attachKnowledgeBase POSTs to /projects/{id}/knowledge-bases with body and returns Project', async () => {
		const fetchSpy = vi.fn(async () =>
			jsonResponse(200, { ...SAMPLE_PROJECT, attached_knowledge_base_ids: ['kb-001'] })
		);
		global.fetch = fetchSpy as unknown as typeof fetch;

		const result = await attachKnowledgeBase('proj-abc123', 'kb-001');

		// Check return shape
		expect(result.id).toBe('proj-abc123');
		expect(result.attached_knowledge_base_ids).toContain('kb-001');

		// Check request shape
		const [url, init] = fetchSpy.mock.calls[0] as unknown as [string, RequestInit];
		expect(url).toContain('/api/v1/projects/proj-abc123/knowledge-bases');
		expect(init.method).toBe('POST');
		const body = JSON.parse(init.body as string);
		expect(body).toEqual({ knowledge_base_id: 'kb-001' });
	});

	it('detachKnowledgeBase DELETEs to /projects/{id}/knowledge-bases/{kbId} and resolves void on 204', async () => {
		const fetchSpy = vi.fn(async () => emptyResponse(204));
		global.fetch = fetchSpy as unknown as typeof fetch;

		const result = await detachKnowledgeBase('proj-abc123', 'kb-001');

		// 204 → undefined
		expect(result).toBeUndefined();

		// Check request shape
		const [url, init] = fetchSpy.mock.calls[0] as unknown as [string, RequestInit];
		expect(url).toContain('/api/v1/projects/proj-abc123/knowledge-bases/kb-001');
		expect(init.method).toBe('DELETE');
	});

	it('attachKnowledgeBase throws descriptive error on 404', async () => {
		const fetchSpy = vi.fn(async () =>
			jsonResponse(404, {
				detail: { code: 'not_found', message: 'Knowledge base not found' }
			})
		);
		global.fetch = fetchSpy as unknown as typeof fetch;

		await expect(attachKnowledgeBase('proj-abc123', 'kb-missing')).rejects.toThrow(/not found/i);
	});

	it('detachKnowledgeBase throws on 403', async () => {
		const fetchSpy = vi.fn(async () =>
			jsonResponse(403, {
				detail: { code: 'forbidden', message: 'Forbidden' }
			})
		);
		global.fetch = fetchSpy as unknown as typeof fetch;

		await expect(detachKnowledgeBase('proj-abc123', 'kb-001')).rejects.toThrow();
	});
});
