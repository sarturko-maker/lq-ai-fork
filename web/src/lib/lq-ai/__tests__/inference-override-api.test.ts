/**
 * Unit tests for the inference tier-floor override API helper.
 *
 * Mocks `fetch` so calls don't escape the test runner. Mirrors the pattern
 * from project-knowledge-bases-api.test.ts: jsonResponse helper + setSession
 * to satisfy the auth header; inspect the Request init to confirm method,
 * URL, and body shape.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { overrideTierFloor } from '../api/inferenceOverride';
import type { Message } from '../types';
import { clearSession, setSession } from '../auth/store';

const realFetch = global.fetch;

function jsonResponse(status: number, body: unknown): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json' }
	});
}

const SAMPLE_AI_MESSAGE: Message = {
	id: 'msg-ai-001',
	chat_id: 'chat-001',
	role: 'assistant',
	content: 'Here is the re-run answer.',
	routed_inference_tier: 4,
	routed_provider: 'anthropic',
	routed_model: 'claude-opus-4-7',
	requested_model: 'claude-opus-4-7',
	prompt_tokens: 120,
	completion_tokens: 240,
	cost_estimate: 0.0123,
	created_at: '2026-05-12T02:00:00Z'
};

describe('inferenceOverride api', () => {
	beforeEach(() => {
		clearSession();
		setSession({ access_token: 'test-token', expires_in: 900 });
		vi.restoreAllMocks();
	});

	afterEach(() => {
		global.fetch = realFetch;
	});

	it('overrideTierFloor POSTs to /inference/override-tier-floor with {message_id, reason} and returns OverrideResponse', async () => {
		const fetchSpy = vi.fn(async () =>
			jsonResponse(200, {
				ai_message: SAMPLE_AI_MESSAGE,
				routing_log_id: 'rl-001'
			})
		);
		global.fetch = fetchSpy as unknown as typeof fetch;

		const result = await overrideTierFloor(
			'msg-refusal-001',
			'Admin override: original refusal was overly conservative on this matter.'
		);

		// Check return shape
		expect(result.ai_message.id).toBe('msg-ai-001');
		expect(result.ai_message.role).toBe('assistant');
		expect(result.routing_log_id).toBe('rl-001');

		// Check request shape
		const [url, init] = fetchSpy.mock.calls[0] as unknown as [string, RequestInit];
		expect(url).toContain('/api/v1/inference/override-tier-floor');
		expect(init.method).toBe('POST');
		const body = JSON.parse(init.body as string);
		expect(body).toEqual({
			message_id: 'msg-refusal-001',
			reason: 'Admin override: original refusal was overly conservative on this matter.'
		});
	});

	it('overrideTierFloor accepts null routing_log_id (gateway-mocked path)', async () => {
		const fetchSpy = vi.fn(async () =>
			jsonResponse(200, {
				ai_message: SAMPLE_AI_MESSAGE,
				routing_log_id: null
			})
		);
		global.fetch = fetchSpy as unknown as typeof fetch;

		const result = await overrideTierFloor(
			'msg-refusal-001',
			'Admin override: see audit notes.'
		);

		expect(result.routing_log_id).toBeNull();
		expect(result.ai_message.id).toBe('msg-ai-001');
	});

	it('overrideTierFloor throws on 403 admin-gating refusal', async () => {
		const fetchSpy = vi.fn(async () =>
			jsonResponse(403, {
				detail: { code: 'forbidden', message: 'Admin role required' }
			})
		);
		global.fetch = fetchSpy as unknown as typeof fetch;

		await expect(
			overrideTierFloor('msg-refusal-001', 'Admin override: please re-run.')
		).rejects.toThrow(/admin/i);
	});

	it('overrideTierFloor throws on 422 reason-too-short validation error', async () => {
		const fetchSpy = vi.fn(async () =>
			jsonResponse(422, {
				detail: { code: 'validation_error', message: 'reason must be at least 10 characters' }
			})
		);
		global.fetch = fetchSpy as unknown as typeof fetch;

		await expect(overrideTierFloor('msg-refusal-001', 'too short')).rejects.toThrow(
			/10 characters/i
		);
	});
});
