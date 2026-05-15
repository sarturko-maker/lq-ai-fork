/**
 * Unit tests for SlashPopover helpers (Wave D.2, Task 3.3).
 *
 * Convention note: this codebase does not install @testing-library/svelte
 * (see AttachKBModal.test.ts / AttachedSkillPill.test.ts headers). CLAUDE.md
 * forbids adding libraries without justification. So we follow the
 * established pattern: the .svelte file exports its pure logic from
 * <script context="module">, and we exercise those helpers here. The
 * template glue (`<svelte:window on:keydown>`, listbox rendering, etc.)
 * is exercised in the Cypress e2e once Task 7.1 wires the composer.
 *
 * Coverage:
 *   - nextIndex(activeIndex, length, direction)
 *   - emptyStateKind(state)
 *   - decideKeyAction(key, state)
 *   - effectiveResult(results, activeIndex)
 *   - fetchResults(query, limit) — async; spy on autocompleteSkills
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
	nextIndex,
	emptyStateKind,
	decideKeyAction,
	effectiveResult,
	fetchResults,
	type SlashPopoverState
} from '../components/SlashPopover.svelte';
import type { SkillAutocompleteItem } from '../types';
import * as skillsApi from '../api/skills';

function makeItem(slug: string, overrides: Partial<SkillAutocompleteItem> = {}): SkillAutocompleteItem {
	return {
		slug,
		slash_alias: null,
		title: slug,
		description: null,
		scope: 'builtin',
		icon: null,
		...overrides
	};
}

function makeState(overrides: Partial<SlashPopoverState> = {}): SlashPopoverState {
	return {
		results: [],
		activeIndex: 0,
		loading: false,
		error: null,
		query: '',
		...overrides
	};
}

describe('SlashPopover.nextIndex', () => {
	it('moves forward and wraps at the end (ArrowDown)', () => {
		expect(nextIndex(0, 3, 1)).toBe(1);
		expect(nextIndex(1, 3, 1)).toBe(2);
		expect(nextIndex(2, 3, 1)).toBe(0); // wrap forward
	});

	it('moves backward and wraps at the start (ArrowUp)', () => {
		expect(nextIndex(2, 3, -1)).toBe(1);
		expect(nextIndex(1, 3, -1)).toBe(0);
		expect(nextIndex(0, 3, -1)).toBe(2); // wrap backward
	});

	it('returns 0 when length is 0 (no rows to cycle through)', () => {
		expect(nextIndex(0, 0, 1)).toBe(0);
		expect(nextIndex(0, 0, -1)).toBe(0);
	});
});

describe('SlashPopover.emptyStateKind', () => {
	it('returns "loading" when loading flag is set', () => {
		expect(emptyStateKind(makeState({ loading: true }))).toBe('loading');
	});

	it('returns "error" when error is set (even with results present)', () => {
		expect(
			emptyStateKind(
				makeState({ error: 'boom', results: [makeItem('a')] })
			)
		).toBe('error');
	});

	it('returns "empty-with-query" when no results and query non-empty', () => {
		expect(emptyStateKind(makeState({ query: 'nda', results: [] }))).toBe(
			'empty-with-query'
		);
	});

	it('returns "empty-no-query" when no results and no query', () => {
		expect(emptyStateKind(makeState({ query: '', results: [] }))).toBe(
			'empty-no-query'
		);
	});

	it('returns "results" when there are results to show', () => {
		expect(
			emptyStateKind(
				makeState({ query: 'n', results: [makeItem('nda-review')] })
			)
		).toBe('results');
	});
});

describe('SlashPopover.decideKeyAction', () => {
	const results = [makeItem('a'), makeItem('b'), makeItem('c')];

	it('Escape returns dismiss regardless of result presence', () => {
		expect(decideKeyAction('Escape', makeState()).kind).toBe('dismiss');
		expect(decideKeyAction('Escape', makeState({ results })).kind).toBe(
			'dismiss'
		);
	});

	it('Enter returns select for the current activeIndex when results present', () => {
		const action = decideKeyAction(
			'Enter',
			makeState({ results, activeIndex: 1 })
		);
		expect(action.kind).toBe('select');
		if (action.kind === 'select') {
			expect(action.result.slug).toBe('b');
		}
	});

	it('Enter returns noop when there are no results', () => {
		expect(decideKeyAction('Enter', makeState({ results: [] })).kind).toBe(
			'noop'
		);
	});

	it('ArrowDown moves activeIndex forward (with wrap)', () => {
		const action = decideKeyAction(
			'ArrowDown',
			makeState({ results, activeIndex: 2 })
		);
		expect(action.kind).toBe('move');
		if (action.kind === 'move') {
			expect(action.nextIndex).toBe(0);
		}
	});

	it('ArrowUp moves activeIndex backward (with wrap)', () => {
		const action = decideKeyAction(
			'ArrowUp',
			makeState({ results, activeIndex: 0 })
		);
		expect(action.kind).toBe('move');
		if (action.kind === 'move') {
			expect(action.nextIndex).toBe(2);
		}
	});

	it('ArrowDown / ArrowUp are noops when there are no results', () => {
		expect(decideKeyAction('ArrowDown', makeState({ results: [] })).kind).toBe(
			'noop'
		);
		expect(decideKeyAction('ArrowUp', makeState({ results: [] })).kind).toBe(
			'noop'
		);
	});

	it('Unrelated keys return noop', () => {
		expect(decideKeyAction('a', makeState({ results })).kind).toBe('noop');
		expect(decideKeyAction('Tab', makeState({ results })).kind).toBe('noop');
	});
});

describe('SlashPopover.effectiveResult', () => {
	const results = [makeItem('a'), makeItem('b')];

	it('returns the item at activeIndex', () => {
		expect(effectiveResult(results, 0)?.slug).toBe('a');
		expect(effectiveResult(results, 1)?.slug).toBe('b');
	});

	it('returns undefined for out-of-range or empty', () => {
		expect(effectiveResult(results, 2)).toBeUndefined();
		expect(effectiveResult([], 0)).toBeUndefined();
		expect(effectiveResult(results, -1)).toBeUndefined();
	});
});

describe('SlashPopover.fetchResults', () => {
	beforeEach(() => {
		vi.restoreAllMocks();
	});

	afterEach(() => {
		vi.restoreAllMocks();
	});

	it('calls autocompleteSkills with query + limit and returns results', async () => {
		const results = [makeItem('nda-review', { title: 'NDA Review' })];
		const spy = vi
			.spyOn(skillsApi, 'autocompleteSkills')
			.mockResolvedValue({ results });
		const out = await fetchResults('nda', 10);
		expect(spy).toHaveBeenCalledTimes(1);
		expect(spy).toHaveBeenCalledWith('nda', 10);
		expect(out).toEqual(results);
	});

	it('passes the empty query through unchanged (matches autocomplete back-end contract)', async () => {
		const spy = vi
			.spyOn(skillsApi, 'autocompleteSkills')
			.mockResolvedValue({ results: [] });
		await fetchResults('', 10);
		expect(spy).toHaveBeenCalledWith('', 10);
	});

	it('propagates errors from the API client (caller handles)', async () => {
		vi.spyOn(skillsApi, 'autocompleteSkills').mockRejectedValue(
			new Error('network down')
		);
		await expect(fetchResults('nda', 10)).rejects.toThrow('network down');
	});
});
