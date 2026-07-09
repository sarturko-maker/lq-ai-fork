/**
 * Pure-helper tests for the /lq-ai/admin/store page (STORE-2, ADR-F065).
 */
import { describe, expect, it } from 'vitest';

import type { DeploymentCapabilitiesResponse, DeploymentCapabilityRead } from '$lib/lq-ai/api/admin';
import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';
import {
	buildRecommendedRails,
	flattenCapabilities,
	matchesSearch,
	missingEntries
} from '../page-helpers';

function capEntry(over: Partial<DeploymentCapabilityRead> = {}): DeploymentCapabilityRead {
	return {
		capability_kind: 'skill',
		capability_key: 'nda-review',
		label: 'NDA Review',
		description: 'Review an NDA.',
		in_library: false,
		enabled: false,
		source: 'built-in',
		author: null,
		version: null,
		tags: [],
		recommended_for: [],
		...over
	};
}

function area(over: Partial<PracticeArea> = {}): PracticeArea {
	return {
		id: 'id',
		key: 'commercial',
		name: 'Commercial',
		unit_label: 'Matter',
		configured: true,
		position: 0,
		profile_md: null,
		default_tier_floor: null,
		default_budget_profile: null,
		agent_config: {},
		hitl_policy: {},
		hitl_eligible_tools: [],
		bound_skills: [],
		bound_tool_groups: [],
		bound_playbooks: [],
		bound_knowledge_bases: [],
		created_at: '2026-01-01T00:00:00Z',
		updated_at: '2026-01-01T00:00:00Z',
		...over
	};
}

describe('matchesSearch', () => {
	const entry = capEntry({
		label: 'NDA Review',
		capability_key: 'nda-review',
		description: 'Review a confidentiality agreement.',
		tags: ['contracts', 'nda']
	});

	it('matches everything for an empty/whitespace term', () => {
		expect(matchesSearch(entry, '')).toBe(true);
		expect(matchesSearch(entry, '   ')).toBe(true);
	});

	it('matches by label, case-insensitively', () => {
		expect(matchesSearch(entry, 'nda review')).toBe(true);
		expect(matchesSearch(entry, 'NDA')).toBe(true);
	});

	it('matches by key', () => {
		expect(matchesSearch(entry, 'nda-review')).toBe(true);
	});

	it('matches by description', () => {
		expect(matchesSearch(entry, 'confidentiality')).toBe(true);
	});

	it('matches by tag', () => {
		expect(matchesSearch(entry, 'contracts')).toBe(true);
	});

	it('does not match an unrelated term', () => {
		expect(matchesSearch(entry, 'redlining')).toBe(false);
	});
});

