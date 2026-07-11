<script module lang="ts">
	/**
	 * Pure, unit-tested helpers for the matter Documents panel (C7a, ADR-F046).
	 * The codebase has no @testing-library/svelte, so behaviour is tested at the
	 * helper layer (pattern: MemoryPanel / MatterCard) and the template is glue.
	 */
	import type { MatterFile } from '$lib/lq-ai/types';
	// Single source of truth for the redline-output check (ADR-F047 dedup).
	import { isRedlineOutput } from '$lib/lq-ai/api/editor';

	/** Human-readable file size (1024-based), e.g. 2048 → "2.0 KB", 0 → "0 B". */
	export function formatBytes(bytes: number): string {
		if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
		const units = ['B', 'KB', 'MB', 'GB'];
		const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
		const value = bytes / 1024 ** i;
		return `${i === 0 ? value : value.toFixed(1)} ${units[i]}`;
	}

	/**
	 * Short badge label for a file's origin, or null for a plain human upload:
	 * "Redline" for a redline output, else "Agent output" for any agent-produced
	 * file (`created_by_run_id` set), else nothing.
	 */
	export function fileOriginBadge(
		file: Pick<MatterFile, 'filename' | 'created_by_run_id'>
	): string | null {
		if (isRedlineOutput(file.filename)) return 'Redline';
		if (file.created_by_run_id) return 'Agent output';
		return null;
	}

	/** True while a run is mid-flight — the live "Updating…" indicator + poll driver. */
	export function isUpdatingLive(runActive: boolean): boolean {
		return runActive;
	}
</script>

