/**
 * Pure-helper tests for the /lq-ai/admin/capabilities page (SETUP-4b).
 * Shared helpers (describeMutationError) are tested in
 * `$lib/lq-ai/admin/__tests__/page-helpers.test.ts` (review fix 4).
 */
import { describe, expect, it } from 'vitest';

import type { DeploymentCapabilitySection } from '$lib/lq-ai/api/admin';
import type { ModelListResponse } from '$lib/lq-ai/api/models';
import {
	aliasMenuRows,
	applyOptimisticToggle,
	entryId,
	sectionSummary,
	tierLabel,
	togglePayload
} from '../page-helpers';

function section(
	entries: DeploymentCapabilitySection['entries'] = []
): DeploymentCapabilitySection {
	return { kind: 'tool', label: 'Tools', entries };
}

function entry(over: Partial<DeploymentCapabilitySection['entries'][number]> = {}) {
	return {
		capability_kind: 'tool' as const,
		capability_key: 'redlining',
		label: 'Redlining',
		description: null,
		enabled: true,
		...over
	};
}

describe('entryId', () => {
	it('joins kind and key', () => {
		expect(entryId('tool', 'redlining')).toBe('tool:redlining');
		expect(entryId('skill', 'contract-qa')).toBe('skill:contract-qa');
	});
});

describe('sectionSummary', () => {
	it('is empty for an empty section', () => {
		expect(sectionSummary(section([]))).toBe('');
	});

	it('counts enabled vs. total', () => {
		expect(
			sectionSummary(
				section([entry({ enabled: true }), entry({ enabled: false, capability_key: 'tabular' })])
			)
		).toBe('1 of 2 on');
	});

	it('reports fully-on', () => {
		expect(sectionSummary(section([entry({ enabled: true })]))).toBe('1 of 1 on');
	});
});

describe('togglePayload (D9 — one element only)', () => {
	it('builds a single-entry toggle body', () => {
		expect(togglePayload('tool', 'redlining', false)).toEqual([
			{ kind: 'tool', key: 'redlining', enabled: false }
		]);
	});
});

describe('applyOptimisticToggle', () => {
	it('flips only the matching (kind, key) entry, leaving others untouched', () => {
		const sections = [
			section([
				entry({ capability_key: 'redlining', enabled: true }),
				entry({ capability_key: 'tabular', enabled: true })
			])
		];
		const next = applyOptimisticToggle(sections, 'tool', 'redlining', false);
		expect(next[0].entries[0].enabled).toBe(false);
		expect(next[0].entries[1].enabled).toBe(true);
		// Original is untouched (pure — new arrays throughout).
		expect(sections[0].entries[0].enabled).toBe(true);
	});

	it('does not cross kinds with the same key', () => {
		const sections = [
			section([entry({ capability_kind: 'tool', capability_key: 'shared', enabled: true })]),
			{
				kind: 'skill' as const,
				label: 'Skills',
				entries: [entry({ capability_kind: 'skill', capability_key: 'shared', enabled: true })]
			}
		];
		const next = applyOptimisticToggle(sections, 'tool', 'shared', false);
		expect(next[0].entries[0].enabled).toBe(false);
		expect(next[1].entries[0].enabled).toBe(true);
	});

	it('per-entry revert leaves an interleaved toggle intact (review fix 2)', () => {
		// A flips off, B flips off while A is in flight, then A's PATCH fails and
		// is reverted PER-ENTRY (apply A's inverse) — B's change must survive.
		// The old full-snapshot restore wiped B; this pins the fixed behavior.
		const s0 = [
			section([
				entry({ capability_key: 'a', enabled: true }),
				entry({ capability_key: 'b', enabled: true })
			])
		];
		const afterA = applyOptimisticToggle(s0, 'tool', 'a', false);
		const afterB = applyOptimisticToggle(afterA, 'tool', 'b', false);
		const afterRevertA = applyOptimisticToggle(afterB, 'tool', 'a', true); // !next of A
		expect(afterRevertA[0].entries[0].enabled).toBe(true); // A reverted
		expect(afterRevertA[0].entries[1].enabled).toBe(false); // B intact
	});
});

describe('aliasMenuRows (review fix 3 — derived from GET /api/v1/models)', () => {
	// Representative merged-discovery payload shape (shape-only values, no real
	// providers/models): one tiered alias, one tier-less alias, one native row.
	const payload: ModelListResponse = {
		object: 'list',
		data: [
			{
				id: 'alias-one',
				object: 'model',
				created: 0,
				owned_by: 'lq-ai-gateway',
				lq_ai_kind: 'alias',
				routed_inference_tier: 4,
				lq_ai_resolves_to: 'provider-x/model-x',
				lq_ai_fallback_count: 1
			},
			{
				id: 'alias-two',
				object: 'model',
				created: 0,
				owned_by: 'lq-ai-gateway',
				lq_ai_kind: 'alias'
				// no routed_inference_tier — the fallback-only alias case
			},
			{
				id: 'provider-x/model-x',
				object: 'model',
				created: 0,
				owned_by: 'provider-x',
				lq_ai_kind: 'provider_native',
				routed_inference_tier: 4,
				provider_type: 'type-x'
			}
		]
	};

	it('keeps alias rows only, mapping id→alias and tier (null when unset)', () => {
		expect(aliasMenuRows(payload)).toEqual([
			{ alias: 'alias-one', tier: 4 },
			{ alias: 'alias-two', tier: null }
		]);
	});

	it('returns [] for an empty payload', () => {
		expect(aliasMenuRows({ object: 'list', data: [] })).toEqual([]);
	});
});

describe('tierLabel', () => {
	it('formats a resolved tier', () => {
		expect(tierLabel(4)).toBe('Tier 4');
		expect(tierLabel(1)).toBe('Tier 1');
	});

	it('renders an em-dash for a null tier', () => {
		expect(tierLabel(null)).toBe('—');
	});
});

