import { describe, expect, it } from 'vitest';

import type { ProfileApplyResult, ProfileSummary } from '$lib/lq-ai/api/profiles';
import {
	adoptedCount,
	blankIdentityComplete,
	buildApplyBody,
	canProceed,
	describeApplyOutcome,
	isValidSlug,
	rosterNames,
	shouldAutoLaunchSetup,
	wizardSteps,
	type BlankIdentity
} from '../page-helpers';

const AREA: ProfileSummary = {
	name: 'commercial',
	kind: 'area',
	display_name: 'Commercial',
	description: 'Contracts and matters.',
	area_key: 'commercial',
	unit_label: 'Matter',
	skill_count: 9,
	tool_group_count: 2,
	subagent_count: 3
};

const BLANK: ProfileSummary = {
	name: 'blank',
	kind: 'blank',
	display_name: 'Blank',
	description: 'Start from scratch.',
	area_key: null,
	unit_label: null,
	skill_count: 0,
	tool_group_count: 0,
	subagent_count: 0
};

const COMPLETE_ID: BlankIdentity = { targetKey: 'disputes', name: 'Disputes', unitLabel: 'Matter' };

function result(over: Partial<ProfileApplyResult> = {}): ProfileApplyResult {
	return {
		profile_name: 'commercial',
		target_key: 'commercial',
		area_created: false,
		adopted: { skill: [], tool: [] },
		bindings_written: { skill: 0, tool: 0 },
		roster_subagents: 0,
		hitl_tools: 0,
		changed_fields: [],
		...over
	};
}

describe('isValidSlug', () => {
	it('accepts anchored lowercase slugs', () => {
		expect(isValidSlug('commercial')).toBe(true);
		expect(isValidSlug('m-and-a')).toBe(true);
		expect(isValidSlug('abc')).toBe(true);
	});
	it('rejects bad shapes', () => {
		expect(isValidSlug('')).toBe(false);
		expect(isValidSlug('a')).toBe(false); // too short (needs >= 3)
		expect(isValidSlug('ab')).toBe(false); // still too short (min 3)
		expect(isValidSlug('-lead')).toBe(false); // leading hyphen
		expect(isValidSlug('trail-')).toBe(false); // trailing hyphen
		expect(isValidSlug('Upper')).toBe(false); // uppercase
		expect(isValidSlug('has space')).toBe(false);
	});
});

describe('wizardSteps', () => {
	it('an area profile has no "name" step', () => {
		const keys = wizardSteps('area').map((s) => s.key);
		expect(keys).toEqual(['profile', 'brief', 'review', 'done']);
	});
	it('a blank profile inserts the "name" step', () => {
		const keys = wizardSteps('blank').map((s) => s.key);
		expect(keys).toEqual(['profile', 'name', 'brief', 'review', 'done']);
	});
	it('before a profile is chosen shows the area-shaped skeleton', () => {
		expect(wizardSteps(null).map((s) => s.key)).toEqual(['profile', 'brief', 'review', 'done']);
	});
});

describe('blankIdentityComplete', () => {
	it('true when all three present and key is a valid slug', () => {
		expect(blankIdentityComplete(COMPLETE_ID)).toBe(true);
	});
	it('false when the key is not a slug', () => {
		expect(blankIdentityComplete({ ...COMPLETE_ID, targetKey: 'Bad Key' })).toBe(false);
	});
	it('false when a field is blank/whitespace', () => {
		expect(blankIdentityComplete({ ...COMPLETE_ID, name: '   ' })).toBe(false);
		expect(blankIdentityComplete({ ...COMPLETE_ID, unitLabel: '' })).toBe(false);
	});
});

describe('buildApplyBody', () => {
	it('an area profile sends an empty body (identity from the manifest)', () => {
		expect(buildApplyBody('area', COMPLETE_ID)).toEqual({});
	});
	it('a blank profile sends the three trimmed identity fields', () => {
		expect(
			buildApplyBody('blank', { targetKey: ' disputes ', name: ' Disputes ', unitLabel: 'Matter' })
		).toEqual({ target_key: 'disputes', name: 'Disputes', unit_label: 'Matter' });
	});
});

