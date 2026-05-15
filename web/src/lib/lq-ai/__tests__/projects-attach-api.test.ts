/**
 * Unit tests for the project file + skill attach/detach API helpers.
 *
 * Mocks `fetch` so calls don't escape the test runner. Mirrors the pattern
 * from saved-prompts-api.test.ts: jsonResponse helper + setSession to
 * satisfy the auth header; inspect the Request init to confirm method,
 * URL encoding, and body shape.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { attachFile, detachFile, attachSkill, detachSkill } from '../api/projects';
import type { Project } from '../types';
import { clearSession, setSession } from '../auth/store';

const realFetch = global.fetch;

function jsonResponse(status: number, body: unknown): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json' }
	});
}

const SAMPLE_PROJECT: Project = {
	id: 'proj-abc123',
	name: 'Acme NDA',
	slug: 'acme-nda',
	description: 'Review the Acme NDA.',
	owner_id: 'user-001',
	privileged: false,
	minimum_inference_tier: null,
	attached_file_ids: ['file-001'],
	attached_skill_names: ['nda-review'],
	created_at: '2026-05-12T00:00:00Z',
	updated_at: '2026-05-12T01:00:00Z'
};

describe('projects attach/detach API', () => {
	beforeEach(() => {
		clearSession();
		setSession({ access_token: 'test-token', expires_in: 900 });
		vi.restoreAllMocks();
	});

	afterEach(() => {
		global.fetch = realFetch;
	});

	// ---- File helpers ----

	it('attachFile POSTs /projects/{id}/files with file_id body and returns Project', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, { ...SAMPLE_PROJECT, attached_file_ids: ['file-001', 'file-002'] }));
		global.fetch = fetchSpy as unknown as typeof fetch;

		const result = await attachFile('proj-abc123', 'file-002');

		// Check return shape
		expect(result.id).toBe('proj-abc123');
		expect(result.attached_file_ids).toContain('file-002');

		// Check request shape
		const [url, init] = fetchSpy.mock.calls[0] as unknown as [string, RequestInit];
		expect(url).toContain('/projects/proj-abc123/files');
		expect(init.method).toBe('POST');
		const body = JSON.parse(init.body as string);
		expect(body).toEqual({ file_id: 'file-002' });
	});

	it('detachFile DELETEs /projects/{id}/files/{file_id} and returns Project', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, { ...SAMPLE_PROJECT, attached_file_ids: [] }));
		global.fetch = fetchSpy as unknown as typeof fetch;

		const result = await detachFile('proj-abc123', 'file-001');

		// Check return shape
		expect(result.id).toBe('proj-abc123');
		expect(result.attached_file_ids).toHaveLength(0);

		// Check request shape
		const [url, init] = fetchSpy.mock.calls[0] as unknown as [string, RequestInit];
		expect(url).toContain('/projects/proj-abc123/files/file-001');
		expect(init.method).toBe('DELETE');
	});

	// ---- Skill helpers ----

	it('attachSkill POSTs /projects/{id}/skills with skill_name body and returns Project', async () => {
		const fetchSpy = vi.fn(async () =>
			jsonResponse(200, { ...SAMPLE_PROJECT, attached_skill_names: ['nda-review', 'msa-review'] })
		);
		global.fetch = fetchSpy as unknown as typeof fetch;

		const result = await attachSkill('proj-abc123', 'msa-review');

		expect(result.id).toBe('proj-abc123');
		expect(result.attached_skill_names).toContain('msa-review');

		const [url, init] = fetchSpy.mock.calls[0] as unknown as [string, RequestInit];
		expect(url).toContain('/projects/proj-abc123/skills');
		expect(init.method).toBe('POST');
		const body = JSON.parse(init.body as string);
		expect(body).toEqual({ skill_name: 'msa-review' });
	});

	it('detachSkill DELETEs /projects/{id}/skills/{skill_name} with URL encoding and returns Project', async () => {
		const fetchSpy = vi.fn(async () =>
			jsonResponse(200, { ...SAMPLE_PROJECT, attached_skill_names: [] })
		);
		global.fetch = fetchSpy as unknown as typeof fetch;

		// Use a skill name with a slash to exercise encodeURIComponent
		const result = await detachSkill('proj-abc123', 'team/nda-review');

		expect(result.id).toBe('proj-abc123');
		expect(result.attached_skill_names).toHaveLength(0);

		const [url, init] = fetchSpy.mock.calls[0] as unknown as [string, RequestInit];
		// encodeURIComponent('team/nda-review') === 'team%2Fnda-review'
		expect(url).toContain('/projects/proj-abc123/skills/team%2Fnda-review');
		expect(init.method).toBe('DELETE');
	});
});
