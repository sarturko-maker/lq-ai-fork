<script module lang="ts">
	/**
	 * Pure, unit-tested helpers for the matter-memory panel (C3c-2). The codebase
	 * has no @testing-library/svelte, so behaviour is tested at the helper layer
	 * (pattern: AttachKBModal / MatterCard) and the template is glue.
	 */

	/** Human label for an append-only log entry's `kind`. */
	export function logKindLabel(kind: string): string {
		switch (kind) {
			case 'wiki_snapshot':
				return 'Summary revision';
			case 'fact':
				return 'Fact';
			case 'correction':
				return 'Pinned correction';
			case 'consolidation':
				return 'Consolidation';
			default:
				return kind.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
		}
	}

	/** Only wiki snapshots are revertable (their `id` is the revert target). */
	export function isRevertable(entry: { kind: string }): boolean {
		return entry.kind === 'wiki_snapshot';
	}

	/** Short, stable provenance handle for a run id (first segment), or em-dash. */
	export function shortRunId(runId: string | null): string {
		return runId ? runId.slice(0, 8) : '—';
	}

	/** Footer note when the log is tail-capped (server returns the recent slice). */
	export function logTailNote(shown: number, total: number): string {
		return total > shown ? `Showing the ${shown} most recent of ${total} entries.` : '';
	}

	/**
	 * A human may write to the tier (pin / correct / retire / revert) only when no run is
	 * mid-write — don't race the agent's own memory writes. (ADR-F042: the human owns the
	 * tier, but never mid-flight.)
	 */
	export function canWrite(runActive: boolean): boolean {
		return !runActive;
	}

	/** Revert is one such write; a named alias keeps the existing revert call sites clear. */
	export const canRevert = canWrite;

	/** Boundary cap on a pinned correction — mirrors the API (CORRECTION_MAX_CHARS). */
	export const CORRECTION_MAX_CHARS = 4_000;

	/** A correction is submittable when it's non-empty and within the body cap (after trim). */
	export function isPinSubmittable(text: string): boolean {
		const t = text.trim();
		return t.length >= 1 && t.length <= CORRECTION_MAX_CHARS;
	}

	/**
	 * Seed the pin composer when correcting a specific fact: quote a short, single-line
	 * excerpt of the fact so the pinned correction reads as a reply (`Re: "…" →`). The
	 * lawyer types the correction after the stub; it's still stored as an ordinary pinned
	 * correction (no in-place edit of the fact — ADR-F042 B2 no-overwrite).
	 */
	export function factCorrectionPrefill(factBody: string): string {
		const oneLine = factBody.replace(/\s+/g, ' ').trim();
		const MAX = 80;
		const excerpt = oneLine.length > MAX ? oneLine.slice(0, MAX).trimEnd() + '…' : oneLine;
		return `Re: "${excerpt}" → `;
	}

	// --- Authorship roster (ADR-F048) ------------------------------------------------

	/** The sides a participant can be on — mirrors the backend enum (MatterParticipantSide). */
	export const PARTICIPANT_SIDES = ['ours', 'counterparty', 'unknown'] as const;

	/** Human label for a participant's `side` (the badge text). */
	export function sideLabel(side: string): string {
		switch (side) {
			case 'ours':
				return 'Ours';
			case 'counterparty':
				return 'Counterparty';
			case 'unknown':
				return 'Unknown';
			default:
				return side;
		}
	}

	/** Tailwind classes for the side badge — brand for ours, amber for counterparty, muted else. */
	export function sideToneClass(side: string): string {
		switch (side) {
			case 'ours':
				return 'border-brand/20 bg-brand/10 text-brand';
			case 'counterparty':
				return 'border-amber-500/20 bg-amber-500/10 text-amber-600 dark:text-amber-400';
			default:
				return 'border-border bg-muted text-muted-foreground';
		}
	}

	/** Whether a roster entry is the lawyer's confirmed record (vs the agent's inference). */
	export function participantTrustLabel(trust: string): string {
		return trust === 'confirmed' ? 'Confirmed' : 'Inferred';
	}

	/** Split the aliases textarea (comma- or newline-separated) into a clean, deduped list. */
	export function parseAliases(text: string): string[] {
		const out: string[] = [];
		const seen = new Set<string>();
		for (const raw of text.split(/[\n,]/)) {
			const item = raw.trim();
			if (!item) continue;
			const key = item.toLowerCase();
			if (seen.has(key)) continue;
			seen.add(key);
			out.push(item);
		}
		return out;
	}

	/** A participant is submittable when it has a name and a valid side (after trim). */
	export function isParticipantSubmittable(name: string, side: string): boolean {
		return name.trim().length >= 1 && (PARTICIPANT_SIDES as readonly string[]).includes(side);
	}
</script>