describe('canProceed', () => {
	it('profile step gates on a selection', () => {
		expect(canProceed('profile', { selectedProfile: null, identity: COMPLETE_ID })).toBe(false);
		expect(canProceed('profile', { selectedProfile: AREA, identity: COMPLETE_ID })).toBe(true);
	});
	it('name step gates on a complete blank identity', () => {
		expect(
			canProceed('name', {
				selectedProfile: BLANK,
				identity: { targetKey: '', name: '', unitLabel: '' }
			})
		).toBe(false);
		expect(canProceed('name', { selectedProfile: BLANK, identity: COMPLETE_ID })).toBe(true);
	});
	it('brief and review are permissive (apply owns the mutation)', () => {
		expect(canProceed('brief', { selectedProfile: AREA, identity: COMPLETE_ID })).toBe(true);
		expect(canProceed('review', { selectedProfile: AREA, identity: COMPLETE_ID })).toBe(true);
	});
});

describe('adoptedCount', () => {
	it('sums across kinds', () => {
		expect(adoptedCount(result({ adopted: { skill: ['a', 'b'], tool: ['c'] } }))).toBe(3);
	});
	it('zero when nothing new', () => {
		expect(adoptedCount(result())).toBe(0);
	});
});

describe('describeApplyOutcome', () => {
	it('keys the headline off area_created', () => {
		expect(describeApplyOutcome(result({ area_created: false }), 'Commercial').headline).toBe(
			'Commercial is ready.'
		);
		expect(describeApplyOutcome(result({ area_created: true }), 'Disputes').headline).toBe(
			'New area “Disputes” is ready.'
		);
	});
	it('reports adopted/roster/hitl counts', () => {
		const o = describeApplyOutcome(
			result({ adopted: { skill: ['a', 'b'], tool: ['c'] }, roster_subagents: 3, hitl_tools: 1 }),
			'Commercial'
		);
		expect(o.lines[0]).toContain('3 capabilities adopted');
		expect(o.lines.some((l) => l.includes('3 sub-agents'))).toBe(true);
		expect(o.lines.some((l) => l.includes('1 stop-and-ask tool'))).toBe(true);
	});
	it('a re-apply that adds nothing is success, not a bare zero', () => {
		const o = describeApplyOutcome(result(), 'Commercial');
		expect(o.lines[0]).toContain('already in your Library');
	});
	it('singularises a single capability', () => {
		const o = describeApplyOutcome(result({ adopted: { skill: ['a'], tool: [] } }), 'Commercial');
		expect(o.lines[0]).toContain('1 capability adopted');
	});
});

describe('rosterNames', () => {
	it('extracts subagent names', () => {
		expect(rosterNames({ subagents: [{ name: 'drafter' }, { name: 'reviewer' }] })).toEqual([
			'drafter',
			'reviewer'
		]);
	});
	it('is defensive against a missing or malformed roster', () => {
		expect(rosterNames({})).toEqual([]);
		expect(rosterNames({ subagents: 'nope' })).toEqual([]);
		expect(rosterNames({ subagents: [{}, { name: '' }, 5] })).toEqual([]);
	});
});

describe('shouldAutoLaunchSetup', () => {
	const base = {
		isAdmin: true,
		role: 'admin' as string | null | undefined,
		dismissed: false,
		libraryEmpty: true
	};
	it('true for a fresh tenant-admin with an empty Library', () => {
		expect(shouldAutoLaunchSetup(base)).toBe(true);
	});
	it('false for the operator (fenced out of apply)', () => {
		expect(shouldAutoLaunchSetup({ ...base, role: 'operator' })).toBe(false);
	});
	it('false once dismissed', () => {
		expect(shouldAutoLaunchSetup({ ...base, dismissed: true })).toBe(false);
	});
	it('false once the Library has entries', () => {
		expect(shouldAutoLaunchSetup({ ...base, libraryEmpty: false })).toBe(false);
	});
	it('false for a non-admin', () => {
		expect(shouldAutoLaunchSetup({ ...base, isAdmin: false })).toBe(false);
	});
});
