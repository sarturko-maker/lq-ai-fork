/**
 * Pure-helper tests for the /lq-ai/admin/areas/[key] detail page (SETUP-4b).
 * Shared helpers (describeMutationError, catalogEntriesForKind) are tested in
 * `$lib/lq-ai/admin/__tests__/page-helpers.test.ts` (review fix 4).
 */
import { describe, expect, it } from 'vitest';

import { LQAIApiError } from '$lib/lq-ai/api/client';
import type { DeploymentCapabilitiesResponse } from '$lib/lq-ai/api/admin';
import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';
import {
	addSubagent,
	agentConfigToRoster,
	bindingLabel,
	degradedBindingKeys,
	diffPatch,
	emptySubagent,
	findAreaByKey,
	formatDeleteConflict,
	hasMultipleLedgerBearingGroups,
	hitlEnabledTools,
	hitlPolicyDirty,
	orgSkillBadges,
	pickerEmptyState,
	removeSubagent,
	rosterDirty,
	rosterErrors,
	rosterToAgentConfig,
	serializeSubagents,
	subagentSkillRows,
	toggleSubagentSkill,
	unboundOptions,
	updateSubagent,
	type SubagentDraft
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

describe('findAreaByKey', () => {
	const areas = [area({ key: 'commercial' }), area({ key: 'privacy', name: 'Privacy' })];

	it('finds the matching area', () => {
		expect(findAreaByKey(areas, 'privacy')?.name).toBe('Privacy');
	});

	it('returns undefined for an unknown key', () => {
		expect(findAreaByKey(areas, 'no-such-area')).toBeUndefined();
	});
});

describe('diffPatch', () => {
	const original = area({
		name: 'Commercial',
		unit_label: 'Matter',
		profile_md: '# doctrine',
		default_tier_floor: 2
	});

	it('is empty when the draft matches the original', () => {
		expect(
			diffPatch(original, {
				name: 'Commercial',
				unit_label: 'Matter',
				profile_md: '# doctrine',
				default_tier_floor: '2',
				default_budget_profile: ''
			})
		).toEqual({});
	});

	it('includes only the changed fields', () => {
		expect(
			diffPatch(original, {
				name: 'Commercial Contracts',
				unit_label: 'Matter',
				profile_md: '# doctrine',
				default_tier_floor: '2',
				default_budget_profile: ''
			})
		).toEqual({ name: 'Commercial Contracts' });
	});

	it('trims name/unit_label before comparing', () => {
		expect(
			diffPatch(original, {
				name: '  Commercial  ',
				unit_label: ' Matter ',
				profile_md: '# doctrine',
				default_tier_floor: '2',
				default_budget_profile: ''
			})
		).toEqual({});
	});

	it('normalizes an emptied doctrine textarea to null', () => {
		expect(
			diffPatch(original, {
				name: 'Commercial',
				unit_label: 'Matter',
				profile_md: '   ',
				default_tier_floor: '2',
				default_budget_profile: ''
			})
		).toEqual({ profile_md: null });
	});

	it('normalizes an emptied tier-floor select to null', () => {
		expect(
			diffPatch(original, {
				name: 'Commercial',
				unit_label: 'Matter',
				profile_md: '# doctrine',
				default_tier_floor: '',
				default_budget_profile: ''
			})
		).toEqual({ default_tier_floor: null });
	});

	it('parses a numeric tier-floor string', () => {
		expect(
			diffPatch(original, {
				name: 'Commercial',
				unit_label: 'Matter',
				profile_md: '# doctrine',
				default_tier_floor: '4',
				default_budget_profile: ''
			})
		).toEqual({ default_tier_floor: 4 });
	});

	it('treats a null original profile_md and an empty draft as unchanged', () => {
		const noProfile = area({ profile_md: null });
		expect(
			diffPatch(noProfile, {
				name: noProfile.name,
				unit_label: noProfile.unit_label,
				profile_md: '',
				default_tier_floor: '',
				default_budget_profile: ''
			})
		).toEqual({});
	});

	// SETUP-5a (ADR-F063): explicit-null-clears semantics — "Inherit" sends
	// null ONLY when the field was actually changed; unchanged = omitted.
	it('includes a newly picked budget profile', () => {
		expect(
			diffPatch(original, {
				name: 'Commercial',
				unit_label: 'Matter',
				profile_md: '# doctrine',
				default_tier_floor: '2',
				default_budget_profile: 'economy'
			})
		).toEqual({ default_budget_profile: 'economy' });
	});

	it('sends an explicit null when changed back to Inherit', () => {
		const withDefault = area({ default_budget_profile: 'economy', default_tier_floor: 2 });
		expect(
			diffPatch(withDefault, {
				name: withDefault.name,
				unit_label: withDefault.unit_label,
				profile_md: withDefault.profile_md ?? '',
				default_tier_floor: '2',
				default_budget_profile: ''
			})
		).toEqual({ default_budget_profile: null });
	});

	it('omits an unchanged budget profile entirely', () => {
		const withDefault = area({ default_budget_profile: 'generous', default_tier_floor: 2 });
		expect(
			diffPatch(withDefault, {
				name: withDefault.name,
				unit_label: withDefault.unit_label,
				profile_md: withDefault.profile_md ?? '',
				default_tier_floor: '2',
				default_budget_profile: 'generous'
			})
		).toEqual({});
	});
});

describe('agentConfigToRoster (B-5)', () => {
	it('parses subagent rows, KEEPING system_prompt (unlike the cockpit projection)', () => {
		expect(
			agentConfigToRoster({
				subagents: [
					{
						name: 'clause-drafter',
						description: 'Draft one clause.',
						system_prompt: 'You are a drafter.',
						skills: ['surgical-redline']
					}
				]
			})
		).toEqual([
			{
				name: 'clause-drafter',
				description: 'Draft one clause.',
				system_prompt: 'You are a drafter.',
				skills: ['surgical-redline']
			}
		]);
	});

	it('returns [] for an empty/missing/odd-shaped config', () => {
		expect(agentConfigToRoster({})).toEqual([]);
		expect(agentConfigToRoster(null)).toEqual([]);
		expect(agentConfigToRoster(undefined)).toEqual([]);
		expect(agentConfigToRoster({ subagents: 'nope' })).toEqual([]);
	});

	it('defaults missing string fields to empty and filters non-string skills', () => {
		expect(agentConfigToRoster({ subagents: [{ name: 'x' }] })).toEqual([
			{ name: 'x', description: '', system_prompt: '', skills: [] }
		]);
		expect(
			agentConfigToRoster({ subagents: [{ name: 'y', skills: ['a', 2, null, 'b'] }] })[0].skills
		).toEqual(['a', 'b']);
	});

	it('skips non-object entries but keeps a malformed object row for repair', () => {
		expect(agentConfigToRoster({ subagents: ['str', 42, null, { description: 'no name' }] })).toEqual([
			{ name: '', description: 'no name', system_prompt: '', skills: [] }
		]);
	});
});

describe('serializeSubagents (B-5)', () => {
	it('trims the required fields and OMITS empty skills', () => {
		expect(
			serializeSubagents([{ name: '  drafter  ', description: ' d ', system_prompt: ' p ', skills: [] }])
		).toEqual([{ name: 'drafter', description: 'd', system_prompt: 'p' }]);
	});

	it('includes skills when present', () => {
		expect(
			serializeSubagents([{ name: 'r', description: 'd', system_prompt: 'p', skills: ['nda-review'] }])
		).toEqual([{ name: 'r', description: 'd', system_prompt: 'p', skills: ['nda-review'] }]);
	});
});

describe('rosterToAgentConfig (B-5)', () => {
	it('splices the roster into a copy, PRESERVING by-reference passthrough keys', () => {
		const prev = {
			subagents: [{ name: 'old', description: 'o', system_prompt: 'o' }],
			playbooks: ['pb'],
			mcp_servers: [{ ref: 'x' }]
		};
		expect(
			rosterToAgentConfig([{ name: 'new', description: 'n', system_prompt: 'n', skills: [] }], prev)
		).toEqual({
			subagents: [{ name: 'new', description: 'n', system_prompt: 'n' }],
			playbooks: ['pb'],
			mcp_servers: [{ ref: 'x' }]
		});
	});

	it('drops the subagents key entirely when the roster is empty (keeps passthrough)', () => {
		expect(
			rosterToAgentConfig([], {
				subagents: [{ name: 'x', description: 'd', system_prompt: 'p' }],
				playbooks: ['pb']
			})
		).toEqual({ playbooks: ['pb'] });
	});

	it('does not mutate the previous config', () => {
		const prev = { subagents: [{ name: 'x', description: 'd', system_prompt: 'p' }] };
		rosterToAgentConfig([{ name: 'y', description: 'd', system_prompt: 'p', skills: [] }], prev);
		expect((prev.subagents[0] as { name: string }).name).toBe('x');
	});
});

describe('rosterDirty (B-5)', () => {
	const stored = {
		subagents: [
			{
				name: 'document-researcher',
				description: 'Investigate.',
				system_prompt: 'You are a researcher.',
				skills: ['contract-qa']
			}
		]
	};

	it('is false when the draft round-trips the stored roster unchanged', () => {
		expect(rosterDirty(stored, agentConfigToRoster(stored))).toBe(false);
	});

	it('is false for a whitespace-only edit (normalized away)', () => {
		const draft = agentConfigToRoster(stored);
		draft[0] = { ...draft[0], description: '  Investigate.  ' };
		expect(rosterDirty(stored, draft)).toBe(false);
	});

	it('is true when a field actually changes', () => {
		const draft = agentConfigToRoster(stored);
		draft[0] = { ...draft[0], system_prompt: 'You are a SENIOR researcher.' };
		expect(rosterDirty(stored, draft)).toBe(true);
	});

	it('is true when a sub-agent is added or removed', () => {
		expect(rosterDirty(stored, [])).toBe(true);
		expect(rosterDirty(stored, addSubagent(agentConfigToRoster(stored)))).toBe(true);
	});

	it('ignores passthrough keys (the form does not own them)', () => {
		const withPassthrough = { ...stored, playbooks: ['pb'] };
		expect(rosterDirty(withPassthrough, agentConfigToRoster(withPassthrough))).toBe(false);
	});
});

describe('rosterErrors (B-5)', () => {
	const bound = ['contract-qa', 'nda-review'];

	it('is empty for a valid roster', () => {
		expect(
			rosterErrors(
				[
					{
						name: 'drafter',
						description: 'Draft.',
						system_prompt: 'Do the thing.',
						skills: ['nda-review']
					}
				],
				bound
			)
		).toEqual([]);
	});

	it('flags each missing required field, labelled by position when unnamed', () => {
		const errs = rosterErrors([{ name: '', description: '', system_prompt: '', skills: [] }], bound);
		expect(errs).toContain('Sub-agent 1: a name is required.');
		expect(errs).toContain('Sub-agent 1: a description is required.');
		expect(errs).toContain('Sub-agent 1: instructions are required.');
	});

	it('uses the name in the label when present', () => {
		expect(
			rosterErrors([{ name: 'drafter', description: '', system_prompt: 'p', skills: [] }], bound)
		).toEqual(['drafter: a description is required.']);
	});

	it('rejects a skill not bound to the area (ADR-F017)', () => {
		expect(
			rosterErrors(
				[{ name: 'r', description: 'd', system_prompt: 'p', skills: ['contract-qa', 'ghost-skill'] }],
				bound
			)
		).toEqual(['r: skill(s) not bound to this area — ghost-skill.']);
	});

	it('flags duplicate sub-agent names (client-only unique gate)', () => {
		expect(
			rosterErrors(
				[
					{ name: 'dup', description: 'd', system_prompt: 'p', skills: [] },
					{ name: 'dup', description: 'd', system_prompt: 'p', skills: [] }
				],
				bound
			)
		).toContain('Sub-agent names must be unique — "dup" is used 2 times.');
	});

	it('counts trim-colliding names as duplicates (matches the on-wire trim)', () => {
		expect(
			rosterErrors(
				[
					{ name: 'dup', description: 'd', system_prompt: 'p', skills: [] },
					{ name: '  dup  ', description: 'd', system_prompt: 'p', skills: [] }
				],
				bound
			)
		).toContain('Sub-agent names must be unique — "dup" is used 2 times.');
	});

	it('treats a whitespace-only name as missing (trimmed before the required check)', () => {
		expect(
			rosterErrors([{ name: '   ', description: 'd', system_prompt: 'p', skills: [] }], bound)
		).toEqual(['Sub-agent 1: a name is required.']);
	});
});

describe('subagentSkillRows (B-5)', () => {
	it('lists the area bound skills (in order), all marked bound', () => {
		expect(subagentSkillRows(['contract-qa', 'nda-review'], [])).toEqual([
			{ name: 'contract-qa', bound: true },
			{ name: 'nda-review', bound: true }
		]);
	});

	it('appends an orphaned sub-agent skill (no longer bound) so it can be un-checked', () => {
		expect(subagentSkillRows(['contract-qa'], ['contract-qa', 'nda-review'])).toEqual([
			{ name: 'contract-qa', bound: true },
			{ name: 'nda-review', bound: false }
		]);
	});

	it('does not duplicate a skill that is both bound and on the sub-agent', () => {
		expect(subagentSkillRows(['contract-qa'], ['contract-qa'])).toEqual([
			{ name: 'contract-qa', bound: true }
		]);
	});

	it('is empty when the area has no bound skills and the sub-agent has none', () => {
		expect(subagentSkillRows([], [])).toEqual([]);
	});
});

describe('roster transforms (B-5)', () => {
	const base: SubagentDraft[] = [{ name: 'a', description: 'da', system_prompt: 'pa', skills: [] }];

	it('emptySubagent is blank', () => {
		expect(emptySubagent()).toEqual({ name: '', description: '', system_prompt: '', skills: [] });
	});

	it('addSubagent appends a blank row without mutating the input', () => {
		const next = addSubagent(base);
		expect(next).toHaveLength(2);
		expect(next[1]).toEqual(emptySubagent());
		expect(base).toHaveLength(1);
	});

	it('removeSubagent drops the indexed row immutably', () => {
		const two = addSubagent(base);
		expect(removeSubagent(two, 0)).toEqual([emptySubagent()]);
		expect(two).toHaveLength(2);
	});

	it('updateSubagent patches one row immutably', () => {
		const next = updateSubagent(base, 0, { name: 'renamed' });
		expect(next[0].name).toBe('renamed');
		expect(next[0].description).toBe('da');
		expect(base[0].name).toBe('a');
	});

	it('toggleSubagentSkill adds then removes a skill immutably', () => {
		const added = toggleSubagentSkill(base, 0, 'nda-review', true);
		expect(added[0].skills).toEqual(['nda-review']);
		expect(toggleSubagentSkill(added, 0, 'nda-review', false)[0].skills).toEqual([]);
		expect(base[0].skills).toEqual([]);
	});

	it('toggleSubagentSkill is idempotent (no dup re-add, no-op absent remove)', () => {
		const added = toggleSubagentSkill(base, 0, 'x', true);
		expect(toggleSubagentSkill(added, 0, 'x', true)[0].skills).toEqual(['x']);
		expect(toggleSubagentSkill(base, 0, 'x', false)[0].skills).toEqual([]);
	});
});

describe('bindingLabel', () => {
	const options = [
		{ key: 'nda-review', label: 'NDA review', description: null, in_library: true },
		{ key: 'contract-qa', label: 'Contract Q&A', description: null, in_library: true }
	];

	it('resolves a known key to its catalog label', () => {
		expect(bindingLabel(options, 'nda-review')).toBe('NDA review');
	});

	it('falls back to the raw key for a drifted/unknown entry', () => {
		expect(bindingLabel(options, 'retired-skill')).toBe('retired-skill');
	});
});

describe('unboundOptions', () => {
	const options = [
		{ key: 'redlining', label: 'Redlining', description: null, in_library: true },
		{ key: 'tabular', label: 'Grids', description: null, in_library: true },
		{ key: 'ropa', label: 'ROPA register', description: null, in_library: true }
	];

	it('excludes already-bound entries', () => {
		expect(unboundOptions(options, ['redlining'])).toEqual([
			{ key: 'tabular', label: 'Grids', description: null, in_library: true },
			{ key: 'ropa', label: 'ROPA register', description: null, in_library: true }
		]);
	});

	it('returns every entry when nothing is bound', () => {
		expect(unboundOptions(options, [])).toEqual(options);
	});

	it('returns [] when everything is bound', () => {
		expect(unboundOptions(options, ['redlining', 'tabular', 'ropa'])).toEqual([]);
	});

	it('works with knowledge-style UUID keys (B-3b) — the helper is generic', () => {
		const knowledgeOptions = [
			{
				key: '11111111-1111-1111-1111-111111111111',
				label: 'Precedent bank',
				description: null,
				in_library: true
			},
			{
				key: '22222222-2222-2222-2222-222222222222',
				label: 'Deal room',
				description: null,
				in_library: true
			}
		];
		expect(unboundOptions(knowledgeOptions, ['11111111-1111-1111-1111-111111111111'])).toEqual([
			{
				key: '22222222-2222-2222-2222-222222222222',
				label: 'Deal room',
				description: null,
				in_library: true
			}
		]);
	});
});

describe('degradedBindingKeys (G13(a))', () => {
	const catalog = [
		{ key: 'redlining', label: 'Redlining', description: null, in_library: true },
		{ key: 'nda-review', label: 'NDA review', description: null, in_library: false }
	];

	it('is not degraded when the bound key is Library-adopted', () => {
		expect(degradedBindingKeys(catalog, ['redlining'])).toEqual(new Set());
	});

	it('is degraded when the bound key has a catalog entry but is not adopted', () => {
		expect(degradedBindingKeys(catalog, ['nda-review'])).toEqual(new Set(['nda-review']));
	});

	it('is degraded when the bound key has NO catalog entry at all (registry drift)', () => {
		expect(degradedBindingKeys(catalog, ['retired-skill'])).toEqual(new Set(['retired-skill']));
	});

	it('mixes adopted and degraded keys correctly in one call', () => {
		expect(degradedBindingKeys(catalog, ['redlining', 'nda-review', 'retired-skill'])).toEqual(
			new Set(['nda-review', 'retired-skill'])
		);
	});

	it('isolates kinds — the same key string in a different kind catalog is judged independently', () => {
		// Same key 'shared-key' adopted in one kind's catalog, not in another's —
		// callers pass one kind's catalog at a time, so each call is self-contained.
		const toolCatalog = [{ key: 'shared-key', label: 'Tool', description: null, in_library: true }];
		const skillCatalog = [
			{ key: 'shared-key', label: 'Skill', description: null, in_library: false }
		];
		expect(degradedBindingKeys(toolCatalog, ['shared-key'])).toEqual(new Set());
		expect(degradedBindingKeys(skillCatalog, ['shared-key'])).toEqual(new Set(['shared-key']));
	});

	it('returns an empty set for empty inputs', () => {
		expect(degradedBindingKeys([], [])).toEqual(new Set());
		expect(degradedBindingKeys(catalog, [])).toEqual(new Set());
	});

	it('degrades every bound key when the catalog itself is empty', () => {
		expect(degradedBindingKeys([], ['redlining', 'nda-review'])).toEqual(
			new Set(['redlining', 'nda-review'])
		);
	});

	it('works with knowledge-style UUID keys (B-3b) — the helper is generic', () => {
		const kbCatalog = [
			{
				key: '11111111-1111-1111-1111-111111111111',
				label: 'Precedent bank',
				description: null,
				in_library: true
			}
		];
		expect(degradedBindingKeys(kbCatalog, ['11111111-1111-1111-1111-111111111111'])).toEqual(
			new Set()
		);
		expect(degradedBindingKeys(kbCatalog, ['22222222-2222-2222-2222-222222222222'])).toEqual(
			new Set(['22222222-2222-2222-2222-222222222222'])
		);
	});
});

describe('pickerEmptyState (STORE-2)', () => {
	const nonEmptyCatalog = [
		{ key: 'redlining', label: 'Redlining', description: null, in_library: true }
	];

	it('returns null when the picker has options', () => {
		expect(pickerEmptyState(nonEmptyCatalog, nonEmptyCatalog)).toBeNull();
	});

	it("returns 'library-empty' when the Library has no entries of this kind", () => {
		expect(pickerEmptyState([], [])).toBe('library-empty');
	});

	it("returns 'all-attached' when the Library has entries but none are unbound", () => {
		expect(pickerEmptyState(nonEmptyCatalog, [])).toBe('all-attached');
	});
});

describe('hasMultipleLedgerBearingGroups (D5)', () => {
	it('is false with zero or one ledger-bearing group', () => {
		expect(hasMultipleLedgerBearingGroups([])).toBe(false);
		expect(hasMultipleLedgerBearingGroups(['tabular'])).toBe(false);
		expect(hasMultipleLedgerBearingGroups(['redlining', 'tabular'])).toBe(false);
	});

	it('is true with both redlining and ropa bound', () => {
		expect(hasMultipleLedgerBearingGroups(['redlining', 'ropa'])).toBe(true);
		expect(hasMultipleLedgerBearingGroups(['redlining', 'tabular', 'ropa'])).toBe(true);
	});
});

describe('hitlEnabledTools (HITL-3, ADR-F071)', () => {
	it('returns the true-valued keys, sorted', () => {
		expect(hitlEnabledTools({ b: true, a: true, c: false })).toEqual(['a', 'b']);
	});

	it('returns [] when nothing is enabled', () => {
		expect(hitlEnabledTools({})).toEqual([]);
		expect(hitlEnabledTools({ x: false, y: false })).toEqual([]);
	});
});

describe('hitlPolicyDirty (HITL-3, ADR-F071)', () => {
	it('is false when the enabled sets match', () => {
		expect(hitlPolicyDirty({ apply_redline: true }, { apply_redline: true })).toBe(false);
	});

	it('is true when the draft drops an enabled tool', () => {
		expect(hitlPolicyDirty({ apply_redline: true }, {})).toBe(true);
	});

	it('is true when the draft adds an enabled tool', () => {
		expect(
			hitlPolicyDirty({ apply_redline: true }, { apply_redline: true, preview_redline: true })
		).toBe(true);
	});

	it('ignores false-valued entries (not part of the enabled set)', () => {
		expect(hitlPolicyDirty({}, { x: false })).toBe(false);
	});
});

describe('orgSkillBadges (B-2b, decision 5)', () => {
	type SkillEntry = DeploymentCapabilitiesResponse['sections'][number]['entries'][number];

	function catalog(skillEntries: SkillEntry[]): DeploymentCapabilitiesResponse {
		return {
			sections: [
				{ kind: 'tool', label: 'Tools', entries: [] },
				{ kind: 'skill', label: 'Skills', entries: skillEntries },
				{ kind: 'playbook', label: 'Playbooks', entries: [] }
			]
		};
	}

	it('returns an empty map for a null catalog (still loading)', () => {
		expect(orgSkillBadges(null).size).toBe(0);
	});

	it('maps only source="org" skill entries, keyed by capability_key', () => {
		const cat = catalog([
			{
				capability_kind: 'skill',
				capability_key: 'org-nda',
				label: 'Org NDA',
				description: null,
				in_library: true,
				enabled: true,
				source: 'org',
				author: 'Jamie Tso',
				approver: 'Alex Admin'
			},
			{
				capability_kind: 'skill',
				capability_key: 'builtin-nda',
				label: 'Built-in NDA',
				description: null,
				in_library: true,
				enabled: true,
				source: 'built-in'
			}
		]);
		const map = orgSkillBadges(cat);
		expect(map.size).toBe(1);
		expect(map.get('org-nda')).toEqual({
			source: 'org',
			author: 'Jamie Tso',
			approver: 'Alex Admin'
		});
		expect(map.has('builtin-nda')).toBe(false);
	});

	it('defaults author/approver to null when the wire omits them', () => {
		const cat = catalog([
			{
				capability_kind: 'skill',
				capability_key: 'org-bare',
				label: 'Org Bare',
				description: null,
				in_library: false,
				enabled: false,
				source: 'org'
			}
		]);
		expect(orgSkillBadges(cat).get('org-bare')).toEqual({
			source: 'org',
			author: null,
			approver: null
		});
	});
});

describe('formatDeleteConflict', () => {
	it('appends the active_matter_count when present', () => {
		const err = new LQAIApiError(
			409,
			'conflict',
			'Practice area has active matters filed under it; archive or re-file them first.',
			{ key: 'commercial', active_matter_count: 3 }
		);
		expect(formatDeleteConflict(err)).toBe(
			'Practice area has active matters filed under it; archive or re-file them first. (3 active matters)'
		);
	});

	it('singularizes a count of one', () => {
		const err = new LQAIApiError(409, 'conflict', 'blocked', { active_matter_count: 1 });
		expect(formatDeleteConflict(err)).toBe('blocked (1 active matter)');
	});

	it('falls back to the bare message when no count is present', () => {
		const err = new LQAIApiError(404, 'not_found', 'practice area not found');
		expect(formatDeleteConflict(err)).toBe('practice area not found');
	});

	it('falls back for non-Error throws', () => {
		expect(formatDeleteConflict('boom')).toBe('Failed to delete the practice area.');
	});
});
