<script lang="ts">
	/**
	 * INTAKE-5a — the lawyer's Inbox list (ADR-F086, plan rulings 1/3/7/8).
	 *
	 * ONE component, two placements (plan ruling 1): the cockpit-level Inbox view
	 * (`?view=inbox`, every matter) and the matter strip's Inbox tab
	 * (`projectId` set, that matter only). The order is the SERVER's
	 * `attention_rank` — this panel never re-sorts (ruling 3).
	 *
	 * It renders no approval card (ruling 2): a row that needs a decision says so
	 * and the detail deep-links into the conversation, where `HitlConfirmCard`
	 * already works.
	 *
	 * Structure follows `GridsPanel` (PageShell / SectionHeader / Skeleton, the
	 * `loadGeneration` out-of-order guard, pure helpers in a sibling module).
	 * Everything is text-interpolated — subjects, labels and summary bullets are
	 * sender- or agent-controlled, so there is no `{@html}` anywhere on this path.
	 */
	import { onDestroy, onMount, untrack } from 'svelte';
	import MailIcon from '@lucide/svelte/icons/mail';

	import { Button } from '$lib/components/ui/button/index.js';
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';
	import PageShell from '$lib/lq-ai/components/primitives/PageShell.svelte';
	import SectionHeader from '$lib/lq-ai/components/primitives/SectionHeader.svelte';
	import StatusDot from '$lib/lq-ai/components/primitives/StatusDot.svelte';
	import { timeAgo } from '$lib/lq-ai/cockpit/helpers';
	import { LQAIApiError } from '$lib/lq-ai/api/client';
	import { listIntakeThreads, type IntakeThread } from '$lib/lq-ai/api/intakeThreads';
	import {
		attentionChip,
		attentionStripe,
		emptyCopy,
		filterQuery,
		INBOX_FILTERS,
		matterRef,
		rowMeta,
		type InboxFilter,
		type IntakeStripe
	} from './intake-panel-helpers';

	let {
		projectId,
		nowMs,
		reloadKey = 0,
		onOpen
	}: {
		/** Set = the matter tab (that matter's threads only); absent = every matter. */
		projectId?: string;
		nowMs: number;
		/** Bumped by the host when a run settles — pulls one quiet refresh. */
		reloadKey?: number;
		onOpen: (threadId: string) => void;
	} = $props();

	const PAGE_SIZE = 50;

	let filter = $state<InboxFilter>('attention');
	let threads = $state<IntakeThread[] | null>(null);
	let nextCursor = $state<string | null>(null);
	let loading = $state(true);
	let loadingMore = $state(false);
	let error = $state<string | null>(null);

	// Out-of-order guard: a slow fetch must not clobber a fresher one, and a
	// filter switch must supersede whatever the previous filter had in flight
	// (the GridsPanel / DocumentsPanel generation pattern).
	let loadGeneration = 0;
	let destroyed = false;

	// Stripes are the ONLY new visual device this slice adds (plan ruling 8) —
	// and they are the existing brand / destructive / attention tokens.
	const STRIPE_CLASS: Record<Exclude<IntakeStripe, null>, string> = {
		brand: 'bg-brand',
		destructive: 'bg-destructive',
		warning: 'bg-status-attention'
	};

	function stripeClass(stripe: IntakeStripe): string {
		return stripe ? STRIPE_CLASS[stripe] : 'bg-transparent';
	}

	async function load(quiet = false) {
		const gen = ++loadGeneration;
		if (!quiet) {
			loading = true;
			error = null;
		}
		try {
			const page = await listIntakeThreads({
				projectId,
				limit: PAGE_SIZE,
				...filterQuery(filter)
			});
			if (gen !== loadGeneration || destroyed) return;
			threads = page.items;
			nextCursor = page.next_cursor;
			if (!quiet) error = null;
		} catch (e) {
			if (gen !== loadGeneration || destroyed) return;
			if (!quiet) {
				error = e instanceof LQAIApiError ? e.message : 'Could not load your email threads.';
			}
		} finally {
			if (!quiet && gen === loadGeneration) loading = false;
		}
	}

	async function loadMore() {
		if (!nextCursor || loadingMore) return;
		const gen = loadGeneration;
		loadingMore = true;
		try {
			const page = await listIntakeThreads({
				projectId,
				limit: PAGE_SIZE,
				cursor: nextCursor,
				...filterQuery(filter)
			});
			// A filter switch (or a reload) since this request started wins.
			if (gen !== loadGeneration || destroyed) return;
			threads = [...(threads ?? []), ...page.items];
			nextCursor = page.next_cursor;
		} catch (e) {
			if (gen !== loadGeneration || destroyed) return;
			error = e instanceof LQAIApiError ? e.message : 'Could not load more threads.';
		} finally {
			if (!destroyed) loadingMore = false;
		}
	}

	function selectFilter(next: InboxFilter) {
		if (next === filter) return;
		filter = next;
		nextCursor = null;
		void load();
	}

	onMount(() => {
		void load();
	});
	onDestroy(() => {
		destroyed = true;
	});

	// Settle reconcile: the host bumps reloadKey when a run settles, so a thread
	// the agent just concluded moves out of "Needs you" without a manual refresh.
	let lastReloadKey = untrack(() => reloadKey);
	$effect(() => {
		if (reloadKey === lastReloadKey) return;
		lastReloadKey = reloadKey;
		void load(true);
	});

	// Container-width collapse (~700px): the panel lives inside a resizable pane,
	// so viewport breakpoints would lie. Starts optimistic so the first paint at
	// desktop widths does not flash the stacked layout.
	let panelWidth = $state(1024);
	const isNarrow = $derived(panelWidth < 700);

	// The mailbox address is a property of the mailbox, not of a row; every row
	// on a page shares it in the ordinary single-mailbox case, so the header
	// states it once rather than repeating it down the list.
	const addresses = $derived(
		Array.from(new Set((threads ?? []).map((t) => t.mailbox_address).filter(Boolean)))
	);
	const subtitle = $derived(
		addresses.length === 1
			? `Email threads arriving at ${addresses[0]}.`
			: 'Email threads the intake mailbox has handled.'
	);
