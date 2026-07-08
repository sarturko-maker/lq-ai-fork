/**
 * Pure-helper tests for the /lq-ai/admin/areas/[key] detail page (SETUP-4b).
 * Shared helpers (describeMutationError, catalogEntriesForKind) are tested in
 * `$lib/lq-ai/admin/__tests__/page-helpers.test.ts` (review fix 4).
 */
import { describe, expect, it } from 'vitest';

import { LQAIApiError } from '$lib/lq-ai/api/client';
import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';
import {
	bindingLabel,
	degradedBindingKeys,
	diffPatch,
	findAreaByKey,
	formatDeleteConflict,
	hasMultipleLedgerBearingGroups,
	parseRosterDraft,
	pickerEmptyState,
	unboundOptions
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
		bound_skills: [],
		bound_tool_groups: [],
		bound_playbooks: [],
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

describe('parseRosterDraft (D6)', () => {
	it('treats an empty textarea as an empty object', () => {
		expect(parseRosterDraft('')).toEqual({ value: {}, error: null });
		expect(parseRosterDraft('   ')).toEqual({ value: {}, error: null });
	});

	it('parses a valid JSON object', () => {
		expect(parseRosterDraft('{"subagents": []}')).toEqual({
			value: { subagents: [] },
			error: null
		});
	});

	it('rejects invalid JSON', () => {
		const result = parseRosterDraft('{not json');
		expect(result.value).toBeNull();
		expect(result.error).toBe('Invalid JSON.');
	});

	it('rejects a JSON array or scalar (must be an object)', () => {
		expect(parseRosterDraft('[]').error).toBe('Must be a JSON object.');
		expect(parseRosterDraft('"just a string"').error).toBe('Must be a JSON object.');
		expect(parseRosterDraft('null').error).toBe('Must be a JSON object.');
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
		const skillCatalog = [{ key: 'shared-key', label: 'Skill', description: null, in_library: false }];
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
});

describe('pickerEmptyState (STORE-2)', () => {
	const nonEmptyCatalog = [{ key: 'redlining', label: 'Redlining', description: null, in_library: true }];

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
