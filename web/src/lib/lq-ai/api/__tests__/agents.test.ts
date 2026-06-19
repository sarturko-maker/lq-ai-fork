/**
 * Unit tests for the agents API client (F0-S3).
 *
 * Mocks ``globalThis.fetch`` so calls don't escape the test runner.
 * Mirrors the autonomous-api / playbooks-api test shape: regressions in the
 * shared ``apiRequest`` helper (URL construction, error translation)
 * surface here too.
 *
 * Focus: URL construction + request-body serialization. Full schema
 * round-trip coverage lives in the API integration tests
 * (api/tests/agents/test_agent_runs_api.py).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { cancelRun, createRun, getRun, getThread, listRuns, listThreads } from '../agents';

/** Minimal Response-shaped stub. apiRequest reads content-type to decide json/text. */
function jsonResponseLike(status: number, body: unknown) {
	return {
		ok: status >= 200 && status < 300,
		status,
		headers: {
			get: (name: string) => (name.toLowerCase() === 'content-type' ? 'application/json' : null)
		},
		json: async () => body
	};
}

/** Extracts the URL string and init from the first fetchMock call. */
function firstCall(fetchMock: ReturnType<typeof vi.fn>): [string, RequestInit] {
	return fetchMock.mock.calls[0] as [string, RequestInit];
}

