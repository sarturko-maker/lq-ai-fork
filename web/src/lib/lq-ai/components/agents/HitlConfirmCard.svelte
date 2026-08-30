<script module lang="ts">
	/**
	 * The cockpit confirm card (HITL-3, ADR-F071): when a run pauses on a
	 * stop-and-ask policy it settles `awaiting_input` with a `hitl_request` step
	 * whose `name` is the gated tool and `summary` is a bounded JSON digest of
	 * the gated call(s). This card renders that SETTLED step (ADR-F004 — durable
	 * truth, survives reload / no live stream) and offers the lawyer the verbs the
	 * SERVER said this pause admits: Approve and Refuse everywhere, plus — for a
	 * `draft_email_reply` (INTAKE-4b, ADR-F087) — reading the draft, rewriting it
	 * in place, and "Respond", which is a reject carrying a note the agent
	 * redrafts from. Every choice drives `resumeRun` up in the parent.
	 *
	 * The digest is untrusted model/tool output, so parsing is DEFENSIVE (mirrors
	 * `subagentTypeOf` in helpers) and every value renders as ESCAPED text — never
	 * markdown/HTML. Pure logic lives here in the module script so vitest exercises
	 * it without a DOM (the RefusalMessageBubble pattern; NO @testing-library/svelte).
	 */

	import type { EditedEmailReplyArgs, ResumeDecision } from '$lib/lq-ai/api/agents';

	/** One gated tool call awaiting a human go-ahead. */
	export interface HitlAction {
		tool: string;
		args: Record<string, unknown>;
		/**
		 * The verbs the SERVER will accept for this call (INTAKE-4b, ADR-F087).
		 * Empty when the pause predates F087 or the digest didn't carry them — the
		 * card then offers approve/refuse only, which the server always accepts.
		 */
		allowedDecisions: string[];
	}

	/** The tool whose arguments a lawyer may rewrite (mirrors api `EDITABLE_TOOL_NAMES`). */
	export const EDITABLE_TOOL = 'draft_email_reply';

	/**
	 * The email draft the card renders. `to` is CONTEXT, never an input: the
	 * mail-bridge is reply-only (it derives recipients from the message being
	 * answered and is never handed an address — ADR-F086), so a recipient editor
	 * would be a control that does nothing. Subject and body are the artefact.
	 */
	export interface DraftFields {
		readonly to: string;
		subject: string;
		body: string;
	}

	/**
	 * Parse the `hitl_request` step's bounded digest into its gated calls. The
	 * runner writes `json.dumps([{tool, args, allowed_decisions}, …], sort_keys=True)`
	 * (api/app/agents/runner.py). DEFENSIVE: a missing / non-JSON / truncated /
	 * odd-shaped summary yields `[]`, so the card degrades to the step's `name`
	 * (approve/refuse only) rather than throwing on untrusted input.
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
							: {},
					allowedDecisions: Array.isArray(rec.allowed_decisions)
						? (rec.allowed_decisions as unknown[]).filter(
								(d): d is string => typeof d === 'string'
							)
						: []
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

	// ---------------------------------------------------------------------
	// INTAKE-4b (ADR-F087): the email-reply review surface.
	//
	// A pause is "editable" only when it is exactly ONE `draft_email_reply`
	// call AND the server said `edit` is allowed for it. Both halves matter: a
	// single decision is fanned across every gated call in the turn, so
	// offering an editor for one of several calls would silently apply one
	// draft's text to all of them; and the verbs come from the server, so the
	// card can never offer a button the resume endpoint would 422.
	// ---------------------------------------------------------------------

	/** The one editable email draft in this pause, or `null`. */
	export function editableDraft(actions: HitlAction[]): DraftFields | null {
		if (actions.length !== 1) return null;
		const action = actions[0];
		if (action.tool !== EDITABLE_TOOL) return null;
		if (!action.allowedDecisions.includes('edit')) return null;
		const to = action.args.to;
		return {
			to: Array.isArray(to)
				? to.filter((a): a is string => typeof a === 'string').join(', ')
				: typeof to === 'string'
					? to
					: '',
			subject: typeof action.args.subject === 'string' ? action.args.subject : '',
			body: typeof action.args.body === 'string' ? action.args.body : ''
		};
	}

	/**
	 * The decision the "Approve & send" button sends: a plain `approve` when the
	 * lawyer changed nothing (the checkpointed call runs untouched — no edit
	 * round-trip, no re-validation surface), otherwise an `edit` carrying ONLY
	 * the fields that actually differ, so an untouched field keeps the agent's
	 * original value server-side.
	 */
	export function approvalDecision(original: DraftFields, edited: DraftFields): ResumeDecision {
		const changed: Partial<EditedEmailReplyArgs> = {};
		if (edited.subject.trim() !== original.subject.trim()) changed.subject = edited.subject.trim();
		if (edited.body !== original.body) changed.body = edited.body;
		if (Object.keys(changed).length === 0) return { type: 'approve' };
		// `body` is required on the wire even when only the subject moved.
		return { type: 'edit', edited_args: { ...changed, body: edited.body } };
	}

	/**
	 * Is this draft sendable as it stands? The server rejects an empty subject or
	 * body with a 422 the lawyer cannot read; catching it here keeps "Approve &
	 * send" honestly disabled instead of failing after the click. NOT a validation
	 * layer — the server still decides (reject-don't-sanitize); this is only the
	 * case a human can obviously see.
	 */
	export function isSendable(draft: DraftFields | null): boolean {
		return !!draft && draft.subject.trim().length > 0 && draft.body.trim().length > 0;
	}

	/**
	 * "Respond" = reject + message (ADR-F087): the note reaches the model as this
	 * tool's result and it redrafts. An empty note is a plain refusal, never a
	 * reject carrying an empty string — and the button that sends one is disabled
	 * (:func:`canRespond`), so an empty note is never how a lawyer lands there.
	 */
	export function canRespond(message: string): boolean {
		return message.trim().length > 0;
	}

	export function respondDecision(message: string): ResumeDecision {
		const trimmed = message.trim();
		return trimmed ? { type: 'reject', message: trimmed } : { type: 'reject' };
	}