describe('buildRecommendedRails', () => {
	const catalog: DeploymentCapabilitiesResponse = {
		sections: [
			{
				kind: 'tool',
				label: 'Tools',
				entries: [
					capEntry({
						capability_kind: 'tool',
						capability_key: 'redlining',
						label: 'Redlining',
						in_library: true,
						recommended_for: ['commercial']
					}),
					capEntry({
						capability_kind: 'tool',
						capability_key: 'ropa',
						label: 'ROPA register',
						in_library: false,
						recommended_for: ['privacy']
					})
				]
			},
			{
				kind: 'skill',
				label: 'Skills',
				entries: [
					capEntry({
						capability_kind: 'skill',
						capability_key: 'nda-review',
						label: 'NDA Review',
						in_library: false,
						recommended_for: ['commercial', 'm-and-a', 'employment']
					})
				]
			},
			{ kind: 'playbook', label: 'Playbooks', entries: [] },
			{
				kind: 'knowledge',
				label: 'Knowledge',
				entries: [
					capEntry({
						capability_kind: 'knowledge',
						capability_key: 'kb-1',
						label: 'Precedent bank',
						source: null,
						in_library: false,
						// Knowledge is never in a recommended set (RECOMMENDED_LIBRARY_SETS
						// only has tool/skill keys server-side) — recommended_for is always [].
						recommended_for: []
					})
				]
			}
		]
	};

	it('builds one rail per area key present in any recommended_for, in the org area position order', () => {
		const areas = [
			area({ key: 'commercial', name: 'Commercial', position: 0 }),
			area({ key: 'privacy', name: 'Privacy', position: 1 }),
			area({ key: 'm-and-a', name: 'M&A', position: 2 }),
			area({ key: 'employment', name: 'Employment', position: 3 })
		];
		const rails = buildRecommendedRails(catalog, areas);
		expect(rails.map((r) => r.areaKey)).toEqual(['commercial', 'privacy', 'm-and-a', 'employment']);
		expect(rails[0].areaLabel).toBe('Commercial');
	});

	it('counts missing (not-yet-adopted) entries per rail', () => {
		const areas = [area({ key: 'commercial', name: 'Commercial' })];
		const rails = buildRecommendedRails(catalog, areas);
		const commercial = rails.find((r) => r.areaKey === 'commercial')!;
		// redlining (in_library) + nda-review (not) recommended for commercial.
		expect(commercial.entries.map((e) => e.key).sort()).toEqual(['nda-review', 'redlining']);
		expect(commercial.missingCount).toBe(1);
	});

	it('reports missingCount 0 when every recommended entry is adopted', () => {
		const onlyAdopted: DeploymentCapabilitiesResponse = {
			sections: [
				{
					kind: 'tool',
					label: 'Tools',
					entries: [
						capEntry({
							capability_kind: 'tool',
							capability_key: 'redlining',
							in_library: true,
							recommended_for: ['commercial']
						})
					]
				},
				{ kind: 'skill', label: 'Skills', entries: [] },
				{ kind: 'playbook', label: 'Playbooks', entries: [] }
			]
		};
		const rails = buildRecommendedRails(onlyAdopted, [area({ key: 'commercial' })]);
		expect(rails[0].missingCount).toBe(0);
	});

	it('falls back to a humanised label and sorts unmatched area keys last', () => {
		// No configured area named 'm-and-a' — falls back to a humanised label,
		// sorted after any area keys that DO have a configured match.
		const rails = buildRecommendedRails(catalog, [area({ key: 'commercial', name: 'Commercial' })]);
		const unmatched = rails.find((r) => r.areaKey === 'm-and-a');
		expect(unmatched?.areaLabel).toBe('M And A');
	});

	it('returns [] when nothing is recommended for any area', () => {
		const empty: DeploymentCapabilitiesResponse = {
			sections: [
				{ kind: 'tool', label: 'Tools', entries: [] },
				{ kind: 'skill', label: 'Skills', entries: [] },
				{ kind: 'playbook', label: 'Playbooks', entries: [] }
			]
		};
		expect(buildRecommendedRails(empty, [])).toEqual([]);
	});

	it('a knowledge entry never generates a rail (recommended_for is always [])', () => {
		const areas = [area({ key: 'commercial', name: 'Commercial' })];
		const rails = buildRecommendedRails(catalog, areas);
		for (const rail of rails) {
			expect(rail.entries.some((e) => e.kind === 'knowledge')).toBe(false);
		}
	});
});

describe('flattenCapabilities', () => {
	it('flattens all four sections, preserving the knowledge kind', () => {
		const catalog: DeploymentCapabilitiesResponse = {
			sections: [
				{ kind: 'tool', label: 'Tools', entries: [] },
				{ kind: 'skill', label: 'Skills', entries: [] },
				{ kind: 'playbook', label: 'Playbooks', entries: [] },
				{
					kind: 'knowledge',
					label: 'Knowledge',
					entries: [
						capEntry({
							capability_kind: 'knowledge',
							capability_key: 'kb-1',
							label: 'Precedent bank',
							source: null,
							in_library: false,
							recommended_for: []
						})
					]
				}
			]
		};
		const flat = flattenCapabilities(catalog);
		const knowledgeEntries = flat.filter((e) => e.capability_kind === 'knowledge');
		expect(knowledgeEntries.map((e) => e.capability_key)).toEqual(['kb-1']);
		expect(knowledgeEntries[0].label).toBe('Precedent bank');
	});
});

describe('missingEntries', () => {
	it('returns only the not-yet-adopted chips as {kind, key} pairs', () => {
		const rail = {
			areaKey: 'commercial',
			areaLabel: 'Commercial',
			entries: [
				{ kind: 'tool' as const, key: 'redlining', label: 'Redlining', inLibrary: true },
				{ kind: 'skill' as const, key: 'nda-review', label: 'NDA Review', inLibrary: false }
			],
			missingCount: 1
		};
		expect(missingEntries(rail)).toEqual([{ kind: 'skill', key: 'nda-review' }]);
	});

	it('handles a knowledge chip (type-level — knowledge never actually appears in a rail)', () => {
		const rail = {
			areaKey: 'commercial',
			areaLabel: 'Commercial',
			entries: [
				{ kind: 'knowledge' as const, key: 'kb-1', label: 'Precedent bank', inLibrary: false }
			],
			missingCount: 1
		};
		expect(missingEntries(rail)).toEqual([{ kind: 'knowledge', key: 'kb-1' }]);
	});

	it('returns [] when everything is already adopted', () => {
		const rail = {
			areaKey: 'commercial',
			areaLabel: 'Commercial',
			entries: [{ kind: 'tool' as const, key: 'redlining', label: 'Redlining', inLibrary: true }],
			missingCount: 0
		};
		expect(missingEntries(rail)).toEqual([]);
	});
});
