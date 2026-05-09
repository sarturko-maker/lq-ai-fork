/**
 * Unit tests for the LQ.AI shell's model-picker API client (D0).
 *
 * Covers `listModels()`, `groupModels()`, `defaultSelection()` — the
 * three pure functions that drive the picker UI.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
	defaultSelection,
	groupModels,
	listModels,
	type ModelEntry,
	type ModelListResponse
} from '../api/models';
import { clearSession, setSession } from '../auth/store';

const realFetch = global.fetch;

function jsonResponse(status: number, body: unknown): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json' }
	});
}

const SAMPLE: ModelListResponse = {
	object: 'list',
	data: [
		{ id: 'smart', object: 'model', created: 0, owned_by: 'lq-ai-gateway', lq_ai_kind: 'alias' },
		{ id: 'fast', object: 'model', created: 0, owned_by: 'lq-ai-gateway', lq_ai_kind: 'alias' },
		{
			id: 'anthropic-prod/claude-haiku-4-5',
			object: 'model',
			created: 0,
			owned_by: 'anthropic-prod',
			lq_ai_kind: 'provider_native',
			routed_inference_tier: 4,
			provider_type: 'anthropic'
		},
		{
			id: 'ollama-local/llama3.1:8b',
			object: 'model',
			created: 0,
			owned_by: 'ollama-local',
			lq_ai_kind: 'provider_native',
			routed_inference_tier: 1,
			provider_type: 'ollama'
		},
		{
			id: 'ollama-local/qwen2.5:7b',
			object: 'model',
			created: 0,
			owned_by: 'ollama-local',
			lq_ai_kind: 'provider_native',
			routed_inference_tier: 1,
			provider_type: 'ollama'
		}
	]
};

describe('listModels', () => {
	beforeEach(() => {
		clearSession();
		setSession({ access_token: 'tok', expires_in: 900 });
		vi.restoreAllMocks();
	});

	afterEach(() => {
		global.fetch = realFetch;
	});

	it('parses the merged response shape', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, SAMPLE));
		global.fetch = fetchSpy as unknown as typeof fetch;

		const out = await listModels();
		expect(out.object).toBe('list');
		expect(out.data.length).toBe(5);
		expect(out.data[0].lq_ai_kind).toBe('alias');
	});

	it('attaches Authorization on the request', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, SAMPLE));
		global.fetch = fetchSpy as unknown as typeof fetch;
		await listModels();
		const init = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[1];
		const headers = init.headers as Record<string, string>;
		expect(headers.Authorization).toBe('Bearer tok');
	});
});

describe('groupModels', () => {
	it('separates aliases from native rows', () => {
		const grouped = groupModels(SAMPLE);
		expect(grouped.aliases.map((a) => a.id)).toEqual(['smart', 'fast']);
		expect([...grouped.nativeByProvider.keys()]).toEqual(['anthropic-prod', 'ollama-local']);
	});

	it('sorts native entries within each provider group by id', () => {
		const grouped = groupModels(SAMPLE);
		const ollama = grouped.nativeByProvider.get('ollama-local');
		expect(ollama?.map((e) => e.id)).toEqual([
			'ollama-local/llama3.1:8b',
			'ollama-local/qwen2.5:7b'
		]);
	});

	it('returns empty groups for an empty list', () => {
		const grouped = groupModels({ object: 'list', data: [] });
		expect(grouped.aliases).toEqual([]);
		expect(grouped.nativeByProvider.size).toBe(0);
	});
});

describe('defaultSelection', () => {
	it("prefers the 'smart' alias when present", () => {
		const grouped = groupModels(SAMPLE);
		expect(defaultSelection(grouped)?.id).toBe('smart');
	});

	it('falls back to the first alias when smart is absent', () => {
		const noSmart: ModelListResponse = {
			object: 'list',
			data: SAMPLE.data.filter((e) => e.id !== 'smart')
		};
		const grouped = groupModels(noSmart);
		expect(defaultSelection(grouped)?.id).toBe('fast');
	});

	it('falls back to a native row when no aliases exist', () => {
		const onlyNative: ModelListResponse = {
			object: 'list',
			data: SAMPLE.data.filter((e) => e.lq_ai_kind === 'provider_native')
		};
		const grouped = groupModels(onlyNative);
		expect(defaultSelection(grouped)?.id).toBe('anthropic-prod/claude-haiku-4-5');
	});

	it('returns null on an empty list', () => {
		const grouped = groupModels({ object: 'list', data: [] });
		expect(defaultSelection(grouped)).toBeNull();
	});
});

describe('ModelEntry shape', () => {
	it('discriminates alias vs provider_native', () => {
		const entries: ModelEntry[] = SAMPLE.data;
		const aliases = entries.filter((e) => e.lq_ai_kind === 'alias');
		const native = entries.filter((e) => e.lq_ai_kind === 'provider_native');
		expect(aliases.length).toBe(2);
		expect(native.length).toBe(3);
		// Aliases have no tier; native rows do.
		expect(aliases.every((e) => e.routed_inference_tier === undefined)).toBe(true);
		expect(native.every((e) => typeof e.routed_inference_tier === 'number')).toBe(true);
	});
});
