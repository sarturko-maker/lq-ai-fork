<script lang="ts">
	/**
	 * Cockpit shell (UX-A-1, ADR-F014) — the single app shell. Extracted out of
	 * `cockpit/Cockpit.svelte` into a SvelteKit layout so it persists across
	 * navigation: the header + the resizable practice-area rail (the F1-S2.1
	 * paneforge pane ≥880px / off-canvas drawer <880px) stay mounted while the
	 * CANVAS renders whatever page is active — the landing today, the tool
	 * surfaces in later UX-A slices. Because the shell never unmounts, the rail
	 * and the launcher (and the way back to the cockpit) are always present.
	 *
	 * The shell owns the data the rail needs (areas + activity + the nowMs clock)
	 * and shares it with the canvas via `CockpitShellState` context. It does NOT
	 * own the view-switch — that is the landing page's job (`(app)/+page.svelte`).
	 */
	import { onDestroy, onMount } from 'svelte';
	import { fade, fly } from 'svelte/transition';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	import * as Resizable from '$lib/components/ui/resizable/index.js';
	import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';
	import { auth } from '$lib/lq-ai/auth/store';
	import { serverNowMs } from '$lib/lq-ai/agents/server-clock';
	import { initPreferences } from '$lib/lq-ai/stores/preferences';
	import AreaRail from '$lib/lq-ai/cockpit/AreaRail.svelte';
	import CockpitHeader from '$lib/lq-ai/cockpit/CockpitHeader.svelte';
	import { CockpitShellState, setCockpitState } from '$lib/lq-ai/cockpit/context.svelte';
	import { cockpitUrl, MOTION, motionMs, parseCockpitState } from '$lib/lq-ai/cockpit/helpers';

	let { children } = $props();

	// Shared shell state (rail ↔ canvas). Scoped to this shell instance.
	const cockpit = setCockpitState(new CockpitShellState());

	const sel = $derived(parseCockpitState($page.url.searchParams));

	// --- Responsive shell state (unchanged from F1-S2.1) --------------------
	let viewportWidth = $state(1280);
	const isNarrow = $derived(viewportWidth < 880);
	let railPane = $state<ReturnType<typeof Resizable.Pane> | null>(null);
	let railCollapsed = $state(false);
	let drawerOpen = $state(false);
	let resizing = $state(false);
	const reducedMotion =
		typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches;

	$effect(() => {
		if (!isNarrow) {
			drawerOpen = false;
		} else {
			resizing = false;
		}
	});

	let drawerEl = $state<HTMLElement | null>(null);
	$effect(() => {
		if (drawerOpen) drawerEl?.focus();
	});

	function toggleRail() {
		if (isNarrow) {
			drawerOpen = !drawerOpen;
			return;
		}
		if (!railPane) return;
		if (railPane.isCollapsed()) railPane.expand();
		else railPane.collapse();
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape' && drawerOpen) drawerOpen = false;
	}
	// ------------------------------------------------------------------------

	let ticker: ReturnType<typeof setInterval> | null = null;
	onMount(() => {
		initPreferences(); // feeds the header Tools-menu gating (autonomous opt-in)
		cockpit.loadAreas();
		cockpit.loadActivity();
		cockpit.nowMs = serverNowMs();
		ticker = setInterval(() => {
			cockpit.nowMs = serverNowMs();
		}, 30_000);
	});
	onDestroy(() => {
		if (ticker) clearInterval(ticker);
	});

	function nav(url: string) {
		goto(url, { keepFocus: true, noScroll: true });
	}

	function enterArea(area: PracticeArea) {
		drawerOpen = false;
		nav(cockpitUrl({ area: area.key }));
	}

	function openUnfiled() {
		drawerOpen = false;
		nav(cockpitUrl({ unfiled: true }));
	}

	function newMatter() {
		// "Start something new" → the landing launcher (ADR-F002: a matter binds
		// to an area, so this routes to the intent entry, not an unbound thread).
		drawerOpen = false;
		nav(cockpitUrl({}));
	}
</script>

<svelte:window bind:innerWidth={viewportWidth} onkeydown={handleKeydown} />

{#snippet railContent()}
	<AreaRail
		areas={cockpit.areas}
		areasError={cockpit.areasError}
		unfiled={cockpit.activity?.unfiled ?? null}
		matters={cockpit.activity?.matters ?? null}
		nowMs={cockpit.nowMs}
		user={$auth.user ?? null}
		selectedAreaKey={sel.area}
		unfiledOpen={sel.unfiled}
		onSelectArea={enterArea}
		onSelectUnfiled={openUnfiled}
		onNewMatter={newMatter}
	/>
{/snippet}

<div class="bg-background text-foreground flex h-dvh min-h-0 flex-col" data-testid="lq-cockpit">
	<CockpitHeader
		user={$auth.user ?? null}
		railHidden={isNarrow ? !drawerOpen : railCollapsed}
		onToggleRail={toggleRail}
	/>
	<div class="relative min-h-0 flex-1">
		<!-- ONE pane group: the rail pane (+ handle) leave the group below the
		     breakpoint, but the MAIN pane never remounts — a live canvas (a
		     conversation, a tool) survives crossing 880px. -->
		<Resizable.PaneGroup direction="horizontal" autoSaveId="lq-cockpit-panes" class="h-full">
			{#if !isNarrow}
				<Resizable.Pane
					id="cockpit-rail"
					order={1}
					collapsible
					collapsedSize={0}
					defaultSize={18}
					minSize={13}
					maxSize={30}
					class={resizing || reducedMotion ? '' : 'transition-[flex-grow] duration-200 ease-out'}
					bind:this={railPane}
					onCollapse={() => (railCollapsed = true)}
					onExpand={() => (railCollapsed = false)}
				>
					{@render railContent()}
				</Resizable.Pane>
				<Resizable.Handle
					class="hover:bg-primary/40 data-[active]:bg-primary/60 transition-colors duration-150 ease-out"
					onDraggingChange={(d) => (resizing = d)}
				/>
			{/if}
			<Resizable.Pane id="cockpit-main" order={2} defaultSize={82}>
				<main class="h-full min-h-0 overflow-y-auto scroll-smooth overscroll-contain">
					{@render children()}
				</main>
			</Resizable.Pane>
		</Resizable.PaneGroup>
		{#if isNarrow && drawerOpen}
			<!-- Scrim: tokenized wash, never a black sheet. -->
			<button
				type="button"
				class="bg-foreground/20 absolute inset-0 z-30 cursor-default"
				aria-label="Close navigation"
				transition:fade={{ duration: motionMs(MOTION.base) }}
				onclick={() => (drawerOpen = false)}
			></button>
			<div
				class="border-border bg-background absolute inset-y-0 left-0 z-40 w-72 max-w-[85%] border-r shadow-lg outline-none"
				data-testid="lq-cockpit-drawer"
				role="dialog"
				aria-modal="true"
				aria-label="Practice areas"
				tabindex="-1"
				bind:this={drawerEl}
				transition:fly={{ x: -24, duration: motionMs(MOTION.base), opacity: 0.4 }}
			>
				{@render railContent()}
			</div>
		{/if}
	</div>
</div>
