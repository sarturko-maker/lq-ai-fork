/**
 * Unit tests for the enhance-prompt API client (T6).
 *
 * Mocks `fetch` so calls don't escape the test runner. Mirrors the pattern
 * used by saved-prompts-api.test.ts: jsonResponse helper, auth setup,
 * per-test fetch spy.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { enhance, recordOutcome } from '../api/enhancePrompt';
import type { EnhancePromptResponse } from '../types';
import { clearSession, setSession } from '../auth/store';
import { LQAIApiError } from '../api/client';

const realFetch = global.fetch;

function jsonResponse(status: number, body: unknown): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json' }
	});
}

const SAMPLE_APPLIED: EnhancePromptResponse = {
	interaction_id: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
	expansion_applied: true,
	expanded_prompt:
		'Please review the attached NDA for key risks including indemnification clauses, IP assignment, and non-compete scope.',
	reasoning: [
		'Added structured risk categories to guide the skill.',
		'Specified document type for accurate routing.'
	],
	skip_reason: null,
	preview_to_user: 'Your prompt was expanded with legal review structure.',
	routed_inference_tier: 2,
	routed_provider: 'openai',
	routed_model: 'gpt-4o'
};

const SAMPLE_SKIPPED: EnhancePromptResponse = {
	interaction_id: 'bbbbbbbb-cccc-dddd-eeee-ffffffffffff',
	expansion_applied: false,
	expanded_prompt: 'review this NDA for issues',
	reasoning: [],
	skip_reason: 'prompt_already_structured',
	preview_to_user: undefined
};

describe('enhance-prompt API', () => {
	beforeEach(() => {
		clearSession();
		setSession({ access_token: 'tok', expires_in: 900 });
		vi.restoreAllMocks();
	});

	afterEach(() => {
		global.fetch = realFetch;
	});

	it('enhance POSTs raw_input and returns the parsed response when expansion_applied=true', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, SAMPLE_APPLIED));
		global.fetch = fetchSpy as unknown as typeof fetch;

		const result = await enhance({ raw_input: 'review this NDA for issues' });

		expect(result.expansion_applied).toBe(true);
		expect(result.interaction_id).toBe(SAMPLE_APPLIED.interaction_id);
		expect(result.expanded_prompt).toContain('NDA');
		expect(result.reasoning).toHaveLength(2);

		const init = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[1];
		expect(init.method).toBe('POST');
		const parsed = JSON.parse(init.body as string);
		expect(parsed.raw_input).toBe('review this NDA for issues');
	});

	it('enhance handles expansion_applied=false with skip_reason', async () => {
		global.fetch = vi.fn(async () => jsonResponse(200, SAMPLE_SKIPPED)) as unknown as typeof fetch;

		const result = await enhance({ raw_input: 'review this NDA for issues' });

		expect(result.expansion_applied).toBe(false);
		expect(result.skip_reason).toBe('prompt_already_structured');
		expect(result.expanded_prompt).toBe('review this NDA for issues');
	});

	it('recordOutcome PATCHes { used: true, edited_before_use: false } for "use enhanced" action', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, SAMPLE_APPLIED));
		global.fetch = fetchSpy as unknown as typeof fetch;

		await recordOutcome(SAMPLE_APPLIED.interaction_id, { used: true, edited_before_use: false });

		const [url, init] = fetchSpy.mock.calls[0] as unknown as [string, RequestInit];
		expect(url).toContain(SAMPLE_APPLIED.interaction_id);
		expect(init.method).toBe('PATCH');
		const body = JSON.parse(init.body as string);
		expect(body.used).toBe(true);
		expect(body.edited_before_use).toBe(false);
	});

	it('recordOutcome PATCHes { used: true, edited_before_use: true } for "edit enhanced" action', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, SAMPLE_APPLIED));
		global.fetch = fetchSpy as unknown as typeof fetch;

		await recordOutcome(SAMPLE_APPLIED.interaction_id, { used: true, edited_before_use: true });

		const init = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[1];
		const body = JSON.parse(init.body as string);
		expect(body.used).toBe(true);
		expect(body.edited_before_use).toBe(true);
	});

	it('recordOutcome PATCHes { used: false } for "keep original" action', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, SAMPLE_SKIPPED));
		global.fetch = fetchSpy as unknown as typeof fetch;

		await recordOutcome(SAMPLE_SKIPPED.interaction_id, { used: false });

		const init = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[1];
		const body = JSON.parse(init.body as string);
		expect(body.used).toBe(false);
		expect(body.edited_before_use).toBeUndefined();
	});

	it('enhance surfaces 502 as LQAIApiError', async () => {
		global.fetch = vi.fn(async () =>
			jsonResponse(502, { detail: { code: 'gateway_error', message: 'Provider unavailable' } })
		) as unknown as typeof fetch;

		await expect(enhance({ raw_input: 'test' })).rejects.toBeInstanceOf(LQAIApiError);
	});
});
