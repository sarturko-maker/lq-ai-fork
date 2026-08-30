<script lang="ts">
	/**
	 * INTAKE-5a — one intake thread, summary first (ADR-F086, plan rulings 2/7/9).
	 *
	 * Ruling 7: the agent has read the whole chain, so the human should not have
	 * to. What opens is the agent's ≤5-bullet account of the thread so far; the
	 * raw email chain sits behind one click (`<details>`), and a thread that never
	 * got a summary shows the chain expanded instead — never an empty page.
	 *
	 * Ruling 2: this surface renders NO approval card. "Open conversation" deep-
	 * links to the conversation where `HitlConfirmCard` already works, so there is
	 * exactly one resume path.
	 *
	 * Ruling 9: bodies are the owner's own mail, shown to the owner, rendered as
	 * plain text with preserved line breaks. There is no `{@html}` on this path —
	 * every subject, address, body, label, note and summary bullet here is
	 * sender- or agent-controlled text.
	 */
	import { onDestroy, onMount } from 'svelte';
	import ArrowLeftIcon from '@lucide/svelte/icons/arrow-left';
	import PaperclipIcon from '@lucide/svelte/icons/paperclip';

	import { Button } from '$lib/components/ui/button/index.js';
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';
	import Alert from '$lib/lq-ai/components/primitives/Alert.svelte';
	import PageShell from '$lib/lq-ai/components/primitives/PageShell.svelte';
	import StatusDot from '$lib/lq-ai/components/primitives/StatusDot.svelte';
	import { timeAgo } from '$lib/lq-ai/cockpit/helpers';
	import { LQAIApiError } from '$lib/lq-ai/api/client';
	import { getIntakeThread, type IntakeThreadDetail } from '$lib/lq-ai/api/intakeThreads';
	import {
		attentionChip,
		authLabel,
		chainSummaryLine,
		matterHref,
		matterRef,
		messageSender,
		outcomeLabel,
		summaryState
	} from './intake-panel-helpers';

	let {
		threadId,
		nowMs,
		onBack,
		onOpenConversation
	}: {
		threadId: string;
		nowMs: number;
		onBack: () => void;
		/** Deep-link into the bound conversation (plan ruling 2). */
		onOpenConversation: (detail: { projectId: string | null; agentThreadId: string }) => void;
	} = $props();

	let data = $state<IntakeThreadDetail | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);

	let loadGeneration = 0;
	let destroyed = false;

	async function load(id: string) {
		const gen = ++loadGeneration;
		loading = true;
		error = null;
		try {
			const detail = await getIntakeThread(id);
			if (gen !== loadGeneration || destroyed) return;
			data = detail;
		} catch (e) {
			if (gen !== loadGeneration || destroyed) return;
			// A thread the caller does not own is a 404, never a 403 — say
			// "not found" rather than hinting that it exists elsewhere.
			error = e instanceof LQAIApiError ? e.message : 'Could not load this thread.';
		} finally {
			if (gen === loadGeneration && !destroyed) loading = false;
		}
	}

	onMount(() => {
		void load(threadId);
	});
	onDestroy(() => {
		destroyed = true;
	});

	// Follow a change of selection without remounting (the list keeps its state).
	// svelte-ignore state_referenced_locally
	let lastThreadId = threadId;
	$effect(() => {
		if (threadId === lastThreadId) return;
		lastThreadId = threadId;
		data = null;
		void load(threadId);
	});

	const thread = $derived(data?.thread ?? null);
	const messages = $derived(data?.messages ?? []);
	const chip = $derived(thread ? attentionChip(thread) : null);
	const summary = $derived(thread ? summaryState(thread) : 'none');
	const chainOpen = $derived(summary === 'none');
	const canOpenConversation = $derived(Boolean(thread?.agent_thread_id));
	const openLabel = $derived(thread?.live_ask ? 'Open conversation · decide' : 'Open conversation');

	function openConversation() {
		if (!thread?.agent_thread_id) return;
		onOpenConversation({
			projectId: thread.project?.id ?? null,
			agentThreadId: thread.agent_thread_id
		});
	}

	let panelWidth = $state(1024);
	const isNarrow = $derived(panelWidth < 700);
