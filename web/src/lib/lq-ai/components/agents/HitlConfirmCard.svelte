<script module lang="ts">
	/**
	 * The cockpit confirm card (HITL-3, ADR-F071): when a run pauses on a
	 * stop-and-ask policy it settles `awaiting_input` with a `hitl_request` step
	 * whose `name` is the gated tool and `summary` is a bounded JSON digest of
	 * the gated call(s). This card renders that SETTLED step (ADR-F004 — durable
	 * truth, survives reload / no live stream) and offers the lawyer two
	 * first-class choices: Approve (proceed) or Refuse (don't). Both drive
	 * `resumeRun` up in the parent.
	 *
	 * The digest is untrusted model/tool output, so parsing is DEFENSIVE (mirrors
	 * `subagentTypeOf` in helpers) and every value renders as ESCAPED text — never
	 * markdown/HTML. Pure logic lives here in the module script so vitest exercises
	 * it without a DOM (the RefusalMessageBubble pattern; NO @testing-library/svelte).
	 */

	/** One gated tool call awaiting a human go-ahead. */
	export interface HitlAction {
		tool: string;
		args: Record<string, unknown>;
	}

	/**
	 * Parse the `hitl_request` step's bounded digest into its gated calls. The
	 * runner writes `json.dumps([{tool, args}, …], sort_keys=True)`
	 * (api/app/agents/runner.py). DEFENSIVE: a missing / non-JSON / truncated
	 * (over-2000-char) / odd-shaped summary yields `[]`, so the card degrades to
	 * the step's `name` rather than throwing on untrusted input.
	 */
	export function parseHitlActions(summary: string | null): HitlAction[] {
		if (!summary) return [];
		let raw: unknown;
		try {
			raw = JSON.parse(summary);
		} catch {
			return [];
		}
		if (!Array.isArray(raw)) return [];
		const actions: HitlAction[] = [];
		for (const item of raw) {
			if (
				item &&
				typeof item === 'object' &&
				typeof (item as Record<string, unknown>).tool === 'string'
			) {
				const rec = item as Record<string, unknown>;
				actions.push({
					tool: rec.tool as string,
					args:
						rec.args && typeof rec.args === 'object' && !Array.isArray(rec.args)
							? (rec.args as Record<string, unknown>)
							: {}
				});
			}
		}
		return actions;
	}

	/**
	 * The gated tool names to render: the parsed digest, or the step's `name` as
	 * a single-item fallback when the digest didn't parse. Empty only if both are
	 * absent (a malformed pause — the card still shows, asking generically).
	 */
	export function hitlToolNames(actions: HitlAction[], fallbackTool: string | null): string[] {
		if (actions.length) return actions.map((a) => a.tool);
		return fallbackTool ? [fallbackTool] : [];
	}

	/** The plain-language ask line under the title, composed from the tool name(s). */
	export function hitlAskLine(tools: string[]): string {
		if (tools.length === 0) {
			return 'The agent needs your go-ahead before it continues.';
		}
		const verb = tools.length === 1 ? 'run this action' : 'run these actions';
		return `The agent wants to ${verb} and is waiting for your go-ahead.`;
	}

	/** Pretty-print one action's args as escaped JSON for the mono details body. */
	export function formatHitlArgs(args: Record<string, unknown>): string {
		if (!args || Object.keys(args).length === 0) return '';
		try {
			return JSON.stringify(args, null, 2);
		} catch {
			return '';
		}
	}
</script>

<script lang="ts">
	import HandIcon from '@lucide/svelte/icons/hand';
	import type { AgentRunStep } from '$lib/lq-ai/api/agents';

	let {
		step,
		pending = false,
		error = null,
		onApprove,
		onRefuse
	}: {
		step: AgentRunStep;
		/** A resume round-trip is in flight — both buttons disable. */
		pending?: boolean;
		/** Last resume attempt's error, shown inline (never blocks re-trying). */
		error?: string | null;
		onApprove: () => void;
		onRefuse: () => void;
	} = $props();

	const actions = $derived(parseHitlActions(step.summary));
	const tools = $derived(hitlToolNames(actions, step.name));
	const askLine = $derived(hitlAskLine(tools));
</script>

<div
	class="ag-hitl"
	role="group"
	aria-label="Waiting for your go-ahead"
	data-testid="lq-ai-agents-hitl-card"
