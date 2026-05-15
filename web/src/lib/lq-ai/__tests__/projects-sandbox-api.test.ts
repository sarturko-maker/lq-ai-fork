/**
 * Unit tests for the Wave D.2 sandbox + sandbox-aware listing
 * helpers on ``api/projects.ts``.
 *
 * Covers:
 *   * ``ensureSandbox()`` — POST ``/projects/sandbox/ensure`` (no body)
 *   * ``listProjects({ includeSandbox, onlySandbox })`` — the new
 *     query-param flags introduced in Wave D.2 Task 2.3.
 *
 * Mirrors the pattern in ``projects-attach-api.test.ts``.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ensureSandbox, listProjects } from '../api/projects';
import type { Project } from '../types';
import { clearSession, setSession } from '../auth/store';

const realFetch = global.fetch;

function jsonResponse(status: number, body: unknown): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json' }
	});
}

const SANDBOX_PROJECT: Project = {
	id: 'proj-sandbox-001',
	name: 'Try-it sandbox',
	slug: '__sandbox__',
	description: 'Auto-created sandbox for skill try-it.',
	owner_id: 'user-001',
	privileged: false,
	minimum_inference_tier: null,
	attached_file_ids: [],
	attached_skill_names: [],
	is_sandbox: true,
	created_at: '2026-05-13T00:00:00Z',
	updated_at: '2026-05-13T00:00:00Z'
};

describe('ensureSandbox', () => {
	beforeEach(() => {
		clearSession();
		setSession({ access_token: 'tok', expires_in: 900 });
		vi.restoreAllMocks();
	});

	afterEach(() => {
		global.fetch = realFetch;
	});

	it('POSTs /projects/sandbox/ensure with an empty body and returns the Project', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, SANDBOX_PROJECT));
		global.fetch = fetchSpy as unknown as typeof fetch;

		const result = await ensureSandbox();

		expect(result.id).toBe('proj-sandbox-001');
		expect(result.is_sandbox).toBe(true);

		const [url, init] = fetchSpy.mock.calls[0] as unknown as [string, RequestInit];
		expect(url).toContain('/api/v1/projects/sandbox/ensure');
		expect(init.method).toBe('POST');
	});

	it('handles the 201 path on first create', async () => {
		global.fetch = vi.fn(async () =>
			jsonResponse(201, SANDBOX_PROJECT)
		) as unknown as typeof fetch;

		const result = await ensureSandbox();
		expect(result.is_sandbox).toBe(true);
	});
});

describe('listProjects sandbox filters', () => {
	beforeEach(() => {
		clearSession();
		setSession({ access_token: 'tok', expires_in: 900 });
		vi.restoreAllMocks();
	});

	afterEach(() => {
		global.fetch = realFetch;
	});

	it('appends include_sandbox=true when requested', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, []));
		global.fetch = fetchSpy as unknown as typeof fetch;

		await listProjects({ includeSandbox: true });

		const url = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[0];
		expect(url).toContain('include_sandbox=true');
	});

	it('appends only_sandbox=true when requested', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, []));
		global.fetch = fetchSpy as unknown as typeof fetch;

		await listProjects({ onlySandbox: true });

		const url = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[0];
		expect(url).toContain('only_sandbox=true');
	});

	it('omits sandbox query params by default', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, []));
		global.fetch = fetchSpy as unknown as typeof fetch;

		await listProjects();

		const url = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[0];
		expect(url).not.toContain('include_sandbox');
		expect(url).not.toContain('only_sandbox');
	});

	it('still supports the archived flag alongside sandbox flags', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, []));
		global.fetch = fetchSpy as unknown as typeof fetch;

		await listProjects({ archived: true, includeSandbox: true });

		const url = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[0];
		expect(url).toContain('archived=true');
		expect(url).toContain('include_sandbox=true');
	});
});