<script lang="ts">
	/**
	 * Matter Documents panel (C7a, ADR-F046) — a read-only list of one matter's
	 * files (uploads + the agent's redline outputs) with a per-row download that
	 * streams the bytes from `GET /files/{id}/content`. The redlined `.docx` work
	 * product was persisted + audited but never surfaced before; this is its home.
	 *
	 * Loading / live-poll / settle-reconcile mirror MemoryPanel (RopaRegister
	 * lineage): a loud first load, a quiet poll while `runActive` (a redline that
	 * just finished appears without a manual refresh), and a quiet reconcile when
	 * the host bumps `reloadKey` on settle. Filenames are plain text (not markdown)
	 * — rendered as text, never `{@html}`.
	 */
	import { onDestroy, onMount } from 'svelte';
	import { fade } from 'svelte/transition';
	import DownloadIcon from '@lucide/svelte/icons/download';
	import FileTextIcon from '@lucide/svelte/icons/file-text';
	import PencilIcon from '@lucide/svelte/icons/pencil';

	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';
	import PageShell from '$lib/lq-ai/components/primitives/PageShell.svelte';
	import SectionHeader from '$lib/lq-ai/components/primitives/SectionHeader.svelte';
	import { POLL_INTERVAL_MS } from '$lib/lq-ai/agents/helpers';
	import { MOTION, motionMs, timeAgo } from '$lib/lq-ai/cockpit/helpers';
	import { listMatterFiles } from '$lib/lq-ai/api/matterFiles';
	import { downloadFile } from '$lib/lq-ai/api/files';
	import { isEditableDocx } from '$lib/lq-ai/api/editor';
	import { LQAIApiError } from '$lib/lq-ai/api/client';
	// `MatterFile` is imported in `<script module>` above (Svelte merges both script
	// blocks into one module, so a second import here would be a duplicate identifier).

	let {
		projectId,
		// True while the matter's agent is working — drives the live poll so a
		// just-produced redline appears without a manual refresh.
		runActive = false,
		// Bumped by the host when a run settles — one reconcile fetch so a final
		// output is never missed even if the last poll tick raced it.
		reloadKey = 0,
		nowMs,
		// Open a .docx in the in-app Word editor (ADR-F047). Absent → no editor
		// affordance (the panel still downloads).
		onOpenEditor
	}: {
		projectId: string;
		runActive?: boolean;
		reloadKey?: number;
		nowMs: number;
		onOpenEditor?: (fileId: string, filename: string) => void;
	} = $props();

	let files = $state<MatterFile[] | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);

	// Per-row download state: the id currently downloading + a transient error
	// (a file deleted out from under the list, a network blip).
	let downloadingId = $state<string | null>(null);
	let downloadError = $state<string | null>(null);

	// Out-of-order guard: a slow fetch must not clobber a fresher one (poll + settle
	// reconcile can overlap — mirrors MemoryPanel / RopaRegister).
	let loadGeneration = 0;
	let pollGeneration = 0;
	let pollTimer: ReturnType<typeof setTimeout> | null = null;
	let destroyed = false;

	async function load(quiet = false) {
		const gen = ++loadGeneration;
		if (!quiet) {
			loading = true;
			error = null;
		}
		try {
			const data = await listMatterFiles(projectId);
			if (gen !== loadGeneration) return; // superseded by a newer load
			files = data.files;
			if (!quiet) error = null;
		} catch (e) {
			if (gen !== loadGeneration) return;
			if (!quiet) {
				error = e instanceof LQAIApiError ? e.message : 'Failed to load this matter’s documents.';
			}
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

	// Settle reconcile: when the host bumps reloadKey (a run just settled), pull once
	// more so a final output lands even if it raced the last poll tick.
	// svelte-ignore state_referenced_locally
	let lastReloadKey = reloadKey;
	$effect(() => {
		if (reloadKey === lastReloadKey) return;
		lastReloadKey = reloadKey;
		void load(true);
	});

	async function download(file: MatterFile) {
		if (downloadingId) return; // one at a time
		downloadingId = file.id;
		downloadError = null;
		try {
			await downloadFile(file.id, file.filename);
		} catch (e) {
			downloadError =
				e instanceof LQAIApiError ? e.message : 'Could not download — it may have been removed.';
		} finally {
			downloadingId = null;
		}
	}
</script>

<PageShell size="default" data-testid="lq-matter-documents">
	<div class="flex items-start justify-between gap-3">
		<SectionHeader
			size="page"
			title="Documents"
			subtitle="This matter’s files — uploads and the agent’s redline outputs. Download to review."
		/>
		{#if isUpdatingLive(runActive)}
			<span
				class="mt-1 inline-flex shrink-0 items-center gap-1.5 text-xs font-medium text-muted-foreground"
				data-testid="lq-documents-live"
			>
				<span class="size-1.5 animate-pulse rounded-full bg-brand" aria-hidden="true"></span>
				Updating live…
			</span>
		{/if}
	</div>

	<div class="mt-5" in:fade={{ duration: motionMs(MOTION.fast) }}>
		{#if loading}
			<div class="space-y-3" data-testid="lq-documents-loading" aria-hidden="true">
				<Skeleton class="h-14 w-full rounded-lg" />
				<Skeleton class="h-14 w-full rounded-lg" />
				<Skeleton class="h-14 w-2/3 rounded-lg" />
			</div>
		{:else if error}
			<p class="text-sm text-destructive" data-testid="lq-documents-error">{error}</p>
		{:else if files}
			{#if downloadError}
				<p class="mb-3 text-sm text-destructive" data-testid="lq-documents-download-error">
					{downloadError}
				</p>
			{/if}
			{#if files.length === 0}
				<div
					class="rounded-lg border border-dashed border-border px-6 py-10 text-center"
					data-testid="lq-documents-empty"
				>
					<p class="text-sm font-medium text-foreground">No documents yet</p>
					<p class="mx-auto mt-1 max-w-prose text-sm text-muted-foreground">
						Upload a contract to this matter, or ask the agent to redline one — its output will
						appear here to download.
					</p>
				</div>
			{:else}
				<ul class="space-y-2" data-testid="lq-documents-list">
					{#each files as f (f.id)}
						{@const badge = fileOriginBadge(f)}
						<li
							class="flex items-center justify-between gap-3 rounded-lg border border-border bg-card p-3"
							data-testid="lq-documents-row"
						>
							<div class="flex min-w-0 items-center gap-3">
								<FileTextIcon class="size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
								<div class="min-w-0">
									<div class="flex items-center gap-2">
										<!-- filename is plain text (a user/work-product label), never markdown -->
										<span class="truncate text-sm font-medium text-foreground">{f.filename}</span>
										{#if badge}
											<Badge
												variant={badge === 'Redline' ? 'default' : 'secondary'}
												class="shrink-0">{badge}</Badge
											>
										{/if}
									</div>
									<p class="mt-0.5 text-xs text-muted-foreground tabular-nums">
										<!-- updated_at set = bytes mutated in place (ADR-F081) — show the freshest instant -->
										{formatBytes(f.size_bytes)} · {timeAgo(f.updated_at ?? f.created_at, nowMs)}
										{#if f.ingestion_status !== 'ready'}
											· {f.ingestion_status}
										{/if}
									</p>
								</div>
							</div>
							<div class="flex shrink-0 items-center gap-2">
								{#if onOpenEditor && isEditableDocx(f.filename)}
									<Button
										type="button"
										variant="outline"
										size="sm"
										data-testid="lq-documents-edit"
										onclick={() => onOpenEditor?.(f.id, f.filename)}
									>
										<PencilIcon class="size-3.5" aria-hidden="true" />
										Edit
									</Button>
								{/if}
								<Button
									type="button"
									variant="outline"
									size="sm"
									disabled={downloadingId === f.id}
									data-testid="lq-documents-download"
									onclick={() => download(f)}
								>
									<DownloadIcon class="size-3.5" aria-hidden="true" />
									{downloadingId === f.id ? 'Downloading…' : 'Download'}
								</Button>
							</div>
						</li>
					{/each}
				</ul>
			{/if}
		{/if}
	</div>
</PageShell>
