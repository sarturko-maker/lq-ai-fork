<script context="module" lang="ts">
	/**
	 * SlashPopover — typeahead listbox rendered by the composer when the
	 * user types a leading "/" to invoke a skill (Wave D.2 Task 3.3).
	 *
	 * Caller contract:
	 *   - Parent (eventually `ChatPanel.svelte`, Task 7.1) *conditionally
	 *     renders* this component when the slash-typeahead is open. While
	 *     mounted, the component owns global keyboard handling via
	 *     `<svelte:window on:keydown>` — Arrow keys cycle the active row,
	 *     Enter selects, Escape dismisses. Unmount the component to hand
	 *     keyboard control back to the composer.
	 *   - `onSelect` fires on row click (mousedown|preventDefault, so the
	 *     event lands before the composer blurs and tears the popover
	 *     out from under the click) and on Enter.
	 *   - `onDismiss` fires on Escape.
	 *
	 * Convention notes for reviewers:
	 *   - Callback props (onSelect, onDismiss) match SkillPicker /
	 *     AttachKBModal / AttachedSkillPill rather than
	 *     createEventDispatcher.
	 *   - The API import is a named function — `autocompleteSkills` —
	 *     from `$lib/lq-ai/api/skills`, not a `skillsApi.autocomplete`
	 *     method (the latter was the plan-text shape; the actual export
	 *     shape per Task 3.1 is a plain function).
	 *   - `SkillAutocompleteItem.description` is `string | null` (per
	 *     Task 3.1's wire type), so the template `?? ''`s it.
	 *   - Design tokens (R7): migrated off the legacy `--lq-*` palette onto
	 *     the shipped semantic tokens (Tailwind `bg-popover`/`border-border`/
	 *     `text-muted-foreground`, `shadow-md`→`--elevation-md`). The active
	 *     row uses `bg-accent` (the soft indigo wash; text stays `foreground`,
	 *     matching the old "soft tint, normal ink"); links/focus use
	 *     `text-primary`/`ring-ring`. No `<style>` block — utility classes only.
	 *   - Pure helpers exported from <script context="module"> so vitest
	 *     can exercise them without @testing-library/svelte (which is
	 *     not installed; see AttachKBModal.test.ts header).
	 */
	import { autocompleteSkills } from '$lib/lq-ai/api/skills';
	import type { SkillAutocompleteItem } from '../types';

	export type SlashPopoverState = {
		results: SkillAutocompleteItem[];
		activeIndex: number;
		loading: boolean;
		error: string | null;
		query: string;
	};

	export type EmptyStateKind =
		| 'loading'
		| 'error'
		| 'empty-with-query'
		| 'empty-no-query'
		| 'results';

	export type KeyAction =
		| { kind: 'select'; result: SkillAutocompleteItem }
		| { kind: 'dismiss' }
		| { kind: 'move'; nextIndex: number }
		| { kind: 'noop' };

	/**
	 * Wrap-around index helper used by ArrowDown (direction = +1) and
	 * ArrowUp (direction = -1). When there are no results the function
	 * returns 0 — the caller is expected to early-return at the
	 * decideKeyAction layer, but this defensive default keeps the helper
	 * total (no NaN if it's ever called with length === 0).
	 */
	export function nextIndex(activeIndex: number, length: number, direction: 1 | -1): number {
		if (length === 0) return 0;
		// JS `%` keeps sign of the dividend, so add `length` to handle
		// negative wraps when direction = -1.
		return (((activeIndex + direction) % length) + length) % length;
	}

	/**
	 * Decide which of the five panel states to render. Ordering matters:
	 * loading wins over error wins over results (we don't show stale
	 * results during an in-flight retry).
	 */
	export function emptyStateKind(state: SlashPopoverState): EmptyStateKind {
		if (state.loading) return 'loading';
		if (state.error) return 'error';
		if (state.results.length === 0) {
			return state.query ? 'empty-with-query' : 'empty-no-query';
		}
		return 'results';
	}

	/**
	 * Map a KeyboardEvent.key + current state to the discrete action the
	 * component should take. Pure for testability; the Svelte handler
	 * calls e.preventDefault() at the action-application site so tests
	 * don't need to construct synthetic events.
	 */
	export function decideKeyAction(key: string, state: SlashPopoverState): KeyAction {
		if (key === 'Escape') return { kind: 'dismiss' };
		const len = state.results.length;
		if (len === 0) return { kind: 'noop' };
		if (key === 'Enter') {
			const result = state.results[state.activeIndex];
			if (!result) return { kind: 'noop' };
			return { kind: 'select', result };
		}
		if (key === 'ArrowDown') {
			return { kind: 'move', nextIndex: nextIndex(state.activeIndex, len, 1) };
		}
		if (key === 'ArrowUp') {
			return { kind: 'move', nextIndex: nextIndex(state.activeIndex, len, -1) };
		}
		return { kind: 'noop' };
	}

	/** Bounds-checked active-row read; returns undefined when out of range. */
	export function effectiveResult(
		results: SkillAutocompleteItem[],
		activeIndex: number
	): SkillAutocompleteItem | undefined {
		if (activeIndex < 0 || activeIndex >= results.length) return undefined;
		return results[activeIndex];
	}

	/**
	 * Thin wrapper around the autocomplete client. Returns the bare
	 * results array (the component holds onto the array, not the
	 * envelope). Errors propagate; the component catches and surfaces
	 * them in the "error" empty state.
	 */
	export async function fetchResults(query: string, limit = 10): Promise<SkillAutocompleteItem[]> {
		const resp = await autocompleteSkills(query, limit);
		return resp.results;
	}

	/** Glyph to display when a result omits a custom icon (matches AttachedSkillPill). */
	export function displayIcon(icon: string | null | undefined): string {
		return icon ? icon : '📜';
	}