>
	<div class="ag-hitl__head">
		<HandIcon class="size-4 shrink-0" aria-hidden="true" />
		<span class="lq-text-label ag-hitl__title">Waiting for your go-ahead</span>
	</div>

	<p class="lq-text-body-sm ag-hitl__ask">{askLine}</p>

	<ul class="ag-hitl__actions">
		{#if actions.length > 0}
			{#each actions as action, idx (idx)}
				{@const argsBody = formatHitlArgs(action.args)}
				<li class="ag-hitl__action">
					<code class="ag-hitl__tool">{action.tool}</code>
					{#if argsBody}
						<details class="ag-hitl__args">
							<summary class="lq-text-caption">Details</summary>
							<pre class="ag-hitl__mono">{argsBody}</pre>
						</details>
					{/if}
				</li>
			{/each}
		{:else if step.name}
			<li class="ag-hitl__action">
				<code class="ag-hitl__tool">{step.name}</code>
			</li>
		{/if}
	</ul>

	<div class="ag-hitl__buttons">
		<button
			type="button"
			class="ag-hitl__btn ag-hitl__btn--approve"
			disabled={pending}
			data-testid="lq-ai-agents-hitl-approve"
			onclick={() => onApprove()}
		>
			{pending ? 'Sending…' : 'Approve'}
		</button>
		<button
			type="button"
			class="ag-hitl__btn ag-hitl__btn--refuse"
			disabled={pending}
			data-testid="lq-ai-agents-hitl-refuse"
			onclick={() => onRefuse()}
		>
			Refuse
		</button>
	</div>

	{#if error}
		<p class="lq-text-caption ag-hitl__error" role="alert">{error}</p>
	{/if}
</div>

<style>
	/* HITL-3 (ADR-F071): the stop-and-ask confirm card. Attention (amber) tone —
	   distinct from the running/completed/failed run states — so it reads as "you
	   are needed here". Renders off the settled hitl_request step (ADR-F004); the
	   mount animation is the "the ask just arrived" beat, motion-guarded. */
	.ag-hitl {
		border: 1px solid var(--color-status-attention);
		background: var(--color-status-attention-wash);
		border-radius: var(--radius-md);
		padding: var(--lq-space-3);
		display: flex;
		flex-direction: column;
		gap: var(--lq-space-2);
		margin-top: var(--lq-space-2);
		animation: ag-hitl-in 180ms ease-out;
	}

	.ag-hitl__head {
		display: flex;
		align-items: center;
		gap: var(--lq-space-2);
		/* The lucide icon inherits this as currentColor (stroke) — scoping a class
		   onto the icon COMPONENT doesn't match (svelte can't see the child's DOM),
		   so tint via the parent and let the title override back to foreground. */
		color: var(--color-status-attention);
	}

	.ag-hitl__title {
		color: var(--color-foreground);
	}

	.ag-hitl__ask {
		color: var(--color-foreground);
		margin: 0;
	}

	.ag-hitl__actions {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: var(--lq-space-2);
	}

	.ag-hitl__action {
		display: flex;
		flex-direction: column;
		gap: var(--lq-space-1);
		min-width: 0;
	}

	.ag-hitl__tool {
		align-self: flex-start;
		max-width: 100%;
		font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
		font-size: 12px;
		background: var(--color-card);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		padding: 1px var(--lq-space-2);
		overflow-wrap: anywhere;
	}

	.ag-hitl__args > summary {
		cursor: pointer;
		color: var(--color-muted-foreground);
		width: fit-content;
	}

	.ag-hitl__mono {
		font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
		font-size: 12px;
		background: var(--color-card);
		border-radius: var(--radius-sm);
		padding: var(--lq-space-2);
		white-space: pre-wrap;
		overflow-wrap: anywhere;
		overflow-x: auto;
		margin: var(--lq-space-1) 0 0;
	}

	.ag-hitl__buttons {
		display: flex;
		flex-wrap: wrap;
		gap: var(--lq-space-2);
		margin-top: var(--lq-space-1);
	}

	.ag-hitl__btn {
		border-radius: var(--radius-sm);
		padding: var(--lq-space-1) var(--lq-space-3);
		font-size: 13px;
		font-weight: 500;
		cursor: pointer;
		border: 1px solid transparent;
		transition:
			opacity 120ms ease-out,
			background 120ms ease-out;
	}

	.ag-hitl__btn:disabled {
		opacity: 0.6;
		cursor: default;
	}

	.ag-hitl__btn:focus-visible {
		outline: 2px solid var(--color-status-attention);
		outline-offset: 2px;
	}

	/* Approve — the house filled primary (charcoal on light, inverted on dark). */
	.ag-hitl__btn--approve {
		background: var(--color-foreground);
		color: var(--color-background);
	}

	.ag-hitl__btn--approve:hover:not(:disabled) {
		opacity: 0.9;
	}

	/* Refuse — a first-class decision, so a clear outline button (not a faint
	   link): deliberately declining, distinct from Stop/Cancel elsewhere. */
	.ag-hitl__btn--refuse {
		background: var(--color-card);
		border-color: var(--color-border);
		color: var(--color-foreground);
	}

	.ag-hitl__btn--refuse:hover:not(:disabled) {
		background: var(--color-muted);
	}

	.ag-hitl__error {
		color: var(--color-status-failed);
		margin: 0;
	}

	@keyframes ag-hitl-in {
		from {
			opacity: 0;
			transform: translateY(4px);
		}
		to {
			opacity: 1;
			transform: none;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.ag-hitl {
			animation: none;
		}
	}
</style>
