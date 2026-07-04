/**
 * Pure-helper tests for the /lq-ai/admin/areas list+create page (SETUP-4b).
 */
import { describe, expect, it } from 'vitest';

import { LQAIApiError } from '$lib/lq-ai/api/client';
import type { DeploymentCapabilitiesResponse } from '$lib/lq-ai/api/admin';
import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';
import {
	areaStatusView,
	availableGroupOptions,
	boundCountsLabel,
	catalogEntriesForKind,
	describeMutationError,
	moveKey,
	validateAreaKey
} from '../page-helpers';

function area(over: Partial<PracticeArea> = {}): PracticeArea {
	return {
		id: '00000000-0000-0000-0000-000000000001',
		key: 'commercial',
		name: 'Commercial',
		unit_label: 'Matter',
		configured: true,
		position: 0,
		profile_md: '# Commercial',
		default_tier_floor: null,
		agent_config: {},
		bound_skills: [],
		bound_tool_groups: [],
		bound_playbooks: [],
		created_at: '2026-01-01T00:00:00Z',
		updated_at: '2026-01-01T00:00:00Z',
		...over
	};
}

describe('validateAreaKey', () => {
	it('requires a non-empty value', () => {
		expect(validateAreaKey('')).toMatch(/required/i);
		expect(validateAreaKey('   ')).toMatch(/required/i);
	});

	it('rejects keys shorter than 3 characters', () => {
		expect(validateAreaKey('ab')).toMatch(/lowercase/i);
	});

	it('rejects leading/trailing hyphen and uppercase', () => {
		expect(validateAreaKey('-bad-')).toMatch(/lowercase/i);
		expect(validateAreaKey('Bad')).toMatch(/lowercase/i);
		expect(validateAreaKey('bad-')).toMatch(/lowercase/i);
	});

	it('accepts a plausible slug', () => {
		expect(validateAreaKey('litigation')).toBeNull();
		expect(validateAreaKey('m-and-a')).toBeNull();
		expect(validateAreaKey('abc')).toBeNull();
	});
});

describe('moveKey', () => {
	const keys = ['a', 'b', 'c', 'd'];

	it('swaps with the previous key on up', () => {
		expect(moveKey(keys, 'c', 'up')).toEqual(['a', 'c', 'b', 'd']);
	});

	it('swaps with the next key on down', () => {
		expect(moveKey(keys, 'b', 'down')).toEqual(['a', 'c', 'b', 'd']);
	});

	it('is a no-op (same reference) at the top edge', () => {
		expect(moveKey(keys, 'a', 'up')).toBe(keys);
	});

	it('is a no-op (same reference) at the bottom edge', () => {
		expect(moveKey(keys, 'd', 'down')).toBe(keys);
	});

	it('is a no-op (same reference) for an unknown key', () => {
		expect(moveKey(keys, 'zzz', 'up')).toBe(keys);
	});
});

describe('boundCountsLabel', () => {
	it('pluralizes each count independently', () => {
		expect(
			boundCountsLabel({ bound_skills: [], bound_playbooks: [], bound_tool_groups: [] })
		).toBe('0 skills · 0 playbooks · 0 groups');
		expect(
			boundCountsLabel({
				bound_skills: ['a'],
				bound_playbooks: [{ id: '1', name: 'x' }],
				bound_tool_groups: ['redlining', 'tabular']
			})
		).toBe('1 skill · 1 playbook · 2 groups');
	});
});

describe('areaStatusView (D5)', () => {
	it('labels a configured area Active with no hint', () => {
		expect(areaStatusView({ configured: true })).toEqual({ label: 'Active', tone: 'secondary' });
	});

	it('labels an unconfigured area with the activation hint', () => {
		expect(areaStatusView({ configured: false })).toEqual({
			label: 'Not configured',
			tone: 'outline',
			title: 'Add doctrine to activate'
		});
	});
});

describe('describeMutationError', () => {
	it('surfaces the server message verbatim', () => {
		const err = new LQAIApiError(409, 'conflict', 'A practice area with this key already exists.');
		expect(describeMutationError(err, 'fallback')).toBe(
			'A practice area with this key already exists.'
		);
	});

	it('falls back for non-Error throws', () => {
		expect(describeMutationError('boom', 'fallback')).toBe('fallback');
		expect(describeMutationError(new Error('net down'), 'fallback')).toBe('net down');
	});
});

describe('catalogEntriesForKind / availableGroupOptions (D7)', () => {
	const catalog: DeploymentCapabilitiesResponse = {
		sections: [
			{
				kind: 'tool',
				label: 'Tools',
				entries: [
					{ capability_kind: 'tool', capability_key: 'redlining', label: 'Redlining', description: 'd1', enabled: true },
					{ capability_kind: 'tool', capability_key: 'tabular', label: 'Grids', description: null, enabled: true }
				]
			},
			{ kind: 'skill', label: 'Skills', entries: [] },
			{ kind: 'playbook', label: 'Playbooks', entries: [] }
		]
	};

	it('returns [] for a null catalog', () => {
		expect(catalogEntriesForKind(null, 'tool')).toEqual([]);
		expect(availableGroupOptions(null)).toEqual([]);
	});

	it('projects a section to {key, label, description}', () => {
		expect(availableGroupOptions(catalog)).toEqual([
			{ key: 'redlining', label: 'Redlining', description: 'd1' },
			{ key: 'tabular', label: 'Grids', description: null }
		]);
	});

	it('returns [] for a kind with no section', () => {
		const noPlaybooks: DeploymentCapabilitiesResponse = {
			sections: catalog.sections.filter((s) => s.kind !== 'playbook')
		};
		expect(catalogEntriesForKind(noPlaybooks, 'playbook')).toEqual([]);
	});
});