</script>

<script lang="ts">
	import HandIcon from '@lucide/svelte/icons/hand';
	import type { AgentRunStep } from '$lib/lq-ai/api/agents';

	let {
		step,
		pending = false,
		error = null,
		onDecide
	}: {
		step: AgentRunStep;
		/** A resume round-trip is in flight — every button disables. */
		pending?: boolean;
		/** Last resume attempt's error, shown inline (never blocks re-trying). */
		error?: string | null;
		/** Send one decision to POST /runs/{id}/resume. */
		onDecide: (decision: ResumeDecision) => void;
	} = $props();

	const actions = $derived(parseHitlActions(step.summary));
	const tools = $derived(hitlToolNames(actions, step.name));
	const askLine = $derived(hitlAskLine(tools));
	// INTAKE-4b (ADR-F087): non-null only for a single editable email draft.
	const draft = $derived(editableDraft(actions));

	let editing = $state(false);
	let responding = $state(false);
	let responseText = $state('');
	/** The lawyer's in-progress rewrite; empty until they press Edit. */
	let overrides = $state<{ subject?: string; body?: string }>({});

	/** What the card SHOWS: the agent's draft with the lawyer's edits laid over it. */
	const shown = $derived(
		draft
			? {
					to: draft.to,
					subject: overrides.subject ?? draft.subject,
					body: overrides.body ?? draft.body
				}
			: null
	);

	// A redraft after "Respond" replaces this card with a NEW step. Drop the
	// working copy when that happens: carrying it over would let the lawyer
	// approve text they last read against a DIFFERENT draft.
	$effect(() => {
		step.id;
		overrides = {};
		editing = false;
		responding = false;
		responseText = '';
	});

	function startEditing(): void {
		if (!shown) return;
		// Seed from what is on screen, so the inputs open with the draft in them.
		overrides = { subject: shown.subject, body: shown.body };
		editing = true;
	}
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

	{#if shown}
		<!-- INTAKE-4b (ADR-F087): the email-reply review surface. The lawyer reads
		     the draft, optionally rewrites it in place, and approves — what they
		     approve is what is sent. Read-only until they press Edit, so the
		     default gesture stays "read, then decide". -->
		<div class="ag-hitl__draft" data-testid="lq-ai-agents-hitl-draft">
			<!-- Context, never an input, and labelled for what it actually is: the
			     agent's STATED addressee. The reply is delivered back on the original
			     email thread and the mail service derives the real recipient from the
			     message being answered (ADR-F086/F087) — so this line must not read
			     as "we will send it here". -->
			<div class="ag-hitl__field">
				<span class="lq-text-caption">The agent addressed this to</span>
				<span class="lq-text-body-sm ag-hitl__value" data-testid="lq-ai-agents-hitl-to">
					{shown.to}
				</span>
				<span class="lq-text-caption ag-hitl__hint">
					Sent as a reply on the original email thread.
				</span>
			</div>
			<label class="ag-hitl__field">
				<span class="lq-text-caption">Subject</span>
				{#if editing}
					<input
						class="ag-hitl__input"
						type="text"
						bind:value={overrides.subject}
						disabled={pending}
						data-testid="lq-ai-agents-hitl-subject"
					/>
				{:else}
					<span class="lq-text-body-sm ag-hitl__value">{shown.subject}</span>
				{/if}
			</label>
			<label class="ag-hitl__field">
				<span class="lq-text-caption">Message</span>
				{#if editing}
					<textarea
						class="ag-hitl__input ag-hitl__textarea"
						rows="8"
						bind:value={overrides.body}
						disabled={pending}
						data-testid="lq-ai-agents-hitl-body"
					></textarea>
				{:else}
					<span class="lq-text-body-sm ag-hitl__value ag-hitl__value--body">{shown.body}</span>
				{/if}
			</label>
			<button
				type="button"
				class="ag-hitl__link"
				disabled={pending}
				data-testid="lq-ai-agents-hitl-edit-toggle"
				onclick={() => (editing ? (editing = false) : startEditing())}
			>
				{editing ? 'Done editing' : 'Edit'}
			</button>
		</div>
	{/if}

	<ul class="ag-hitl__actions" class:ag-hitl__actions--quiet={!!draft}>
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

	{#if responding}
		<!-- "Respond" is a reject carrying the lawyer's note (ADR-F087): the agent
		     sees it as this tool's result and writes a new draft. -->
		<div class="ag-hitl__respond">
			<label class="ag-hitl__field">
				<span class="lq-text-caption">Tell the agent what to change</span>
				<textarea
					class="ag-hitl__input ag-hitl__textarea"
					rows="3"
					maxlength="2000"
					bind:value={responseText}
					disabled={pending}
					data-testid="lq-ai-agents-hitl-response"
				></textarea>
			</label>
		</div>
	{/if}

	<div class="ag-hitl__buttons">
		{#if draft && shown}
			<button
				type="button"
				class="ag-hitl__btn ag-hitl__btn--approve"
				disabled={pending || responding || !isSendable(shown)}
				data-testid="lq-ai-agents-hitl-approve"
				onclick={() => draft && shown && onDecide(approvalDecision(draft, shown))}
			>
				{pending ? 'Sending…' : 'Approve & send'}
			</button>
			{#if responding}
				<button
					type="button"
					class="ag-hitl__btn ag-hitl__btn--refuse"
					disabled={pending || !canRespond(responseText)}
					data-testid="lq-ai-agents-hitl-respond-send"
					onclick={() => onDecide(respondDecision(responseText))}
				>
					Send back to the agent
				</button>
			{:else}
				<button
					type="button"
					class="ag-hitl__btn ag-hitl__btn--refuse"
					disabled={pending}
					data-testid="lq-ai-agents-hitl-respond"
					onclick={() => (responding = true)}
				>
					Respond
				</button>
			{/if}
			<button
				type="button"
				class="ag-hitl__btn ag-hitl__btn--refuse"
				disabled={pending}
				data-testid="lq-ai-agents-hitl-refuse"
				onclick={() => onDecide({ type: 'reject' })}
			>
				Refuse
			</button>
		{:else}
			<button
				type="button"
				class="ag-hitl__btn ag-hitl__btn--approve"
				disabled={pending}
				data-testid="lq-ai-agents-hitl-approve"
				onclick={() => onDecide({ type: 'approve' })}
			>
				{pending ? 'Sending…' : 'Approve'}
			</button>
			<button
				type="button"
				class="ag-hitl__btn ag-hitl__btn--refuse"
				disabled={pending}
				data-testid="lq-ai-agents-hitl-refuse"
				onclick={() => onDecide({ type: 'reject' })}
			>
				Refuse
			</button>
		{/if}
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

	/* INTAKE-4b (ADR-F087): the draft under review. Card-on-card, one step in,
	   so the reply reads as the artefact and the tool digest below it as detail. */
	.ag-hitl__draft,
	.ag-hitl__respond {
		display: flex;
		flex-direction: column;
		gap: var(--lq-space-2);
		background: var(--color-card);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		padding: var(--lq-space-3);
	}

	.ag-hitl__field {
		display: flex;
		flex-direction: column;
		gap: var(--lq-space-1);
		min-width: 0;
	}

	.ag-hitl__field > span:first-child,
	.ag-hitl__hint {
		color: var(--color-muted-foreground);
	}

	.ag-hitl__value {
		color: var(--color-foreground);
		overflow-wrap: anywhere;
	}

	.ag-hitl__value--body {
		white-space: pre-wrap;
	}

	.ag-hitl__input {
		width: 100%;
		font: inherit;
		color: var(--color-foreground);
		background: var(--color-background);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		padding: var(--lq-space-1) var(--lq-space-2);
	}

	.ag-hitl__input:focus-visible {
		outline: 2px solid var(--color-status-attention);
		outline-offset: 1px;
	}

	.ag-hitl__textarea {
		resize: vertical;
		min-height: 4rem;
	}

	.ag-hitl__link {
		align-self: flex-start;
		background: none;
		border: none;
		padding: 0;
		font-size: 13px;
		color: var(--color-muted-foreground);
		text-decoration: underline;
		cursor: pointer;
	}

	.ag-hitl__link:disabled {
		opacity: 0.6;
		cursor: default;
	}

	/* With the draft rendered above, the raw tool digest is secondary detail. */
	.ag-hitl__actions--quiet {
		opacity: 0.75;
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