</script>

<div bind:clientWidth={panelWidth}>
	<PageShell size="wide" class="space-y-4">
		<button
			type="button"
			class="text-muted-foreground hover:text-foreground focus-visible:ring-ring inline-flex items-center gap-1.5 rounded-md text-xs font-medium transition-colors duration-150 focus-visible:ring-2 focus-visible:outline-none"
			onclick={onBack}
			data-testid="lq-intake-back"
		>
			<ArrowLeftIcon class="size-3.5" aria-hidden="true" /> Inbox
		</button>

		{#if loading}
			<div class="space-y-3" data-testid="lq-intake-loading">
				<Skeleton class="h-7 w-2/3 rounded-md" />
				<Skeleton class="h-32 w-full rounded-lg" />
				<Skeleton class="h-16 w-full rounded-lg" />
			</div>
		{:else if error}
			<Alert intent="error">
				{error}
				<button type="button" class="ml-2 underline" onclick={() => load(threadId)}>Retry</button>
			</Alert>
		{:else if thread && chip}
			<div class="flex flex-wrap items-start justify-between gap-3">
				<h1 class="text-foreground min-w-0 text-xl font-semibold tracking-tight">
					{thread.subject || '(no subject)'}
				</h1>
				<StatusDot status={chip.dot} label={chip.label} class="shrink-0 whitespace-nowrap" />
			</div>

			{#if thread.auth_state === 'fail'}
				<!-- Spoof signal, raised BEFORE the human acts on the email. -->
				<Alert intent="warning">Sender authentication failed. Treat this email with care.</Alert>
			{/if}
			{#if thread.claimed_reference}
				<Alert intent="info">
					This email claims {thread.claimed_reference}.
				</Alert>
			{/if}

			<div class="flex gap-4 {isNarrow ? 'flex-col' : 'items-start'}">
				<div class="min-w-0 flex-1 space-y-4">
					{#if summary !== 'none'}
						<!-- The summary card comes FIRST (ruling 7): the agent read the
						     chain so the lawyer doesn't have to. -->
						<section
							class="border-border bg-card rounded-xl border p-4 shadow-xs"
							data-testid="lq-intake-summary"
						>
							<p class="text-muted-foreground text-[11px] font-semibold tracking-wide uppercase">
								The thread so far · updated {timeAgo(thread.last_inbound_at, nowMs)}
							</p>
							<ul class="mt-3 space-y-2">
								{#each thread.summary as item, i (i)}
									<li class="text-foreground text-sm leading-relaxed">
										<b>{item.title}.</b>
										{item.text}
									</li>
								{/each}
							</ul>
							{#if summary === 'stale'}
								<p class="text-muted-foreground mt-3 text-xs" data-testid="lq-intake-stale">
									Summary not updated — the agent's last run did not finish reading
								</p>
							{/if}
						</section>
					{/if}

					<!-- The chain: collapsed behind one click when there is a summary,
					     expanded when there is none (never an empty page). -->
					<details
						class="border-border bg-card rounded-xl border shadow-xs"
						open={chainOpen}
						data-testid="lq-intake-chain"
					>
						<summary
							class="text-foreground hover:bg-muted/40 focus-visible:ring-ring cursor-pointer rounded-xl px-4 py-3 text-sm font-medium transition-colors duration-150 focus-visible:ring-2 focus-visible:outline-none"
						>
							{chainSummaryLine(messages)}
						</summary>
						<div class="border-border space-y-4 border-t px-4 py-4">
							{#if data?.messages_truncated}
								<Alert intent="info">
									This chain is longer than we show — the newest emails are not listed here.
								</Alert>
							{/if}
							{#each messages as message (message.id)}
								<article
									class="{message.direction === 'out'
										? 'border-brand/40 border-l-2 pl-3'
										: ''} space-y-1.5"
									data-testid="lq-intake-message"
									data-direction={message.direction}
								>
									<header class="flex flex-wrap items-baseline justify-between gap-2">
										<span class="text-foreground text-xs font-medium">
											{messageSender(message, thread.mailbox_address)}
										</span>
										<span class="text-muted-foreground text-[11px] tabular-nums">
											{timeAgo(message.provider_timestamp, nowMs)}
										</span>
									</header>
									{#if message.body_text}
										<p
											class="text-foreground max-w-[68ch] text-sm leading-relaxed whitespace-pre-wrap"
										>
											{message.body_text}
										</p>
									{:else}
										<p class="text-muted-foreground text-sm italic">(no message text)</p>
									{/if}
									{#if message.attachment_filenames.length > 0}
										<ul class="flex flex-wrap gap-2 pt-0.5">
											{#each message.attachment_filenames as filename, i (i)}
												<li
													class="border-border text-muted-foreground inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px]"
												>
													<PaperclipIcon class="size-3" aria-hidden="true" />
													<span class="max-w-[24ch] truncate">{filename}</span>
													{#if message.file_ids[i]}
														<!-- Resolved to a `files` row: it is in this matter's
														     Documents tab. No new download path is added here
														     (plan ruling 9) — the cockpit has no per-file route. -->
														<span class="text-[10px] opacity-70">in Documents</span>
													{/if}
												</li>
											{/each}
										</ul>
									{/if}
									{#if message.send_error}
										<p class="text-destructive text-xs" data-testid="lq-intake-send-error">
											Reply not sent ({message.send_error})
										</p>
									{/if}
								</article>
							{:else}
								<p class="text-muted-foreground text-sm">No emails recorded on this thread yet.</p>
							{/each}
						</div>
					</details>
				</div>

				<!-- "What the agent did" — the receipt, beside the thread. -->
				<aside
					class="border-border bg-card shrink-0 space-y-3 rounded-xl border p-4 shadow-xs {isNarrow
						? 'w-full'
						: 'w-64'}"
					data-testid="lq-intake-receipt"
				>
					<p class="text-muted-foreground text-[11px] font-semibold tracking-wide uppercase">
						What the agent did
					</p>
					<dl class="space-y-2.5 text-xs">
						<div>
							<dt class="text-muted-foreground">Matter</dt>
							<dd class="mt-0.5 font-mono break-all">
								{#if matterHref(thread)}
									<a class="text-brand hover:underline" href={matterHref(thread)}
										>{matterRef(thread)}</a
									>
								{:else}
									<span class="text-muted-foreground">{matterRef(thread)}</span>
								{/if}
							</dd>
						</div>
						<div>
							<dt class="text-muted-foreground">Outcome</dt>
							<dd class="text-foreground mt-0.5">{outcomeLabel(thread.outcome)}</dd>
							{#if thread.outcome_note}
								<dd class="text-muted-foreground mt-0.5 leading-relaxed">{thread.outcome_note}</dd>
							{/if}
						</div>
						{#if thread.label}
							<div>
								<dt class="text-muted-foreground">Label</dt>
								<dd class="text-foreground mt-0.5 break-words">{thread.label}</dd>
							</div>
						{/if}
						<div>
							<dt class="text-muted-foreground">Sender check</dt>
							<dd
								class="mt-0.5 {thread.auth_state === 'fail'
									? 'text-destructive'
									: 'text-foreground'}"
							>
								{authLabel(thread.auth_state)}
							</dd>
						</div>
					</dl>
					<Button
						class="w-full"
						disabled={!canOpenConversation}
						title={canOpenConversation
							? undefined
							: 'This thread has no conversation — nothing to open.'}
						onclick={openConversation}
						data-testid="lq-intake-open-conversation"
					>
						{openLabel}
					</Button>
				</aside>
			</div>
		{/if}
	</PageShell>
</div>
