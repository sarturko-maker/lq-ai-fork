<script context="module" lang="ts">
	import { TABS, isTabVisible, type TabDef, type User, type TabVisibilityOpts } from '../tabs';

	export type TopTabBarUser = User;

	export function visibleTabsFor(user: User | null, opts: TabVisibilityOpts = {}): TabDef[] {
		return TABS.filter((t) => isTabVisible(t.id, user, opts));
	}

	/**
	 * State-dependent colour/underline classes for a tab (F2-M3). Active wins
	 * (single primary accent); coming-soon (unavailable) is dimmest; the legacy
	 * group rests one step quieter than core so the section reads as secondary.
	 */
	export function tabStateClass(opts: {
		active: boolean;
		available: boolean;
		legacy: boolean;
	}): string {
		if (opts.active) return 'border-primary text-primary';
		if (!opts.available) return 'text-muted-foreground/60';
		if (opts.legacy) return 'text-muted-foreground/70 hover:text-foreground';
		return 'text-muted-foreground hover:text-foreground';
	}
</script>

<script lang="ts">
	import { goto } from '$app/navigation';
	import { activeTabFor, isTabAvailable, tabGroupOf, type TabId } from '../tabs';
	import { tabIcon } from '../tab-icons';
	import { preferences } from '$lib/lq-ai/stores/preferences';
	import ComingSoonModal from './ComingSoonModal.svelte';

	export let user: User | null;
	export let pathname: string;

	$: tabs = visibleTabsFor(user, { autonomousEnabled: $preferences.autonomous_enabled });
	$: active = activeTabFor(pathname);

	let comingSoonOpen = false;
	let comingSoonTabId: TabId = 'home';
	let comingSoonWave: string | undefined;

	function handleTabClick(tabId: TabId, route: string, wave: string | undefined) {
		if (isTabAvailable(tabId)) {
			goto(route);
		} else {
			comingSoonTabId = tabId;
			comingSoonWave = wave;
			comingSoonOpen = true;
		}
	}

	function handleTabKeydown(e: KeyboardEvent, idx: number) {
		if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
			e.preventDefault();
			const delta = e.key === 'ArrowRight' ? 1 : -1;
			const next = (idx + delta + tabs.length) % tabs.length;
			const buttons = (e.currentTarget as HTMLElement)
				.closest('ul')
				?.querySelectorAll<HTMLButtonElement>('button[role="tab"]');
			buttons?.[next]?.focus();
		}
	}
</script>

<!-- F2-M2: migrated off `--lq-*` to semantic tokens (the dark-mode fix) +
     scira calm — quiet muted resting state, a single primary accent on the
     active tab, lighter underline. Matches the cockpit CockpitHeader idiom so
     the two eras share one accent.
     F2-M3: condensed (tighter `gap-0.5`) + subtle section separators between
     presentational groups (core / legacy-executor / gated) with the legacy
     group resting one step quieter. RESTYLE/GROUP ONLY — every tab stays
     visible, clickable, in source order; one `<ul role="tablist">` keeps
     arrow-key nav intact (separators are inert presentation rows). -->
<nav class="border-b border-border px-4" aria-label="Primary">
	<ul class="m-0 flex list-none items-stretch gap-0.5 p-0" role="tablist">
		{#each tabs as tab, tabIndex (tab.id)}
			{#if tabIndex > 0 && tabGroupOf(tab) !== tabGroupOf(tabs[tabIndex - 1])}
				<li
					role="presentation"
					aria-hidden="true"
					class="mx-1.5 h-5 w-px self-center bg-border"
				></li>
			{/if}
			<li role="presentation">
				<button
					type="button"
					role="tab"
					aria-selected={active === tab.id}
					aria-controls="lq-main"
					class="inline-flex cursor-pointer items-center gap-1 border-0 border-b-2 border-transparent bg-transparent px-2.5 py-3 text-sm font-medium transition-colors duration-150 ease-out focus-visible:rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring {tabStateClass(
						{
							active: active === tab.id,
							available: isTabAvailable(tab.id),
							legacy: tabGroupOf(tab) === 'legacy'
						}
					)}"
					on:click={() => handleTabClick(tab.id, tab.route, tab.shipsInWave)}
					on:keydown={(e) => handleTabKeydown(e, tabIndex)}
				>
					<svelte:component this={tabIcon(tab.id)} class="size-4 shrink-0" aria-hidden="true" />
					<span>{tab.label}</span>
				</button>
			</li>
		{/each}
	</ul>
</nav>

<ComingSoonModal
	open={comingSoonOpen}
	tabId={comingSoonTabId}
	wave={comingSoonWave}
	onClose={() => (comingSoonOpen = false)}
/>
