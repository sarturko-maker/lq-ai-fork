<script lang="ts">
	/**
	 * The AI-systems register (read-only) — AIC-1, ADR-F057/F018/F019.
	 *
	 * Surfaces the company's deployment-global register of AI systems (EU AI Act)
	 * inside an AI Compliance matter: one table, a row per system, showing the FACTS
	 * the classification engine (AIC-2) will consume. Rendered in LQ.AI's own F013
	 * design language. Read-only: the AI Compliance Deep Agent writes the register
	 * (guarded, code-validated tools); the user reads and owns it.
	 *
	 * There is deliberately NO risk-tier column: the tier is a legal determination
	 * owned by the deterministic engine (ADR-F057 presence gate), not something the
	 * register stores — it lands in a later slice as its own artifact.
	 *
	 * The live-update machinery (generation-guarded poll + settle reconcile + the
	 * changed-row wash) mirrors RopaRegister.svelte: the poll is the source of truth;
	 * the wash is animation only (ADR-F004).
	 */
	import { onDestroy, onMount } from 'svelte';
	import { fade } from 'svelte/transition';

	import { Badge } from '$lib/components/ui/badge/index.js';
	import {
		Table,
		TableBody,
		TableCell,
		TableHead,
		TableHeader,
		TableRow
	} from '$lib/components/ui/table/index.js';
	import PageShell from '$lib/lq-ai/components/primitives/PageShell.svelte';
	import SectionHeader from '$lib/lq-ai/components/primitives/SectionHeader.svelte';
	import { listAiSystems, type AiSystemRead } from '$lib/lq-ai/api/compliance';
	import { POLL_INTERVAL_MS } from '$lib/lq-ai/agents/helpers';
	import { MOTION, motionMs } from '$lib/lq-ai/cockpit/helpers';

	let {
		// AIC-1: true while the AI Compliance agent is working — drives the live poll
		// so the agent's writes appear here as they commit. The host relays it.
		runActive = false,
		// Bumped by the host when a run settles — triggers one reconcile fetch so the
		// final write is never missed even if the last poll tick raced it.
		reloadKey = 0,
		// ADR-F024: ids of register rows the agent just changed (hoisted + decayed by
		// the host). A matching row gets a transient wash — animation only.
		changedIds = new Set<string>()
	}: { runActive?: boolean; reloadKey?: number; changedIds?: Set<string> } = $props();

	let systems = $state<AiSystemRead[] | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);

	const LIFECYCLE_LABELS: Record<string, string> = {
		in_development: 'In development',
		in_service: 'In service',
		decommissioned: 'Decommissioned'
	};
	const ORIGIN_LABELS: Record<string, string> = {
		in_house: 'In-house',
		third_party: 'Third-party',
		hybrid: 'Hybrid'
	};
	function lifecycleLabel(v: string): string {
		return LIFECYCLE_LABELS[v] ?? v;
	}
	function originLabel(v: string): string {
		return ORIGIN_LABELS[v] ?? v;
	}

	// --- Live-update machinery (mirrors RopaRegister.svelte verbatim) ----------
	// Out-of-order guard: a slow fetch must not clobber a fresher one (the live poll
	// and the settle-reconcile can overlap).
	let loadGeneration = 0;
	// Timer-chain ownership guard: bumped on every stop so a tick from a superseded
	// chain refuses to re-arm — one live poll loop at a time.
	let pollGeneration = 0;
	let pollTimer: ReturnType<typeof setTimeout> | null = null;
	let destroyed = false;

	/**
	 * Re-read the register. `quiet` = a live refresh (poll tick or settle reconcile):
	 * keep the current rows on screen — never flip back to the skeleton, and never
	 * blank to an error on a transient blip. The first mount load is loud.
	 */
	async function load(quiet = false) {
		const gen = ++loadGeneration;
		if (!quiet) {
			loading = true;
			error = null;
		}
		try {
			const rows = await listAiSystems();
			if (gen !== loadGeneration) return; // superseded by a newer load
			systems = rows;
			if (!quiet) error = null;
		} catch (e) {
			if (gen !== loadGeneration) return;
			if (!quiet)
				error = e instanceof Error ? e.message : 'Failed to load the AI-systems register.';
		} finally {
			if (!quiet) loading = false;
		}
	}

	function schedulePoll(gen: number) {
		pollTimer = setTimeout(() => {
			void pollTick(gen);
		}, POLL_INTERVAL_MS);
	}

	async function pollTick(gen: number) {
		if (gen !== pollGeneration) return; // chain superseded before this fired
		await load(true);
		if (destroyed || !runActive || gen !== pollGeneration) return;
		schedulePoll(gen);
	}

	function stopPoll() {
		pollGeneration += 1; // retire the current chain
		if (pollTimer !== null) {
			clearTimeout(pollTimer);
			pollTimer = null;
		}
	}

	onMount(() => {
		void load();
	});

	onDestroy(() => {
		destroyed = true;
		stopPoll();
	});

	// Start/stop the live poll as the run starts/ends.
	$effect(() => {
		if (!runActive) return;
		const gen = pollGeneration;
		schedulePoll(gen);
		return () => stopPoll();
	});

	// Settle reconcile: when the host bumps reloadKey (a run just settled), pull once
	// more so the final write lands even if it raced the last poll tick.
	// svelte-ignore state_referenced_locally
	let lastReloadKey = reloadKey;
	$effect(() => {
		if (reloadKey === lastReloadKey) return;
		lastReloadKey = reloadKey;
		void load(true);
	});
