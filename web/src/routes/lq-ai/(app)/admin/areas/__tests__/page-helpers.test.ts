/**
 * Pure-helper tests for the /lq-ai/admin/areas list+create page (SETUP-4b).
 * Shared helpers (describeMutationError, catalogEntriesForKind) are tested in
 * `$lib/lq-ai/admin/__tests__/page-helpers.test.ts` (review fix 4).
 */
import { describe, expect, it } from 'vitest';

import type { DeploymentCapabilitiesResponse } from '$lib/lq-ai/api/admin';
import {
	areaStatusView,
	availableGroupOptions,
	boundCountsLabel,
	moveKey,
	validateAreaKey
} from '../page-helpers';

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

describe('availableGroupOptions (D7)', () => {
	const catalog: DeploymentCapabilitiesResponse = {
		sections: [
			{
				kind: 'tool',
				label: 'Tools',
				entries: [
					{
						capability_kind: 'tool',
						capability_key: 'redlining',
						label: 'Redlining',
						description: 'd1',
						in_library: true,
						enabled: true
					},
					{
						capability_kind: 'tool',
						capability_key: 'tabular',
						label: 'Grids',
						description: null,
						in_library: true,
						enabled: true
					}
				]
			},
			{ kind: 'skill', label: 'Skills', entries: [] },
			{ kind: 'playbook', label: 'Playbooks', entries: [] }
		]
	};

	it('returns [] for a null catalog', () => {
		expect(availableGroupOptions(null)).toEqual([]);
	});

	it('offers every registry tool group for a brand-new area', () => {
		expect(availableGroupOptions(catalog)).toEqual([
			{ key: 'redlining', label: 'Redlining', description: 'd1', in_library: true },
			{ key: 'tabular', label: 'Grids', description: null, in_library: true }
		]);
	});
});