</script>

<script lang="ts">
	import { onMount } from 'svelte';

	export let query: string;
	export let onSelect: (skill: SkillAutocompleteItem) => void;
	export let onDismiss: () => void;

	let results: SkillAutocompleteItem[] = [];
	let activeIndex = 0;
	let loading = false;
	let error: string | null = null;

	// Monotonic request token: when the user types fast, multiple load()
	// calls can be in-flight simultaneously and resolve out of order. We
	// capture an id at the top of each call and check it before every
	// state mutation so only the most-recent fetch wins.
	let requestId = 0;

	$: kind = emptyStateKind({ results, activeIndex, loading, error, query });

	async function load() {
		const myId = ++requestId;
		loading = true;
		error = null;
		try {
			const next = await fetchResults(query, 10);
			if (myId !== requestId) return; // superseded by a newer call
			results = next;
			// Clamp activeIndex to the new result-set length.
			if (activeIndex >= results.length) activeIndex = 0;
		} catch (e: unknown) {
			if (myId !== requestId) return;
			error =
				e instanceof Error
					? (e.message ?? 'Failed to load suggestions.')
					: 'Failed to load suggestions.';
			results = [];
		} finally {
			if (myId === requestId) loading = false;
		}
	}

	function retry() {
		void load();
	}

	// Initial fetch + re-fetch on query change.
	let lastQuery: string | undefined;
	onMount(() => {
		lastQuery = query;
		void load();
	});
	$: if (lastQuery !== undefined && query !== lastQuery) {
		lastQuery = query;
		activeIndex = 0;
		void load();
	}

	function onWindowKey(e: KeyboardEvent) {
		const action = decideKeyAction(e.key, {
			results,
			activeIndex,
			loading,
			error,
			query
		});
		switch (action.kind) {
			case 'select':
				// stopPropagation so the composer's Enter-to-send handler
				// (Task 7.1) doesn't also fire on the same keystroke.
				e.preventDefault();
				e.stopPropagation();
				onSelect(action.result);
				return;
			case 'dismiss':
				e.preventDefault();
				e.stopPropagation();
				onDismiss();
				return;
			case 'move':
				e.preventDefault();
				e.stopPropagation();
				activeIndex = action.nextIndex;
				return;
			case 'noop':
				// Let unhandled keys continue propagating so the user can
				// keep typing into the composer.
				return;
		}
	}

	function onRowMouseDown(e: MouseEvent, result: SkillAutocompleteItem) {
		// mousedown (not click) so the handler fires before the composer
		// blurs and the popover unmounts out from under us.
		e.preventDefault();
		onSelect(result);
	}
</script>

<svelte:window on:keydown={onWindowKey} />

<!-- tabindex="-1" required by a11y rule when aria-activedescendant is set;
     the composer (Task 7.1) retains focus and keyboard events are caught
     by the window handler above, so this listbox is never tab-focused. -->
<div
	class="flex max-h-80 min-w-[280px] max-w-[min(90vw,420px)] flex-col overflow-y-auto rounded-md border border-border bg-popover p-1 text-[13px] text-popover-foreground shadow-md"
	role="listbox"
	tabindex="-1"
	aria-label="Skill suggestions"
	aria-activedescendant={kind === 'results' ? `lq-slash-row-${activeIndex}` : undefined}
>
	{#if kind === 'loading'}
		<div class="px-3 py-2 text-xs text-muted-foreground" role="presentation">Loading…</div>
	{:else if kind === 'error'}
		<div class="px-3 py-2 text-xs text-destructive dark:text-red-300" role="presentation">
			Couldn't load suggestions ·
			<button
				type="button"
				class="rounded-sm text-xs text-inherit underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
				on:click={retry}>retry</button
			>
		</div>
	{:else if kind === 'empty-with-query'}
		<div class="px-3 py-2 text-xs text-muted-foreground" role="presentation">
			No matching skills · Esc to dismiss
		</div>
	{:else if kind === 'empty-no-query'}
		<div class="px-3 py-2 text-xs text-muted-foreground" role="presentation">
			You don't have any skills yet —
			<a href="/lq-ai/skills" class="text-primary underline">Browse</a>
			·
			<a href="/lq-ai/skills/new" class="text-primary underline">Create</a>
		</div>
	{:else}
		{#each results as r, i}
			<button
				type="button"
				role="option"
				id={`lq-slash-row-${i}`}
				class="flex w-full items-start gap-2 rounded-sm px-3 py-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
				class:bg-accent={i === activeIndex}
				aria-selected={i === activeIndex}
				on:mousedown={(e) => onRowMouseDown(e, r)}
				on:mouseenter={() => (activeIndex = i)}
			>
				<span class="shrink-0 pt-px text-sm leading-snug" aria-hidden="true"
					>{displayIcon(r.icon)}</span
				>
				<span class="flex min-w-0 flex-col">
					<span class="truncate font-medium text-foreground">{r.title}</span>
					<span class="truncate text-xs text-muted-foreground">{r.description ?? ''}</span>
				</span>
			</button>
		{/each}
	{/if}
</div>