</script>

<div bind:clientWidth={panelWidth}>
	<PageShell class="space-y-4">
		<SectionHeader title="Inbox" {subtitle} />

		<!-- Segmented filter. "Needs you" is the server's own attention set
		     (ranks 0–2) — the same definition the rail badge counts. -->
		<div class="flex flex-wrap items-center justify-between gap-3">
			<div
				class="border-border bg-muted/40 focus-within:ring-ring inline-flex rounded-lg border p-0.5"
				role="group"
				aria-label="Filter threads"
				data-testid="lq-inbox-filters"
			>
				{#each INBOX_FILTERS as f (f.id)}
					<button
						type="button"
						aria-pressed={filter === f.id}
						class="focus-visible:ring-ring rounded-md px-3 py-1 text-xs font-medium transition-colors duration-150 focus-visible:ring-2 focus-visible:outline-none {filter ===
						f.id
							? 'bg-card text-foreground shadow-xs'
							: 'text-muted-foreground hover:text-foreground'}"
						data-testid="lq-inbox-filter-{f.id}"
						onclick={() => selectFilter(f.id)}
					>
						{f.label}
					</button>
				{/each}
			</div>
			{#if threads}
				<span class="text-muted-foreground text-xs tabular-nums" data-testid="lq-inbox-count">
					{threads.length}{nextCursor ? '+' : ''}
					{threads.length === 1 && !nextCursor ? 'thread' : 'threads'}
				</span>
			{/if}
		</div>

		{#if loading}
			<div class="space-y-2" data-testid="lq-inbox-loading">
				{#each [0, 1, 2, 3] as i (i)}
					<Skeleton class="h-16 w-full rounded-lg" />
				{/each}
			</div>
		{:else if error}
			<p class="text-destructive text-sm" data-testid="lq-inbox-error">
				{error}
				<button type="button" class="ml-2 underline" onclick={() => load()}>Retry</button>
			</p>
		{:else if !threads || threads.length === 0}
			<div
				class="border-border rounded-lg border border-dashed p-6 text-center"
				data-testid="lq-inbox-empty"
			>
				<MailIcon class="text-muted-foreground mx-auto size-6" aria-hidden="true" />
				<p class="text-foreground mt-2 text-sm font-medium">{emptyCopy(filter)}</p>
				<p class="text-muted-foreground mt-1 text-xs">
					Threads appear here as the intake mailbox receives them.
				</p>
			</div>
		{:else}
			<ul class="space-y-2" data-testid="lq-inbox-list">
				{#each threads as thread (thread.id)}
					{@const chip = attentionChip(thread)}
					{@const stripe = attentionStripe(thread)}
					<li>
						<button
							type="button"
							class="border-border bg-card hover:bg-muted/40 focus-visible:ring-ring flex w-full items-stretch gap-0 overflow-hidden rounded-lg border text-left transition-colors duration-150 focus-visible:ring-2 focus-visible:outline-none"
							data-testid="lq-inbox-row"
							data-thread-id={thread.id}
							onclick={() => onOpen(thread.id)}
						>
							<!-- 3px attention stripe: brand / destructive / warning, else nothing. -->
							<span
								class="w-[3px] shrink-0 self-stretch {stripeClass(stripe)}"
								aria-hidden="true"
								data-stripe={stripe ?? 'none'}
							></span>
							<span
								class="flex min-w-0 flex-1 gap-3 p-3 {isNarrow
									? 'flex-col'
									: 'items-center justify-between'}"
							>
								<span class="min-w-0 flex-1">
									<span class="text-foreground block truncate text-sm font-medium"
										>{thread.subject || '(no subject)'}</span
									>
									<span class="text-muted-foreground block truncate text-xs">{rowMeta(thread)}</span
									>
								</span>
								<span
									class="flex shrink-0 items-center gap-3 {isNarrow ? 'flex-wrap' : 'justify-end'}"
								>
									{#if !projectId}
										<!-- The matter tab already knows which matter this is; showing
										     "this matter" on every row would be noise, so it shows nothing. -->
										<span
											class="text-muted-foreground font-mono text-[11px] whitespace-nowrap"
											data-testid="lq-inbox-matter">{matterRef(thread)}</span
										>
									{/if}
									<StatusDot status={chip.dot} label={chip.label} class="whitespace-nowrap" />
									<span class="text-muted-foreground text-[11px] whitespace-nowrap tabular-nums"
										>{timeAgo(thread.last_inbound_at, nowMs)}</span
									>
								</span>
							</span>
						</button>
					</li>
				{/each}
			</ul>

			{#if nextCursor}
				<div class="flex justify-center pt-1">
					<Button
						variant="outline"
						size="sm"
						disabled={loadingMore}
						onclick={loadMore}
						data-testid="lq-inbox-load-more"
					>
						{loadingMore ? 'Loading…' : 'Load more'}
					</Button>
				</div>
			{/if}
		{/if}
	</PageShell>
</div>