describe('agents API client', () => {
	const fetchMock = vi.fn();
	let originalFetch: typeof globalThis.fetch;

	beforeEach(() => {
		originalFetch = globalThis.fetch;
		globalThis.fetch = fetchMock as unknown as typeof globalThis.fetch;
		fetchMock.mockReset();
	});

	afterEach(() => {
		globalThis.fetch = originalFetch;
	});

	it('createRun POSTs the body to /agents/runs', async () => {
		fetchMock.mockResolvedValueOnce(jsonResponseLike(202, { id: 'r1', status: 'running' }));
		const run = await createRun({ prompt: 'What is the liability cap?' });
		expect(run.id).toBe('r1');
		const [url, init] = firstCall(fetchMock);
		expect(url).toMatch(/\/agents\/runs$/);
		expect(init.method).toBe('POST');
		expect(JSON.parse(init.body as string)).toEqual({ prompt: 'What is the liability cap?' });
	});

	it('createRun forwards optional model_alias and max_steps', async () => {
		fetchMock.mockResolvedValueOnce(jsonResponseLike(202, { id: 'r2', status: 'running' }));
		await createRun({ prompt: 'p', model_alias: 'fast', max_steps: 5 });
		const [, init] = firstCall(fetchMock);
		expect(JSON.parse(init.body as string)).toEqual({
			prompt: 'p',
			model_alias: 'fast',
			max_steps: 5
		});
	});

	it('createRun forwards the matter binding (F0-S4)', async () => {
		fetchMock.mockResolvedValueOnce(
			jsonResponseLike(202, { id: 'r3', status: 'running', project_id: 'proj-1' })
		);
		const run = await createRun({ prompt: 'p', project_id: 'proj-1' });
		expect(run.project_id).toBe('proj-1');
		const [, init] = firstCall(fetchMock);
		expect(JSON.parse(init.body as string)).toEqual({ prompt: 'p', project_id: 'proj-1' });
	});

	it('getRun GETs /agents/runs/{id} with the id URL-encoded', async () => {
		fetchMock.mockResolvedValueOnce(
			jsonResponseLike(200, { run: { id: 'a/b', status: 'completed' }, steps: [] })
		);
		const detail = await getRun('a/b');
		expect(detail.steps).toEqual([]);
		const [url] = firstCall(fetchMock);
		expect(url).toMatch(/\/agents\/runs\/a%2Fb$/);
	});

	it('listRuns GETs /agents/runs without params by default', async () => {
		fetchMock.mockResolvedValueOnce(
			jsonResponseLike(200, { runs: [], total_count: 0, limit: 50, offset: 0 })
		);
		await listRuns();
		const [url] = firstCall(fetchMock);
		expect(url).toMatch(/\/agents\/runs$/);
	});

	it('listRuns serializes limit and offset as query params', async () => {
		fetchMock.mockResolvedValueOnce(
			jsonResponseLike(200, { runs: [], total_count: 0, limit: 20, offset: 40 })
		);
		await listRuns({ limit: 20, offset: 40 });
		const [url] = firstCall(fetchMock);
		expect(url).toMatch(/\/agents\/runs\?limit=20&offset=40$/);
	});

	it('createRun forwards thread_id for follow-ups (F0-S5)', async () => {
		fetchMock.mockResolvedValueOnce(
			jsonResponseLike(202, { id: 'r4', status: 'running', thread_id: 't1' })
		);
		const run = await createRun({ prompt: 'and the indemnity?', thread_id: 't1' });
		expect(run.thread_id).toBe('t1');
		const [, init] = firstCall(fetchMock);
		expect(JSON.parse(init.body as string)).toEqual({
			prompt: 'and the indemnity?',
			thread_id: 't1'
		});
	});

	it('listThreads GETs /agents/threads with optional pagination', async () => {
		fetchMock.mockResolvedValueOnce(
			jsonResponseLike(200, { threads: [], total_count: 0, limit: 50, offset: 0 })
		);
		await listThreads();
		expect(firstCall(fetchMock)[0]).toMatch(/\/agents\/threads$/);

		fetchMock.mockResolvedValueOnce(
			jsonResponseLike(200, { threads: [], total_count: 0, limit: 20, offset: 40 })
		);
		await listThreads({ limit: 20, offset: 40 });
		expect(fetchMock.mock.calls[1][0]).toMatch(/\/agents\/threads\?limit=20&offset=40$/);
	});

	it('getThread GETs /agents/threads/{id} with the id URL-encoded', async () => {
		fetchMock.mockResolvedValueOnce(
			jsonResponseLike(200, {
				thread: { id: 'a/b' },
				runs: [],
				continuable: false
			})
		);
		const detail = await getThread('a/b');
		expect(detail.continuable).toBe(false);
		expect(firstCall(fetchMock)[0]).toMatch(/\/agents\/threads\/a%2Fb$/);
	});

	it('cancelRun POSTs to /agents/runs/{id}/cancel with the id URL-encoded (PRIV-9a)', async () => {
		fetchMock.mockResolvedValueOnce(
			jsonResponseLike(200, { id: 'a/b', status: 'cancelled', thread_id: 't1' })
		);
		const run = await cancelRun('a/b');
		expect(run.status).toBe('cancelled');
		const [url, init] = firstCall(fetchMock);
		expect(url).toMatch(/\/agents\/runs\/a%2Fb\/cancel$/);
		expect(init.method).toBe('POST');
	});

	it('cancelRun surfaces a 404 (cross-user / unknown run) as a typed error', async () => {
		fetchMock.mockResolvedValueOnce(jsonResponseLike(404, { detail: 'run not found' }));
		await expect(cancelRun('nope')).rejects.toMatchObject({ status: 404 });
	});

	it('translates the 409 thread brakes into typed errors (plain-string detail)', async () => {
		fetchMock.mockResolvedValueOnce(jsonResponseLike(409, { detail: 'thread_busy' }));
		await expect(createRun({ prompt: 'p', thread_id: 't1' })).rejects.toMatchObject({
			status: 409,
			code: 'http_409',
			message: 'thread_busy'
		});
	});

	it('translates the 429 flood brake into a typed error (plain-string detail on the wire)', async () => {
		// The backend raises HTTPException(429, detail="too_many_running_runs")
		// — a STRING detail (api/app/api/agent_runs.py; pinned by the api's
		// test_agent_runs_api.py). errorFor() maps string details to a
		// synthetic http_NNN code with the string as the message. Do NOT
		// branch on code === 'too_many_running_runs'; it never occurs.
		fetchMock.mockResolvedValueOnce(jsonResponseLike(429, { detail: 'too_many_running_runs' }));
		await expect(createRun({ prompt: 'p' })).rejects.toMatchObject({
			status: 429,
			code: 'http_429',
			message: 'too_many_running_runs'
		});
	});
});
