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
		approver: null,
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
		expect(provenanceBadge({ source: 'community', author: 'Jamie Tso', version: '1.0.0' })).toBe(
			'Community · Jamie Tso · v1.0.0'
		);
	});

	it('renders author-only (no version) correctly', () => {
		expect(provenanceBadge({ source: 'community', author: 'Jamie Tso', version: null })).toBe(
			'Community · Jamie Tso'
		);
	});

	it('returns null when source is null (dangling entry, or a playbook — D-A)', () => {
		expect(provenanceBadge({ source: null, author: null, version: null })).toBeNull();
	});

	it('suppresses the backend "unversioned" sentinel — never renders "vunversioned"', () => {
		// derive_summary sends the sentinel (not null) for a versionless skill (D-E);
		// the badge must treat it as no-version (STORE-2 review fix).
		expect(
			provenanceBadge({ source: 'community', author: 'Jamie Tso', version: 'unversioned' })
		).toBe('Community · Jamie Tso');
	});

	it('falls back to the raw source string for an unmapped value', () => {
		expect(provenanceBadge({ source: 'exotic', author: null, version: null })).toBe('exotic');
	});

	// B-2b (ADR-F067 D2/D3, D3.5 wire gap) — org-authored provenance badge.
	it('renders "Org-authored · {author} · approved by {approver}" for an org skill', () => {
		expect(provenanceBadge({ source: 'org', author: 'Jamie Tso', approver: 'Alex Admin' })).toBe(
			'Org-authored · Jamie Tso · approved by Alex Admin'
		);
	});

	it('omits the approved-by clause when approver is absent', () => {
		expect(provenanceBadge({ source: 'org', author: 'Jamie Tso', approver: null })).toBe(
			'Org-authored · Jamie Tso'
		);
	});

	it('omits author when absent (the member Library read never carries org author)', () => {
		expect(provenanceBadge({ source: 'org', author: null, approver: 'Alex Admin' })).toBe(
			'Org-authored · approved by Alex Admin'
		);
	});

	it('renders the bare source label when neither author nor approver is present', () => {
		expect(provenanceBadge({ source: 'org', author: null, approver: null })).toBe('Org-authored');
	});

	it('never appends a version bit for an org skill even when version is present', () => {
		expect(
			provenanceBadge({ source: 'org', author: 'Jamie Tso', version: '1.0.0', approver: null })
		).toBe('Org-authored · Jamie Tso');
	});

	// B-4 (ADR-F067 D2/D3) — an approved org-authored PLAYBOOK entry gets the
	// same badge automatically (provenanceBadge is kind-generic; the backend now
	// emits source='org'+author+approver for approved org playbooks).
	it('renders the org badge for an approved org playbook entry (kind-generic, B-4)', () => {
		expect(
			provenanceBadge(
				entry({
					kind: 'playbook',
					key: 'pb-1',
					source: 'org',
					author: 'Jamie Tso',
					version: '2',
					approver: 'Alex Admin'
				})
			)
		).toBe('Org-authored · Jamie Tso · approved by Alex Admin');
	});
});

describe('groupLibraryEntries', () => {
	it('splits a flat list into tool/skill/playbook/knowledge buckets, preserving order', () => {
		const entries = [
			entry({ kind: 'tool', key: 'tabular' }),
			entry({ kind: 'skill', key: 'alpha' }),
			entry({ kind: 'tool', key: 'redlining' }),
			entry({ kind: 'playbook', key: 'pb-1' }),
			entry({ kind: 'skill', key: 'beta' }),
			entry({ kind: 'knowledge', key: 'kb-1' })
		];
		const grouped = groupLibraryEntries(entries);
		expect(grouped.tool.map((e) => e.key)).toEqual(['tabular', 'redlining']);
		expect(grouped.skill.map((e) => e.key)).toEqual(['alpha', 'beta']);
		expect(grouped.playbook.map((e) => e.key)).toEqual(['pb-1']);
		expect(grouped.knowledge.map((e) => e.key)).toEqual(['kb-1']);
	});

	it('returns empty buckets for an empty list', () => {
		expect(groupLibraryEntries([])).toEqual({ tool: [], skill: [], playbook: [], knowledge: [] });
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

describe('buildWhereUsedMap + whereUsedFor', () => {
	it('maps skills, tool groups, playbooks, and knowledge bases (id-as-string!) per area', () => {
		const areas = [
			area({
				key: 'commercial',
				name: 'Commercial',
				bound_skills: ['nda-review'],
				bound_tool_groups: ['redlining'],
				bound_playbooks: [{ id: 'pb-1', name: 'NDA playbook' }],
				bound_knowledge_bases: [{ id: 'kb-1', name: 'Precedent bank' }]
			}),
			area({
				key: 'privacy',
				name: 'Privacy',
				bound_skills: ['nda-review'],
				bound_tool_groups: [],
				bound_playbooks: [],
				bound_knowledge_bases: []
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
		// Knowledge id must match AS A STRING too (same convention, ADR-F067 D1).
		expect(whereUsedFor(map, { kind: 'knowledge', key: 'kb-1' })).toEqual(['Commercial']);
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
