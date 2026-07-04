/**
 * Pure-helper tests for the /lq-ai/admin/capabilities page (SETUP-4b).
 */
import { describe, expect, it } from 'vitest';

import { LQAIApiError } from '$lib/lq-ai/api/client';
import type { DeploymentCapabilitySection } from '$lib/lq-ai/api/admin';
import {
	applyOptimisticToggle,
	describeMutationError,
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

describe('describeMutationError', () => {
	it('surfaces the server message verbatim', () => {
		const err = new LQAIApiError(422, 'validation_error', "Tool group 'nope' is not in the registry.");
		expect(describeMutationError(err, 'fallback')).toBe(
			"Tool group 'nope' is not in the registry."
		);
	});

	it('falls back for non-Error throws', () => {
		expect(describeMutationError('boom', 'fallback')).toBe('fallback');
	});
});
