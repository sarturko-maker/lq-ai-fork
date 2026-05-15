/**
 * Unit tests for the users API client (export + delete flows).
 *
 * Follows the saved-prompts-api.test.ts pattern: mock fetch, assert on
 * URL shape / method / response parsing.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { cancelDeletion, getExportJob, requestDeletion, startExport } from '../api/users';
import type { DeleteScheduledResponse, ExportJob } from '../types';
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

const EXPORT_JOB_QUEUED: ExportJob = {
	job_id: 'a1b2c3d4-0000-0000-0000-000000000001',
	status: 'queued',
	download_url: null
};

const EXPORT_JOB_DONE: ExportJob = {
	job_id: 'a1b2c3d4-0000-0000-0000-000000000001',
	status: 'completed',
	download_url: 'https://storage.example.com/exports/a1b2c3d4.zip?sig=x'
};

const DELETE_RESPONSE: DeleteScheduledResponse = {
	scheduled_deletion_at: '2026-06-10T12:00:00Z',
	grace_period_days: 30
};

describe('users API', () => {
	beforeEach(() => {
		clearSession();
		setSession({ access_token: 'tok', expires_in: 900 });
		vi.restoreAllMocks();
	});

	afterEach(() => {
		global.fetch = realFetch;
	});

	it('startExport POSTs to /users/me/export and returns job shape', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(202, EXPORT_JOB_QUEUED));
		global.fetch = fetchSpy as unknown as typeof fetch;
		const out = await startExport();
		expect(out.job_id).toBe(EXPORT_JOB_QUEUED.job_id);
		expect(out.status).toBe('queued');
		const init = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[1];
		expect(init.method).toBe('POST');
	});

	it('getExportJob encodes the job_id in the URL path', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, EXPORT_JOB_DONE));
		global.fetch = fetchSpy as unknown as typeof fetch;
		const out = await getExportJob(EXPORT_JOB_DONE.job_id);
		expect(out.status).toBe('completed');
		expect(out.download_url).toContain('storage.example.com');
		const url = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[0];
		expect(url).toContain(encodeURIComponent(EXPORT_JOB_DONE.job_id));
	});

	it('requestDeletion POSTs and returns the scheduled date + grace period', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(202, DELETE_RESPONSE));
		global.fetch = fetchSpy as unknown as typeof fetch;
		const out = await requestDeletion();
		expect(out.scheduled_deletion_at).toBe('2026-06-10T12:00:00Z');
		expect(out.grace_period_days).toBe(30);
		const init = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[1];
		expect(init.method).toBe('POST');
	});

	it('cancelDeletion POSTs to /users/me/delete/cancel and surfaces 400 as LQAIApiError', async () => {
		global.fetch = vi.fn(async () =>
			jsonResponse(400, { detail: { code: 'no_pending_deletion', message: 'No pending deletion' } })
		) as unknown as typeof fetch;
		await expect(cancelDeletion()).rejects.toBeInstanceOf(LQAIApiError);
	});
});
