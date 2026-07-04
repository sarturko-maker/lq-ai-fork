/**
 * Pure-helper tests for the /lq-ai/admin/areas/[key] detail page (SETUP-4b).
 */
import { describe, expect, it } from 'vitest';

import { LQAIApiError } from '$lib/lq-ai/api/client';
import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';
import {
	bindingLabel,
	describeMutationError,
	diffPatch,
	findAreaByKey,
	formatDeleteConflict,
	hasMultipleLedgerBearingGroups,
	parseRosterDraft,
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
				default_tier_floor: '2'
			})
		).toEqual({});
	});

	it('includes only the changed fields', () => {
		expect(
			diffPatch(original, {
				name: 'Commercial Contracts',
				unit_label: 'Matter',
				profile_md: '# doctrine',
				default_tier_floor: '2'
			})
		).toEqual({ name: 'Commercial Contracts' });
	});

	it('trims name/unit_label before comparing', () => {
		expect(
			diffPatch(original, {
				name: '  Commercial  ',
				unit_label: ' Matter ',
				profile_md: '# doctrine',
				default_tier_floor: '2'
			})
		).toEqual({});
	});

	it('normalizes an emptied doctrine textarea to null', () => {
		expect(
			diffPatch(original, {
				name: 'Commercial',
				unit_label: 'Matter',
				profile_md: '   ',
				default_tier_floor: '2'
			})
		).toEqual({ profile_md: null });
	});

	it('normalizes an emptied tier-floor select to null', () => {
		expect(
			diffPatch(original, {
				name: 'Commercial',
				unit_label: 'Matter',
				profile_md: '# doctrine',
				default_tier_floor: ''
			})
		).toEqual({ default_tier_floor: null });
	});

	it('parses a numeric tier-floor string', () => {
		expect(
			diffPatch(original, {
				name: 'Commercial',
				unit_label: 'Matter',
				profile_md: '# doctrine',
				default_tier_floor: '4'
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
				default_tier_floor: ''
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
		{ key: 'nda-review', label: 'NDA review', description: null },
		{ key: 'contract-qa', label: 'Contract Q&A', description: null }
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
		{ key: 'redlining', label: 'Redlining', description: null },
		{ key: 'tabular', label: 'Grids', description: null },
		{ key: 'ropa', label: 'ROPA register', description: null }
	];

	it('excludes already-bound entries', () => {
		expect(unboundOptions(options, ['redlining'])).toEqual([
			{ key: 'tabular', label: 'Grids', description: null },
			{ key: 'ropa', label: 'ROPA register', description: null }
		]);
	});

	it('returns every entry when nothing is bound', () => {
		expect(unboundOptions(options, [])).toEqual(options);
	});

	it('returns [] when everything is bound', () => {
		expect(unboundOptions(options, ['redlining', 'tabular', 'ropa'])).toEqual([]);
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

describe('describeMutationError', () => {
	it('surfaces the server message verbatim', () => {
		const err = new LQAIApiError(400, 'validation_error', 'Unsupported agent_config key: foo');
		expect(describeMutationError(err, 'fallback')).toBe('Unsupported agent_config key: foo');
	});

	it('falls back for non-Error throws', () => {
		expect(describeMutationError('boom', 'fallback')).toBe('fallback');
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
