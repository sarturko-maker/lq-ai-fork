<script lang="ts">
	/**
	 * One rendered row of an agent turn's timeline (AE6, ADR-F011): a Vercel AI
	 * Elements "Tool" card (name + Parameters + Result + status) or a reasoning
	 * row. Factored out of ConversationPanel (UX-B-5) so a top-level row and a
	 * subagent-nested child (the delegation boundary) render identically — the
	 * parent component uses legacy `<slot>`, so a `{#snippet}` there is illegal;
	 * a child component is the clean way to share the markup.
	 *
	 * Purely presentational over an already-`visibleSteps`/`groupTurnSteps` row
	 * (ADR-F004): raw args/output stay verbatim in the mono bodies, no per-tool
	 * error is invented (a failed run surfaces via the run-level badge).
	 */
	import ChevronDownIcon from '@lucide/svelte/icons/chevron-down';
	import CircleCheckIcon from '@lucide/svelte/icons/circle-check';
	import LoaderCircleIcon from '@lucide/svelte/icons/loader-circle';
	import WrenchIcon from '@lucide/svelte/icons/wrench';

	import { renderModelMarkdown } from '$lib/lq-ai/sanitize-markdown';
	import { stepDisplay, type TurnRow } from '$lib/lq-ai/agents/helpers';

	let { row, live }: { row: TurnRow; live: boolean } = $props();

	/**
	 * View model for the Tool card: natural-language title from the dispatching
	 * call, the input/output bodies, and a presentational status (running only
	 * while the call has no result yet and the turn is live).
	 */
	function toolView(r: Extract<TurnRow, { kind: 'tool' }>) {
		const titleStep = r.call ?? r.result;
		const title = titleStep ? stepDisplay(titleStep).title : r.name;
		const running = r.result === null && live && r.call !== null;
		return {
			title,
			inputBody: r.call?.summary ?? '',
			outputBody: r.result?.summary ?? '',
			status: running ? ('running' as const) : ('completed' as const),
			statusLabel: running ? 'Running' : 'Completed'
		};
	}
</script>

{#if row.kind === 'tool'}
	{@const t = toolView(row)}
	<details class="ag-tool" data-testid="lq-ai-agents-tool">
		<summary class="ag-tool__header">
			<span class="ag-tool__name">
				<WrenchIcon class="ag-tool__icon size-4" aria-hidden="true" />
				<span class="lq-text-label ag-tool__title">{t.title}</span>
				<span
					class="ag-tool__badge ag-tool__badge--{t.status}"
					data-testid="lq-ai-agents-tool-status"
				>
					{#if t.status === 'running'}
						<LoaderCircleIcon class="size-3.5 ag-tool__spin" aria-hidden="true" />
					{:else}
						<CircleCheckIcon class="size-3.5" aria-hidden="true" />
					{/if}
					{t.statusLabel}
				</span>
			</span>
			<ChevronDownIcon class="ag-tool__chevron size-4" aria-hidden="true" />
		</summary>
		<div class="ag-tool__body">
			{#if t.inputBody}
				<div class="ag-tool__section">
					<h4 class="ag-tool__label">Parameters</h4>
					<pre class="ag-tool__mono">{t.inputBody}</pre>
				</div>
			{/if}
			{#if t.outputBody}
				<div class="ag-tool__section">
					<h4 class="ag-tool__label">Result</h4>
					<pre class="ag-tool__mono">{t.outputBody}</pre>
				</div>
			{/if}
		</div>
	</details>
{:else}
	{@const d = stepDisplay(row.step)}
	<span class="ag-step__title lq-text-label">{d.title}</span>
	{#if d.thinking}
		<details class="ag-thinking">
			<summary class="lq-text-caption">Reasoning</summary>
			<div class="ag-thinking__body prose prose-sm max-w-none">
				<!-- eslint-disable-next-line svelte/no-at-html-tags — renderModelMarkdown-sanitized -->
				{@html renderModelMarkdown(d.thinking)}
			</div>
		</details>
	{/if}
	{#if d.body}
		<p class="lq-text-body-sm ag-step__body">{d.body}</p>
	{/if}
{/if}

<style>
	.ag-step__title {
		color: var(--color-muted-foreground);
		display: block;
	}

	.ag-step__body {
		white-space: pre-wrap;
		overflow-wrap: anywhere;
		margin-top: var(--lq-space-1);
	}

	/* AE Tool card (AE6): bordered collapsible holding one tool's name +
     status + Parameters/Result. Hand-built on <details> (the AE `tool`
     registry item pulls `collapsible` + `badge` + `./code.json`, all dodged
     across the AE series — README § prompt-input / code). */
	.ag-tool {
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
		background: var(--color-card);
		overflow: hidden;
	}

	.ag-tool__header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--lq-space-3);
		padding: var(--lq-space-2) var(--lq-space-3);
		cursor: pointer;
		list-style: none;
		min-width: 0;
	}

	.ag-tool__header::-webkit-details-marker {
		display: none;
	}

	.ag-tool__name {
		display: flex;
		align-items: center;
		gap: var(--lq-space-2);
		min-width: 0;
	}

	.ag-tool__icon {
		color: var(--color-muted-foreground);
		flex: none;
	}

	.ag-tool__title {
		color: var(--color-foreground);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		min-width: 0;
	}

	.ag-tool__badge {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		flex: none;
		border-radius: var(--lq-radius-pill);
		padding: 0 var(--lq-space-2);
		font-size: 11px;
		line-height: 18px;
		white-space: nowrap;
	}

	.ag-tool__badge--completed {
		background: var(--color-status-completed-wash);
		color: var(--color-status-completed);
	}

	.ag-tool__badge--running {
		background: var(--color-status-running-wash);
		color: var(--color-status-running);
	}

	.ag-tool__chevron {
		color: var(--color-muted-foreground);
		flex: none;
		transition: transform 150ms ease-out;
	}

	.ag-tool[open] .ag-tool__chevron {
		transform: rotate(180deg);
	}

	.ag-tool__spin {
		animation: ag-spin 1s linear infinite;
	}

	.ag-tool__body {
		border-top: 1px solid var(--color-border);
		display: flex;
		flex-direction: column;
		gap: var(--lq-space-3);
		padding: var(--lq-space-3);
	}

	.ag-tool__section {
		display: flex;
		flex-direction: column;
		gap: var(--lq-space-1);
	}

	.ag-tool__label {
		font-size: 10px;
		font-weight: 600;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--color-muted-foreground);
		margin: 0;
	}

	.ag-tool__mono {
		font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
		font-size: 12px;
		background: var(--color-muted);
		border-radius: var(--radius-sm);
		padding: var(--lq-space-2);
		white-space: pre-wrap;
		overflow-wrap: anywhere;
		overflow-x: auto;
		margin: 0;
	}

	.ag-thinking summary {
		cursor: pointer;
		color: color-mix(in oklch, var(--color-muted-foreground) 85%, transparent);
	}

	/* Settled reasoning, markdown-rendered (F0-S8) — quieter than the
     answer prose: inset panel, smaller type. */
	.ag-thinking__body {
		background: var(--color-muted);
		border-radius: var(--radius-sm);
		padding: var(--lq-space-2) var(--lq-space-3);
		margin-top: var(--lq-space-1);
		font-size: 13px;
		color: var(--color-muted-foreground);
	}

	@keyframes ag-spin {
		to {
			transform: rotate(360deg);
		}
	}
</style>
