/**
 * Tests for the shared Library-view helpers (STORE-2, ADR-F065) — the single
 * home for grouping/where-used/provenance-badge logic used by BOTH
 * `/lq-ai/admin/library` and the member-readable `/lq-ai/library`.
 */
import { describe, expect, it } from 'vitest';

import type { LibraryEntry } from '$lib/lq-ai/api/library';
import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';
import {
	buildWhereUsedMap,
	groupLibraryEntries,
	provenanceBadge,
	removeConfirmWarning,
	whereUsedFor,
	whereUsedLabel
} from '../page-helpers';

function entry(over: Partial<LibraryEntry> = {}): LibraryEntry {
	return {
		kind: 'skill',
		key: 'nda-review',
		label: 'NDA Review',
		description: 'd',
		source: 'built-in',
		author: null,
		version: null,
		adopted_at: '2026-07-06T00:00:00Z',
		...over
	};
}

describe('provenanceBadge', () => {
	it('renders a built-in badge with no author/version', () => {
		expect(provenanceBadge({ source: 'built-in', author: null, version: null })).toBe(
			'LQ built-in'
		);
	});

	it('renders a community badge with author + version appended', () => {
		expect(
			provenanceBadge({ source: 'community', author: 'Jamie Tso', version: '1.0.0' })
		).toBe('Community · Jamie Tso · v1.0.0');
	});

	it('renders author-only (no version) correctly', () => {
		expect(provenanceBadge({ source: 'community', author: 'Jamie Tso', version: null })).toBe(
			'Community · Jamie Tso'
		);
	});

	it('returns null when source is null (dangling entry, or a playbook — D-A)', () => {
		expect(provenanceBadge({ source: null, author: null, version: null })).toBeNull();
	});

	it('falls back to the raw source string for an unmapped value', () => {
		expect(provenanceBadge({ source: 'exotic', author: null, version: null })).toBe('exotic');
	});
});

describe('groupLibraryEntries', () => {
	it('splits a flat list into tool/skill/playbook buckets, preserving order', () => {
		const entries = [
			entry({ kind: 'tool', key: 'tabular' }),
			entry({ kind: 'skill', key: 'alpha' }),
			entry({ kind: 'tool', key: 'redlining' }),
			entry({ kind: 'playbook', key: 'pb-1' }),
			entry({ kind: 'skill', key: 'beta' })
		];
		const grouped = groupLibraryEntries(entries);
		expect(grouped.tool.map((e) => e.key)).toEqual(['tabular', 'redlining']);
		expect(grouped.skill.map((e) => e.key)).toEqual(['alpha', 'beta']);
		expect(grouped.playbook.map((e) => e.key)).toEqual(['pb-1']);
	});

	it('returns empty buckets for an empty list', () => {
		expect(groupLibraryEntries([])).toEqual({ tool: [], skill: [], playbook: [] });
	});
});

function area(over: Partial<PracticeArea> = {}): PracticeArea {
	return {
		id: 'area-id',
		key: 'commercial',
		name: 'Commercial',
		unit_label: 'Matter',
		configured: true,
		position: 0,
		profile_md: null,
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

describe('buildWhereUsedMap + whereUsedFor', () => {
	it('maps skills, tool groups, and playbooks (id-as-string!) per area', () => {
		const areas = [
			area({
				key: 'commercial',
				name: 'Commercial',
				bound_skills: ['nda-review'],
				bound_tool_groups: ['redlining'],
				bound_playbooks: [{ id: 'pb-1', name: 'NDA playbook' }]
			}),
			area({
				key: 'privacy',
				name: 'Privacy',
				bound_skills: ['nda-review'],
				bound_tool_groups: [],
				bound_playbooks: []
			})
		];
		const map = buildWhereUsedMap(areas);
		expect(whereUsedFor(map, { kind: 'skill', key: 'nda-review' })).toEqual([
			'Commercial',
			'Privacy'
		]);
		expect(whereUsedFor(map, { kind: 'tool', key: 'redlining' })).toEqual(['Commercial']);
		// Playbook id must match AS A STRING (Library keys playbooks by str(id)).
		expect(whereUsedFor(map, { kind: 'playbook', key: 'pb-1' })).toEqual(['Commercial']);
	});

	it('returns [] for a key bound nowhere', () => {
		const map = buildWhereUsedMap([area()]);
		expect(whereUsedFor(map, { kind: 'skill', key: 'unbound-skill' })).toEqual([]);
	});

	it('handles an empty area list', () => {
		const map = buildWhereUsedMap([]);
		expect(whereUsedFor(map, { kind: 'tool', key: 'redlining' })).toEqual([]);
	});
});

describe('whereUsedLabel', () => {
	it('renders the positive line for one or more areas', () => {
		expect(whereUsedLabel(['Commercial'])).toBe('Attached to: Commercial');
		expect(whereUsedLabel(['Commercial', 'Privacy'])).toBe('Attached to: Commercial, Privacy');
	});

	it('renders the honest negative for an unbound entry', () => {
		expect(whereUsedLabel([])).toBe('Not attached to any practice area.');
	});
});

describe('removeConfirmWarning (D-F)', () => {
	it('returns null when the entry is bound nowhere (no extra warning line)', () => {
		expect(removeConfirmWarning([])).toBeNull();
	});

	it('warns about a single area in the singular', () => {
		expect(removeConfirmWarning(['Commercial'])).toBe(
			'The Commercial agent will lose this — it stays attached but stops resolving until you add it back.'
		);
	});

	it('warns about multiple areas in the plural', () => {
		expect(removeConfirmWarning(['Commercial', 'Privacy'])).toBe(
			'The Commercial, Privacy agents will lose this — it stays attached but stops resolving until you add it back.'
		);
	});
});
