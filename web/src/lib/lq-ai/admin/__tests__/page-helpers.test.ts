/**
 * Shared admin page-helper tests (SETUP-4b review fix 4) — the single home for
 * describeMutationError + catalogEntriesForKind coverage (previously duplicated
 * per admin page).
 */
import { describe, expect, it } from 'vitest';

import { LQAIApiError } from '$lib/lq-ai/api/client';
import type { DeploymentCapabilitiesResponse } from '$lib/lq-ai/api/admin';
import { catalogEntriesForKind, describeMutationError } from '../page-helpers';

describe('describeMutationError', () => {
	it('surfaces an LQAIApiError message verbatim', () => {
		const err = new LQAIApiError(409, 'conflict', 'A practice area with this key already exists.');
		expect(describeMutationError(err, 'fallback')).toBe(
			'A practice area with this key already exists.'
		);
	});

	it('never special-cases an error code — the raw message passes through untouched', () => {
		// SETUP-3b review fix F4 contract: no client-side synthesis keyed on codes.
		const err = new LQAIApiError(409, 'some_code', 'server text');
		expect(describeMutationError(err, 'fallback')).toBe('server text');
	});

	it('falls back when the LQAIApiError message is empty', () => {
		const err = new LQAIApiError(500, 'internal', '');
		expect(describeMutationError(err, 'fallback')).toBe('fallback');
	});

	it('uses a plain Error message', () => {
		expect(describeMutationError(new Error('net down'), 'fallback')).toBe('net down');
	});

	it('falls back for non-Error throws', () => {
		expect(describeMutationError('boom', 'fallback')).toBe('fallback');
		expect(describeMutationError(undefined, 'fallback')).toBe('fallback');
	});
});

describe('catalogEntriesForKind', () => {
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
						enabled: true
					},
					{
						capability_kind: 'tool',
						capability_key: 'tabular',
						label: 'Grids',
						description: null,
						enabled: false
					}
				]
			},
			{ kind: 'skill', label: 'Skills', entries: [] },
			{ kind: 'playbook', label: 'Playbooks', entries: [] }
		]
	};

	it('returns [] for a null catalog', () => {
		expect(catalogEntriesForKind(null, 'tool')).toEqual([]);
	});

	it('projects a section to {key, label, description} regardless of enabled state', () => {
		expect(catalogEntriesForKind(catalog, 'tool')).toEqual([
			{ key: 'redlining', label: 'Redlining', description: 'd1' },
			{ key: 'tabular', label: 'Grids', description: null }
		]);
	});

	it('returns [] for an empty section', () => {
		expect(catalogEntriesForKind(catalog, 'skill')).toEqual([]);
	});

	it('returns [] for a kind with no section at all', () => {
		const noPlaybooks: DeploymentCapabilitiesResponse = {
			sections: catalog.sections.filter((s) => s.kind !== 'playbook')
		};
		expect(catalogEntriesForKind(noPlaybooks, 'playbook')).toEqual([]);
	});
});
