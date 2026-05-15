/**
 * Unit tests for skillsApi.getInputs — GET /api/v1/skills/{name}/inputs.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { getInputs } from '../api/skills';
import type { SkillInputs } from '../types';
import { clearSession, setSession } from '../auth/store';

const realFetch = global.fetch;

function jsonResponse(status: number, body: unknown): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json' }
	});
}

const SAMPLE_INPUTS: SkillInputs = {
	name: 'nda-review',
	required: [
		{
			name: 'perspective',
			type: 'enum',
			enum: ['recipient', 'discloser', 'both'],
			required: true,
			description: 'Which party perspective to adopt'
		}
	],
	optional: [
		{
			name: 'matter_name',
			type: 'string',
			required: false,
			description: 'Matter label for the output header'
		}
	]
};

describe('skillsApi.getInputs', () => {
	beforeEach(() => {
		clearSession();
		setSession({ access_token: 'tok', expires_in: 900 });
		vi.restoreAllMocks();
	});

	afterEach(() => {
		global.fetch = realFetch;
	});

	it('returns the SkillInputs shape with required and optional arrays', async () => {
		global.fetch = vi.fn(async () => jsonResponse(200, SAMPLE_INPUTS)) as unknown as typeof fetch;
		const out = await getInputs('nda-review');
		expect(out.name).toBe('nda-review');
		expect(out.required).toHaveLength(1);
		expect(out.required[0].name).toBe('perspective');
		expect(out.required[0].type).toBe('enum');
		expect(out.optional).toHaveLength(1);
		expect(out.optional[0].name).toBe('matter_name');
	});

	it('URL-encodes the skill name in the request path', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, { name: 'my skill', required: [], optional: [] }));
		global.fetch = fetchSpy as unknown as typeof fetch;
		await getInputs('my skill/with-slashes');
		const url = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[0];
		expect(url).toContain('my%20skill%2Fwith-slashes');
		expect(url).toContain('/inputs');
	});
});