</script>

<PageShell size="narrow" data-testid="lq-ai-systems-register">
	<SectionHeader
		size="page"
		title="AI systems"
		subtitle="The company register of AI systems under the EU AI Act — maintained by the AI Compliance agent, owned by you. The agent records the facts; the risk tier is a determination for the classification engine."
	/>

	<div class="mt-4" in:fade={{ duration: motionMs(MOTION.fast) }}>
		{#if loading}
			<p class="text-sm text-muted-foreground">Loading the register…</p>
		{:else if error}
			<p class="text-sm text-destructive">{error}</p>
		{:else if (systems?.length ?? 0) === 0}
			<p class="max-w-prose text-sm text-muted-foreground">
				No AI systems recorded yet. Ask the agent to register a system and it will appear here as it
				is recorded.
			</p>
		{:else}
			<div class="rounded-lg border border-border">
				<Table>
					<TableHeader>
						<TableRow>
							<TableHead>Name</TableHead>
							<TableHead>Intended purpose</TableHead>
							<TableHead>Lifecycle</TableHead>
							<TableHead>Origin</TableHead>
							<TableHead>GPAI</TableHead>
						</TableRow>
					</TableHeader>
					<TableBody>
						{#each systems ?? [] as s (s.id)}
							<TableRow
								class="lq-reg-row{changedIds.has(s.id) ? ' lq-row-changed' : ''}"
								data-testid="lq-ai-system-row"
							>
								<TableCell class="font-medium text-foreground">{s.name}</TableCell>
								<TableCell class="max-w-md text-muted-foreground">
									<span class="line-clamp-2">{s.intended_purpose}</span>
								</TableCell>
								<TableCell>
									<Badge variant="secondary">{lifecycleLabel(s.lifecycle_status)}</Badge>
								</TableCell>
								<TableCell class="text-muted-foreground">
									{originLabel(s.development_origin)}
								</TableCell>
								<TableCell>
									{#if s.gpai_systemic}
										<Badge variant="destructive">Systemic GPAI</Badge>
									{:else if s.is_gpai}
										<Badge variant="outline">GPAI</Badge>
									{:else}
										<span class="text-muted-foreground">—</span>
									{/if}
								</TableCell>
							</TableRow>
						{/each}
					</TableBody>
				</Table>
			</div>
		{/if}
	</div>
</PageShell>

<style>
	/* AIC-1 (ADR-F024): a row the agent just changed gets a brief green wash (the
	   "just written" intent), then fades — mirrors RopaRegister's wash. :global
	   because shadcn TableRow renders the <tr> outside this scope. Reduced-motion →
	   the wash applies and clears instantly. */
	:global(tr.lq-reg-row) {
		transition: background-color 600ms ease-out;
	}
	:global(tr.lq-reg-row.lq-row-changed) {
		background-color: var(--color-status-completed-wash);
	}
	@media (prefers-reduced-motion: reduce) {
		:global(tr.lq-reg-row) {
			transition: none;
		}
	}
</style>