<script lang="ts">
	/**
	 * Matter-memory panel (C3c-2, ADR-F042 / F044) — a read-only window onto one
	 * matter's working-memory tier (the auto-written wiki, the live typed fact
	 * ledger, the lawyer's pinned corrections, and the append-only activity log),
	 * plus a human-authenticated wiki revert behind a confirm step.
	 *
	 * Every `*_md` / `body_preview` is MODEL-authored (untrusted) — rendered only
	 * through `renderModelMarkdown` (DOMPurify, media-forbid), never raw `{@html}`.
	 * The agent has no revert tool; restore is a human action and is disabled
	 * while a run is active so it can't race an in-flight write.
	 *
	 * Loading / live-poll / settle-reconcile mirror RopaRegister (PRIV-9a): a loud
	 * first load, a quiet poll while `runActive`, and a quiet reconcile when the
	 * host bumps `reloadKey` on settle.
	 */
	import { onDestroy, onMount, tick } from 'svelte';
	import { fade } from 'svelte/transition';
	import PinIcon from '@lucide/svelte/icons/pin';

	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Dialog from '$lib/components/ui/dialog/index.js';
	import { Separator } from '$lib/components/ui/separator/index.js';
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';
	import PageShell from '$lib/lq-ai/components/primitives/PageShell.svelte';
	import SectionHeader from '$lib/lq-ai/components/primitives/SectionHeader.svelte';
	import { renderModelMarkdown } from '$lib/lq-ai/sanitize-markdown';
	import { POLL_INTERVAL_MS } from '$lib/lq-ai/agents/helpers';
	import { MOTION, motionMs, timeAgo } from '$lib/lq-ai/cockpit/helpers';
	import {
		readMatterMemory,
		revertWiki,
		pinCorrection,
		retireCorrection,
		retireFact,
		createParticipant,
		updateParticipant,
		retireParticipant
	} from '$lib/lq-ai/api/matterMemory';
	import { LQAIApiError } from '$lib/lq-ai/api/client';
	import type {
		MatterFactRead,
		MatterLogEntryRead,
		MatterMemoryRead,
		MatterParticipantRead
	} from '$lib/lq-ai/types';

	let {
		projectId,
		// True while the matter's agent is working — drives the live poll and
		// disables revert (the host relays it from the conversation's run state).
		runActive = false,
		// Bumped by the host when a run settles — one reconcile fetch so the final
		// write is never missed even if the last poll tick raced it.
		reloadKey = 0,
		nowMs
	}: { projectId: string; runActive?: boolean; reloadKey?: number; nowMs: number } = $props();

	let memory = $state<MatterMemoryRead | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);

	// Revert confirm flow (human-authenticated; the agent has no revert tool).
	let revertOpen = $state(false);
	let revertTarget = $state<MatterLogEntryRead | null>(null);
	let reverting = $state(false);
	let revertError = $state<string | null>(null);

	// C3-UM — pin composer: the human pins a correction the agent must defer to. Shared
	// by the section-header "+ Pin a correction" button and the per-fact "Correct" action.
	let composerOpen = $state(false);
	let composerText = $state('');
	let pinning = $state(false);
	let pinError = $state<string | null>(null);
	let composerTextareaEl = $state<HTMLTextAreaElement | null>(null);

	// C3-UM — retire confirm: soft-retire a pinned correction, a fact's window, or
	// (ADR-F048) a roster participant.
	type RetireTarget = { kind: 'correction' | 'fact' | 'participant'; id: string };
	let retireOpen = $state(false);
	let retireTarget = $state<RetireTarget | null>(null);
	let retiring = $state(false);
	let retireError = $state<string | null>(null);

	// ADR-F048 — authorship-roster add/edit form (the lawyer owns the who-is-who).
	let participantFormOpen = $state(false);
	let editingParticipantId = $state<string | null>(null);
	let pName = $state('');
	let pSide = $state<string>('ours');
	let pRole = $state('');
	let pOrg = $state('');
	let pAliasesText = $state('');
	let savingParticipant = $state(false);
	let participantError = $state<string | null>(null);
	let pNameEl = $state<HTMLInputElement | null>(null);

	const allEmpty = $derived(
		memory !== null &&
			memory.wiki.content_md.trim() === '' &&
			memory.facts.length === 0 &&
			memory.corrections.length === 0 &&
			memory.roster.length === 0 &&
			memory.log.length === 0
	);

	// Out-of-order guard: a slow fetch must not clobber a fresher one (the live
	// poll and the settle reconcile can overlap — mirrors RopaRegister).
	let loadGeneration = 0;
	let pollGeneration = 0;
	let pollTimer: ReturnType<typeof setTimeout> | null = null;
	let destroyed = false;

	/**
	 * Re-read the whole memory projection. `quiet` = a live refresh (poll tick or
	 * settle reconcile): keep the current view on screen, never flip to the
	 * skeleton, never blank to an error on a transient blip. The first mount load
	 * is loud (shows the skeleton, surfaces a hard error).
	 */
	async function load(quiet = false) {
		const gen = ++loadGeneration;
		if (!quiet) {
			loading = true;
			error = null;
		}
		try {
			const data = await readMatterMemory(projectId);
			if (gen !== loadGeneration) return; // superseded by a newer load
			memory = data;
			if (!quiet) error = null;
		} catch (e) {
			if (gen !== loadGeneration) return;
			if (!quiet) {
				error = e instanceof LQAIApiError ? e.message : 'Failed to load this matter’s memory.';
			}
		} finally {
			if (!quiet) loading = false;
		}
	}

	// PRIV-9a live update — poll while a run is active, self-rescheduling so
	// requests can't pile up; `gen` threads chain identity so a superseded tick
	// never re-arms.
	function schedulePoll(gen: number) {
		pollTimer = setTimeout(() => {
			void pollTick(gen);
		}, POLL_INTERVAL_MS);
	}

	async function pollTick(gen: number) {
		if (gen !== pollGeneration) return;
		await load(true);
		if (destroyed || !runActive || gen !== pollGeneration) return;
		schedulePoll(gen);
	}

	function stopPoll() {
		pollGeneration += 1;
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

	// Settle reconcile: when the host bumps reloadKey (a run just settled), pull
	// once more so the final write lands even if it raced the last poll tick.
	// svelte-ignore state_referenced_locally
	let lastReloadKey = reloadKey;
	$effect(() => {
		if (reloadKey === lastReloadKey) return;
		lastReloadKey = reloadKey;
		void load(true);
	});

	// Clear the dialog's target + error whenever it closes (Cancel, Esc, overlay,
	// or success) so a reopen never shows a stale target. `confirmRevert` captures
	// the id synchronously before its await, so this can't disturb an in-flight POST.
	$effect(() => {
		if (!revertOpen) {
			revertTarget = null;
			revertError = null;
		}
	});

	function askRevert(entry: MatterLogEntryRead) {
		revertTarget = entry;
		revertError = null;
		revertOpen = true;
	}

	async function confirmRevert() {
		if (!revertTarget) return;
		reverting = true;
		revertError = null;
		try {
			await revertWiki(projectId, revertTarget.id);
			revertOpen = false;
			revertTarget = null;
			await load(true); // refetch so the restored wiki + new snapshot appear
		} catch (e) {
			revertError = e instanceof LQAIApiError ? e.message : 'Could not restore — try again.';
		} finally {
			reverting = false;
		}
	}

	/** Absolute date for a fact's effective ("as of") instant; relative is wrong here. */
	function asOfDate(iso: string | null): string {
		if (!iso) return '';
		const t = Date.parse(iso);
		return Number.isNaN(t) ? '' : new Date(t).toLocaleDateString();
	}

	// --- C3-UM: the three human "update memory" gestures ---------------------------

	/** Open the pin composer (preserves any draft) and focus the textarea. */
	function openComposer() {
		pinError = null;
		composerOpen = true;
		void tick().then(() => composerTextareaEl?.focus());
	}

	/** Cancel = discard: close the composer and drop the draft + any error. */
	function closeComposer() {
		composerOpen = false;
		composerText = '';
		pinError = null;
	}

	/** Correct a specific fact: seed the composer with a "Re: '…' →" stub, focus + reveal it. */
	function correctFact(fact: MatterFactRead) {
		composerText = factCorrectionPrefill(fact.body_md);
		pinError = null;
		composerOpen = true;
		void tick().then(() => {
			composerTextareaEl?.scrollIntoView({ block: 'center', behavior: 'smooth' });
			composerTextareaEl?.focus();
			// Caret at the end, so the lawyer types after the stub.
			composerTextareaEl?.setSelectionRange(composerText.length, composerText.length);
		});
	}

	async function submitPin() {
		if (!isPinSubmittable(composerText) || !canWrite(runActive)) return;
		pinning = true;
		pinError = null;
		try {
			await pinCorrection(projectId, composerText.trim());
			composerText = '';
			composerOpen = false;
			await load(true); // refetch so the new pin appears
		} catch (e) {
			pinError = e instanceof LQAIApiError ? e.message : 'Could not pin — try again.';
		} finally {
			pinning = false;
		}
	}

	function askRetire(target: RetireTarget) {
		retireTarget = target;
		retireError = null;
		retireOpen = true;
	}

	async function confirmRetire() {
		if (!retireTarget) return;
		const target = retireTarget; // capture before await (the close effect clears state)
		retiring = true;
		retireError = null;
		try {
			if (target.kind === 'correction') {
				await retireCorrection(projectId, target.id);
			} else if (target.kind === 'participant') {
				await retireParticipant(projectId, target.id);
			} else {
				await retireFact(projectId, target.id);
			}
			retireOpen = false;
			retireTarget = null;
			await load(true); // refetch so the retired entry drops off the live lists
		} catch (e) {
			retireError = e instanceof LQAIApiError ? e.message : 'Could not retire — try again.';
		} finally {
			retiring = false;
		}
	}

	// --- ADR-F048: the authorship-roster add / edit / remove gestures ----------------

	function resetParticipantForm() {
		editingParticipantId = null;
		pName = '';
		pSide = 'ours';
		pRole = '';
		pOrg = '';
		pAliasesText = '';
		participantError = null;
	}

	/** Open the add-participant form (blank) and focus the name field. */
	function openAddParticipant() {
		resetParticipantForm();
		participantFormOpen = true;
		void tick().then(() => pNameEl?.focus());
	}

	/** Open the form pre-filled to edit an existing participant. */
	function openEditParticipant(p: MatterParticipantRead) {
		editingParticipantId = p.id;
		pName = p.display_name;
		pSide = p.side;
		pRole = p.role_label ?? '';
		pOrg = p.organization ?? '';
		pAliasesText = (p.aliases ?? []).join(', ');
		participantError = null;
		participantFormOpen = true;
		void tick().then(() => pNameEl?.focus());
	}

	/** Cancel = discard the form draft. */
	function closeParticipantForm() {
		participantFormOpen = false;
		resetParticipantForm();
	}

	async function submitParticipant() {
		if (!isParticipantSubmittable(pName, pSide) || !canWrite(runActive)) return;
		savingParticipant = true;
		participantError = null;
		const body = {
			display_name: pName.trim(),
			side: pSide,
			role_label: pRole.trim() || null,
			organization: pOrg.trim() || null,
			aliases: parseAliases(pAliasesText),
			source_citation: null
		};
		try {
			if (editingParticipantId) {
				await updateParticipant(projectId, editingParticipantId, body);
			} else {
				await createParticipant(projectId, body);
			}
			participantFormOpen = false;
			resetParticipantForm();
			await load(true); // refetch so the new/edited participant appears
		} catch (e) {
			participantError =
				e instanceof LQAIApiError ? e.message : 'Could not save the participant — try again.';
		} finally {
			savingParticipant = false;
		}
	}

	// Clear the retire dialog's target + error on close (Cancel, Esc, overlay, or success)
	// so a reopen never shows a stale target. `confirmRetire` captures the target before
	// its await, so this can't disturb an in-flight POST.
	$effect(() => {
		if (!retireOpen) {
			retireTarget = null;
			retireError = null;
		}
	});
</script>

{#snippet md(text: string)}
	<!-- Untrusted, model-authored markdown → sanitised, media-free HTML. -->
	<div class="prose prose-sm max-w-none dark:prose-invert">
		<!-- eslint-disable-next-line svelte/no-at-html-tags — renderModelMarkdown-sanitized (DOMPurify, media-forbid) -->
		{@html renderModelMarkdown(text)}
	</div>
{/snippet}

{#snippet pinComposer()}
	<!-- The human pins a correction the agent must treat as ground truth (ADR-F042). The
	     body is the lawyer's own text; the server caps + validates it, the read surface
	     renders it through renderModelMarkdown. -->
	<div
		class="mt-3 rounded-lg border border-border bg-card p-3 text-left"
		data-testid="lq-memory-composer"
	>
		<textarea
			bind:this={composerTextareaEl}
			bind:value={composerText}
			rows="3"
			maxlength={CORRECTION_MAX_CHARS}
			placeholder="Pin a correction the agent must treat as ground truth — e.g. “We act for the seller, not the buyer.”"
			class="w-full resize-y rounded-md border border-input bg-background p-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
			data-testid="lq-memory-composer-input"
		></textarea>
		{#if pinError}
			<p class="mt-1.5 text-sm text-destructive" data-testid="lq-memory-pin-error">{pinError}</p>
		{/if}
		<div class="mt-2 flex items-center justify-between gap-3">
			<span class="text-xs text-muted-foreground tabular-nums">
				{composerText.trim().length.toLocaleString()}/{CORRECTION_MAX_CHARS.toLocaleString()}
			</span>
			<div class="flex items-center gap-2">
				<Button type="button" variant="ghost" size="sm" onclick={closeComposer}>Cancel</Button>
				<Button
					type="button"
					size="sm"
					disabled={!isPinSubmittable(composerText) || !canWrite(runActive) || pinning}
					data-testid="lq-memory-pin-submit"
					onclick={submitPin}
				>
					{pinning ? 'Pinning…' : 'Pin correction'}
				</Button>
			</div>
		</div>
	</div>
{/snippet}

{#snippet participantForm()}
	<!-- ADR-F048: the lawyer adds/edits a who-is-who participant. A human write is
	     stored trust='confirmed' (the agent can no longer override its side/role). -->
	<div
		class="mt-3 rounded-lg border border-border bg-card p-3 text-left"
		data-testid="lq-roster-form"
	>
		<div class="grid gap-3 sm:grid-cols-2">
			<label class="block text-xs font-medium text-muted-foreground">
				Name
				<input
					bind:this={pNameEl}
					bind:value={pName}
					type="text"
					maxlength="200"
					placeholder="e.g. Jane Smith"
					class="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
					data-testid="lq-roster-name"
				/>
			</label>
			<label class="block text-xs font-medium text-muted-foreground">
				Side
				<select
					bind:value={pSide}
					class="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
					data-testid="lq-roster-side"
				>
					{#each PARTICIPANT_SIDES as s (s)}
						<option value={s}>{sideLabel(s)}</option>
					{/each}
				</select>
			</label>
			<label class="block text-xs font-medium text-muted-foreground">
				Role <span class="font-normal">(optional)</span>
				<input
					bind:value={pRole}
					type="text"
					maxlength="200"
					placeholder="e.g. Lead counsel"
					class="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
					data-testid="lq-roster-role"
				/>
			</label>
			<label class="block text-xs font-medium text-muted-foreground">
				Organisation <span class="font-normal">(optional)</span>
				<input
					bind:value={pOrg}
					type="text"
					maxlength="200"
					placeholder="e.g. Acme LLP"
					class="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
					data-testid="lq-roster-org"
				/>
			</label>
		</div>
		<label class="mt-3 block text-xs font-medium text-muted-foreground">
			Also known as <span class="font-normal"
				>(the names/emails they write under, comma-separated)</span
			>
			<textarea
				bind:value={pAliasesText}
				rows="2"
				placeholder="e.g. J. Smith, jsmith@acme.com"
				class="mt-1 w-full resize-y rounded-md border border-input bg-background p-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
				data-testid="lq-roster-aliases"
			></textarea>
		</label>
		{#if participantError}
			<p class="mt-1.5 text-sm text-destructive" data-testid="lq-roster-error">
				{participantError}
			</p>
		{/if}
		<div class="mt-2 flex items-center justify-end gap-2">
			<Button type="button" variant="ghost" size="sm" onclick={closeParticipantForm}>Cancel</Button>
			<Button
				type="button"
				size="sm"
				disabled={!isParticipantSubmittable(pName, pSide) ||
					!canWrite(runActive) ||
					savingParticipant}
				data-testid="lq-roster-submit"
				onclick={submitParticipant}
			>
				{savingParticipant ? 'Saving…' : editingParticipantId ? 'Save' : 'Add participant'}
			</Button>
		</div>
	</div>
{/snippet}

<PageShell size="default" data-testid="lq-matter-memory">
	<div class="flex items-start justify-between gap-3">
		<SectionHeader
			size="page"
			title="Memory"
			subtitle="What this matter has learned — maintained by the agent, owned by you."
		/>
		{#if runActive}
			<span
				class="mt-1 inline-flex shrink-0 items-center gap-1.5 text-xs font-medium text-muted-foreground"
				data-testid="lq-memory-live"
			>
				<span class="size-1.5 animate-pulse rounded-full bg-brand" aria-hidden="true"></span>
				Updating live…
			</span>
		{/if}
	</div>

	<div class="mt-5" in:fade={{ duration: motionMs(MOTION.fast) }}>
		{#if loading}
			<div class="space-y-3" data-testid="lq-memory-loading" aria-hidden="true">
				<Skeleton class="h-24 w-full rounded-lg" />
				<Skeleton class="h-4 w-2/3" />
				<Skeleton class="h-4 w-1/2" />
			</div>
		{:else if error}
			<p class="text-sm text-destructive" data-testid="lq-memory-error">{error}</p>
		{:else if memory}
			{#if allEmpty}
				<div
					class="rounded-lg border border-dashed border-border px-6 py-10 text-center"
					data-testid="lq-memory-empty"
				>
					<p class="text-sm font-medium text-foreground">No memory yet</p>
					<p class="mx-auto mt-1 max-w-prose text-sm text-muted-foreground">
						As the agent works this matter it records a working summary, typed facts, and the
						corrections you pin — they’ll appear here.
					</p>
					<div class="mx-auto mt-4 max-w-prose">
						{#if composerOpen}
							{@render pinComposer()}
						{:else}
							<Button
								type="button"
								variant="outline"
								size="sm"
								disabled={!canWrite(runActive)}
								title={canWrite(runActive)
									? 'Pin a correction'
									: 'Paused while the agent is working'}
								data-testid="lq-memory-pin-open-empty"
								onclick={openComposer}
							>
								+ Pin a correction
							</Button>
						{/if}
					</div>
				</div>
			{:else}
				<!-- Working summary (the auto-written wiki) -->
				<section data-testid="lq-memory-wiki">
					<div class="flex items-baseline justify-between gap-3">
						<SectionHeader size="section" title="Working summary" />
						<span class="shrink-0 text-xs text-muted-foreground tabular-nums">
							{memory.wiki.char_count.toLocaleString()} chars
							{#if memory.wiki.version_count > 0}
								· {memory.wiki.version_count}
								prior {memory.wiki.version_count === 1 ? 'version' : 'versions'}
							{/if}
						</span>
					</div>
					<div class="mt-2 rounded-lg border border-border bg-card p-4">
						{#if memory.wiki.content_md.trim()}
							{@render md(memory.wiki.content_md)}
						{:else}
							<p class="text-sm text-muted-foreground">
								The agent hasn’t written a summary for this matter yet.
							</p>
						{/if}
					</div>
				</section>

				<Separator class="my-6" />

				<!-- Authorship roster (ADR-F048): who is who on the matter -->
				<section data-testid="lq-memory-roster">
					<div class="flex items-center justify-between gap-3">
						<SectionHeader size="section" title="Participants ({memory.roster.length})" />
						{#if !(participantFormOpen && editingParticipantId === null)}
							<Button
								type="button"
								variant="outline"
								size="sm"
								class="shrink-0"
								disabled={!canWrite(runActive)}
								title={canWrite(runActive)
									? 'Add a participant'
									: 'Paused while the agent is working'}
								data-testid="lq-roster-add"
								onclick={openAddParticipant}
							>
								+ Add participant
							</Button>
						{/if}
					</div>
					{#if participantFormOpen && editingParticipantId === null}
						{@render participantForm()}
					{/if}
					{#if memory.roster.length === 0}
						<p class="mt-2 text-sm text-muted-foreground">
							No participants recorded yet. The agent adds who it learns (from emails, documents and
							what you tell it); add or correct them here.
						</p>
					{:else}
						<ul class="mt-2 space-y-3">
							{#each memory.roster as p (p.id)}
								<li class="rounded-lg border border-border bg-card p-3">
									{#if participantFormOpen && editingParticipantId === p.id}
										{@render participantForm()}
									{:else}
										<div class="flex items-start justify-between gap-2">
											<div class="min-w-0">
												<div class="flex flex-wrap items-center gap-2">
													<span class="font-medium text-foreground">{p.display_name}</span>
													<Badge variant="outline" class={sideToneClass(p.side)}>
														{sideLabel(p.side)}
													</Badge>
													{#if p.trust === 'confirmed'}
														<span class="text-label text-brand uppercase">
															{participantTrustLabel(p.trust)}
														</span>
													{/if}
												</div>
												{#if p.role_label || p.organization}
													<p class="mt-0.5 text-xs text-muted-foreground">
														{[p.role_label, p.organization].filter(Boolean).join(' · ')}
													</p>
												{/if}
												{#if p.aliases.length}
													<p class="mt-0.5 text-xs text-muted-foreground">
														writes as: {p.aliases.join(', ')}
													</p>
												{/if}
											</div>
											<div class="flex shrink-0 items-center gap-1">
												<Button
													type="button"
													variant="ghost"
													size="sm"
													class="h-auto px-2 py-0.5 text-xs text-muted-foreground hover:text-foreground"
													disabled={!canWrite(runActive)}
													title={canWrite(runActive)
														? 'Edit this participant'
														: 'Paused while the agent is working'}
													data-testid="lq-roster-edit"
													onclick={() => openEditParticipant(p)}
												>
													Edit
												</Button>
												<Button
													type="button"
													variant="ghost"
													size="sm"
													class="h-auto px-2 py-0.5 text-xs text-muted-foreground hover:text-foreground"
													disabled={!canWrite(runActive)}
													title={canWrite(runActive)
														? 'Remove this participant'
														: 'Paused while the agent is working'}
													data-testid="lq-roster-remove"
													onclick={() => askRetire({ kind: 'participant', id: p.id })}
												>
													Remove
												</Button>
											</div>
										</div>
									{/if}
								</li>
							{/each}
						</ul>
					{/if}
				</section>

				<Separator class="my-6" />

				<!-- Live typed facts (the current ledger; superseded excluded) -->
				<section data-testid="lq-memory-facts">
					<SectionHeader size="section" title="Facts ({memory.facts.length})" />
					{#if memory.facts.length === 0}
						<p class="mt-2 text-sm text-muted-foreground">No facts recorded yet.</p>
					{:else}
						<ul class="mt-2 space-y-3">
							{#each memory.facts as f (f.id)}
								<li class="rounded-lg border border-border bg-card p-3">
									<div class="mb-1.5 flex items-start justify-between gap-2">
										<div>
											{#if f.fact_type}
												<Badge variant="secondary">{f.fact_type}</Badge>
											{/if}
										</div>
										<div class="flex shrink-0 items-center gap-1">
											<Button
												type="button"
												variant="ghost"
												size="sm"
												class="h-auto px-2 py-0.5 text-xs text-muted-foreground hover:text-foreground"
												disabled={!canWrite(runActive)}
												title={canWrite(runActive)
													? 'Pin a correction to this fact'
													: 'Paused while the agent is working'}
												data-testid="lq-memory-fact-correct"
												onclick={() => correctFact(f)}
											>
												Correct
											</Button>
											<Button
												type="button"
												variant="ghost"
												size="sm"
												class="h-auto px-2 py-0.5 text-xs text-muted-foreground hover:text-foreground"
												disabled={!canWrite(runActive)}
												title={canWrite(runActive)
													? 'Close this fact’s validity window'
													: 'Paused while the agent is working'}
												data-testid="lq-memory-fact-retire"
												onclick={() => askRetire({ kind: 'fact', id: f.id })}
											>
												Retire
											</Button>
										</div>
									</div>
									{@render md(f.body_md)}
									<p class="mt-1.5 text-xs text-muted-foreground">
										{#if f.source_citation}<span class="italic">{f.source_citation}</span> ·{/if}
										{#if asOfDate(f.valid_at)}as of {asOfDate(f.valid_at)} ·{/if}
										{f.author ?? 'agent'} · {timeAgo(f.created_at, nowMs)}
									</p>
								</li>
							{/each}
						</ul>
					{/if}
				</section>

				<Separator class="my-6" />

				<!-- Pinned corrections (the lawyer's enforced record) -->
				<section data-testid="lq-memory-corrections">
					<div class="flex items-center justify-between gap-3">
						<SectionHeader
							size="section"
							title="Pinned corrections ({memory.corrections.length})"
						/>
						{#if !composerOpen}
							<Button
								type="button"
								variant="outline"
								size="sm"
								class="shrink-0"
								disabled={!canWrite(runActive)}
								title={canWrite(runActive)
									? 'Pin a correction'
									: 'Paused while the agent is working'}
								data-testid="lq-memory-pin-open"
								onclick={openComposer}
							>
								+ Pin a correction
							</Button>
						{/if}
					</div>
					{#if composerOpen}
						{@render pinComposer()}
					{/if}
					{#if memory.corrections.length === 0}
						<p class="mt-2 text-sm text-muted-foreground">
							No corrections pinned. Pin one to override what the agent believes.
						</p>
					{:else}
						<ul class="mt-2 space-y-3">
							{#each memory.corrections as c (c.id)}
								{@const pinned = c.trust === 'human-pinned'}
								<!-- Human-pinned correction: the ONE scarce-blue accent (F013) — a 2px
								     brand rail + brand Pin icon mark the lawyer's enforced truth that the
								     agent must defer to; body stays monochrome. -->
								<li
									class="rounded-lg border border-border bg-card p-3 {pinned
										? 'border-l-2 border-l-brand'
										: ''}"
								>
									<div class="mb-1.5 flex items-center justify-between gap-2">
										<div
											class="flex items-center gap-1.5 {pinned
												? 'text-brand'
												: 'text-muted-foreground'}"
										>
											<PinIcon class="size-3.5" aria-hidden="true" />
											<span class="text-label uppercase">{pinned ? 'Pinned' : c.trust}</span>
										</div>
										<Button
											type="button"
											variant="ghost"
											size="sm"
											class="h-auto shrink-0 px-2 py-0.5 text-xs text-muted-foreground hover:text-foreground"
											disabled={!canWrite(runActive)}
											title={canWrite(runActive)
												? 'Retire this correction'
												: 'Paused while the agent is working'}
											data-testid="lq-memory-correction-retire"
											onclick={() => askRetire({ kind: 'correction', id: c.id })}
										>
											Retire
										</Button>
									</div>
									{@render md(c.body_md)}
									<p class="mt-1.5 text-xs text-muted-foreground">{timeAgo(c.created_at, nowMs)}</p>
								</li>
							{/each}
						</ul>
					{/if}
				</section>

				<Separator class="my-6" />

				<!-- Append-only activity log (revert offered on snapshot rows) -->
				<section data-testid="lq-memory-log">
					<SectionHeader size="section" title="Activity ({memory.log_total})" />
					{#if memory.log.length === 0}
						<p class="mt-2 text-sm text-muted-foreground">No activity yet.</p>
					{:else}
						<ul class="mt-2 space-y-2">
							{#each memory.log as e (e.id)}
								<li
									class="rounded-lg border border-border bg-card p-3 {e.superseded
										? 'opacity-60'
										: ''}"
								>
									<div class="flex items-center justify-between gap-3">
										<div class="flex min-w-0 items-center gap-2 text-xs">
											<span class="font-medium text-foreground">{logKindLabel(e.kind)}</span>
											{#if e.superseded}
												<Badge variant="outline" class="font-normal">superseded</Badge>
											{/if}
											<span class="truncate text-muted-foreground">
												{e.author ?? 'agent'} · {shortRunId(e.run_id)} · {timeAgo(
													e.created_at,
													nowMs
												)}
											</span>
										</div>
										{#if isRevertable(e)}
											<Button
												type="button"
												variant="outline"
												size="sm"
												class="shrink-0"
												disabled={!canRevert(runActive)}
												title={canRevert(runActive)
													? 'Restore the summary to this version'
													: 'Paused while the agent is working'}
												data-testid="lq-memory-restore"
												onclick={() => askRevert(e)}
											>
												Restore this version
											</Button>
										{/if}
									</div>
									{#if e.body_preview.trim()}
										<div class="mt-2">{@render md(e.body_preview)}</div>
									{/if}
								</li>
							{/each}
						</ul>
						{#if logTailNote(memory.log.length, memory.log_total)}
							<p class="mt-2 text-xs text-muted-foreground tabular-nums">
								{logTailNote(memory.log.length, memory.log_total)}
							</p>
						{/if}
					{/if}
				</section>
			{/if}
		{/if}
	</div>
</PageShell>

<!-- Revert confirm: a material, human-owned write — reversible (current state is
     snapshotted first) but it changes what the agent treats as current memory. -->
<Dialog.Root bind:open={revertOpen}>
	<Dialog.Content class="shadow-lg sm:max-w-md">
		<Dialog.Header>
			<Dialog.Title>Restore this version?</Dialog.Title>
			<Dialog.Description>
				{#if revertTarget}
					Restore the working summary to the version from {timeAgo(revertTarget.created_at, nowMs)}
					({shortRunId(revertTarget.run_id)}). Your current summary is snapshotted first, so this is
					reversible — nothing is deleted.
				{/if}
			</Dialog.Description>
		</Dialog.Header>
		{#if revertError}
			<p class="text-sm text-destructive" data-testid="lq-memory-revert-error">{revertError}</p>
		{/if}
		<Dialog.Footer class="mt-2">
			<Button type="button" variant="outline" onclick={() => (revertOpen = false)}>Cancel</Button>
			<Button
				type="button"
				disabled={reverting}
				data-testid="lq-memory-revert-confirm"
				onclick={confirmRevert}
			>
				{reverting ? 'Restoring…' : 'Restore version'}
			</Button>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>

<!-- Retire confirm (C3-UM): a soft, append-only retire — the correction/fact drops off
     the live lists but stays in the activity log. Disabled-during-run is enforced on the
     trigger buttons, not here. -->
<Dialog.Root bind:open={retireOpen}>
	<Dialog.Content class="shadow-lg sm:max-w-md">
		<Dialog.Header>
			<Dialog.Title>
				{#if retireTarget?.kind === 'fact'}
					Retire this fact?
				{:else if retireTarget?.kind === 'participant'}
					Remove this participant?
				{:else}
					Retire this correction?
				{/if}
			</Dialog.Title>
			<Dialog.Description>
				{#if retireTarget?.kind === 'fact'}
					This closes the fact’s validity window so the agent stops treating it as current. Nothing
					is deleted — it stays in the activity log, marked superseded.
				{:else if retireTarget?.kind === 'participant'}
					This removes the person from the matter’s roster, so the agent no longer matches their
					edits to a side. Nothing is deleted; you can add them again later.
				{:else}
					This stops the correction from overriding what the agent believes. Nothing is deleted — it
					stays in the activity log, marked superseded.
				{/if}
			</Dialog.Description>
		</Dialog.Header>
		{#if retireError}
			<p class="text-sm text-destructive" data-testid="lq-memory-retire-error">{retireError}</p>
		{/if}
		<Dialog.Footer class="mt-2">
			<Button type="button" variant="outline" onclick={() => (retireOpen = false)}>Cancel</Button>
			<Button
				type="button"
				disabled={retiring}
				data-testid="lq-memory-retire-confirm"
				onclick={confirmRetire}
			>
				{#if retireTarget?.kind === 'participant'}
					{retiring ? 'Removing…' : 'Remove'}
				{:else}
					{retiring ? 'Retiring…' : 'Retire'}
				{/if}
			</Button>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>
