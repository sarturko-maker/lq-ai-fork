<script lang="ts">
	/**
	 * Single message bubble.
	 *
	 * - Assistant content renders as Markdown (M1: client-side via `marked`,
	 *   sanitised with `DOMPurify`; both already deps of the OpenWebUI fork).
	 * - Applied-skills chips on assistant messages.
	 * - Tier badge on assistant messages.
	 * - error_code surfaces as a red-line banner (per Task C8 spec).
	 * - Citations: when the array is non-empty, render a count summary;
	 *   when empty, render nothing (the citation engine lands in a future
	 *   release — until then we don't telegraph a roadmap to users).
	 * - Wave D.1 T15: when `message.kind === 'refusal'` the bubble dispatches
	 *   to `RefusalMessageBubble` and forwards the rerun / override /
	 *   explainer callbacks; the default rendering below is skipped.
	 */
	import { captureAffordanceInline } from '$lib/lq-ai/preferences/capture-affordance';
	import { citationsApi, LQAIApiError } from '$lib/lq-ai/api';
	import { decorateCitationsInline } from '$lib/lq-ai/citations/decorate-inline';
	import { enhanceCodeBlocks } from '$lib/lq-ai/code/enhance';
	import { splitThink } from '$lib/lq-ai/agents/helpers';
	import { renderModelMarkdown } from '$lib/lq-ai/sanitize-markdown';

	import type { Citation, Message } from '../types';
	import AppliedSkillsChip from './AppliedSkillsChip.svelte';
	import CaptureSkillModal from './CaptureSkillModal.svelte';
	import EnhancedDiffModal from './EnhancedDiffModal.svelte';
	import M2Citations from './M2Citations.svelte';
	import MessageActionsBar from './MessageActionsBar.svelte';
	import MessageSources from './MessageSources.svelte';
	import MessageOverflowMenu from './MessageOverflowMenu.svelte';
	import ProvenancePill from './ProvenancePill.svelte';
	import RefusalMessageBubble from './RefusalMessageBubble.svelte';
	import TierBadge from './TierBadge.svelte';
	import TierDetailsPanel from './TierDetailsPanel.svelte';
	import Alert from './primitives/Alert.svelte';
	import ReasoningRibbon from './primitives/ReasoningRibbon.svelte';
	// AE1 (ADR-F011): the AI Elements message identity — full-width assistant
	// (document-style Response = our sanitized prose) + soft right-aligned user
	// bubble. Message/MessageContent are pure layout primitives; all the
	// functional plumbing below (ribbon, citations, tier, skills, capture,
	// overflow, refusal, error) is unchanged.
	// Aliased to `AeMessage` — `Message` is already the message *type* from `../types`.
	import {
		Message as AeMessage,
		MessageContent
	} from '$lib/lq-ai/components/ai-elements/message/index.js';

	export let message: Message;
	export let isStreaming: boolean = false;
	export let onAppliedSkillClicked: ((name: string) => void) | undefined = undefined;

	// AE2 (ADR-F011) — Retry re-runs the prompt that produced this assistant
	// message through the normal send path (ChatPanel owns the re-dispatch). The
	// Copy / Copy-sources actions are self-contained in MessageActionsBar.
	// No-op default so historical/standalone renders keep working.
	export let onRetry: (msg: Message) => void = () => {};

	// Wave D.1 T20 follow-on — the original prompt the operator typed
	// before clicking "Use enhanced" on the EnhancePromptExpansion panel.
	// Session scope (in-memory, not persisted server-side); undefined when
	// this is a historical message from a prior session. The ✨ pill is
	// still rendered when `message.is_enhanced` is true even if the
	// original is missing — the modal then shows a "not preserved"
	// fallback so the operator gets the right transparency signal.
	export let originalEnhancedPrompt: string | undefined = undefined;

	// Wave D.1 T15 — refusal-bubble plumbing. Defaults are no-ops so the
	// chat surface keeps working when the parent doesn't wire these (e.g.
	// historical chats with no refusal rows). ChatPanel owns the modal +
	// re-run state; this component only forwards the per-message callback.
	export let currentUserRole: 'admin' | 'member' | 'viewer' | 'operator' = 'member';
	export let onRefusalRerun: (msg: Message) => void = () => {};
	export let onRefusalOverrideRequested: (msg: Message) => void = () => {};
	export let onRefusalExplainerRequested: (msg: Message) => void = () => {};

	// D2: tier badge opens a click-for-details panel surfacing the
	// resolved provider/model + token usage. Per PRD §1.3 the user
	// can always answer "what just ran?" from the message they
	// received. State stays local to this bubble so multiple open
	// panels are not possible (the modal is exclusive).
	let tierDetailsOpen = false;

	// Wave D.1 T20 follow-on — ✨ enhanced pill state. Per-message-local
	// so the diff modal is exclusive: clicking the pill on one message
	// does not surface another message's diff.
	let enhancedDiffOpen = false;

	// Wave D.2 Task 5.3 — capture-as-skill modal trigger. Per-message-local
	// so each bubble owns its own modal instance and the right
	// `sourceMessage` is captured in the closure. The inline 📝 / overflow
	// "Capture as skill" item are conditional on the
	// `captureAffordanceInline` preference (Wave D.2 Task 5.1) — auto-
	// subscribed in the template via `$captureAffordanceInline` so Svelte
	// handles teardown.
	let captureOpen = false;

	// M2-C2 — Citation Engine UI. Lazy-fetch per-message citations from
	// `GET /messages/{id}/citations` once the assistant message has
	// finished streaming (Decision B). `fetchedCitations === null` means
	// "not yet fetched"; `[]` means "fetched, no rows". The decorator and
	// the sidecar chip list both consume this array. DE-275 captures the
	// future option to embed citations in the message envelope and skip
	// this round-trip entirely.
	let fetchedCitations: Citation[] | null = null;
	let citationFetchInflight = false;

	async function loadCitations(chatId: string, messageId: string): Promise<void> {
		citationFetchInflight = true;
		try {
			fetchedCitations = await citationsApi.getMessageCitations(chatId, messageId);
		} catch (err) {
			// Degrade gracefully — a 404 here just means no rows have been
			// persisted for this message yet (skills that don't cite, or
			// pre-M2 historical messages). Anything else is logged but the
			// bubble keeps rendering its content cleanly.
			if (!(err instanceof LQAIApiError) || err.status !== 404) {
				console.warn('[M2-C2] failed to load citations', err);
			}
			fetchedCitations = [];
		} finally {
			citationFetchInflight = false;
		}
	}

	$: if (
		message.role === 'assistant' &&
		message.id &&
		message.chat_id &&
		!isStreaming &&
		fetchedCitations === null &&
		!citationFetchInflight
	) {
		void loadCitations(message.chat_id, message.id);
	}

	// R6: split MiniMax-M3 `<think>…</think>` reasoning out of the assistant
	// text so it collapses into the ReasoningRibbon instead of leaking into the
	// answer prose (DOMPurify drops the unknown <think> tag but keeps its text).
	// `splitThink` is the same parser the agent surface uses; UI-only — the API
	// record keeps the honest full text.
	$: split =
		message.role === 'assistant' ? splitThink(message.content) : { thinking: null, visible: '' };

	// Both sinks go through the shared hardened renderer (media-forbidden — model
	// output is untrusted; see sanitize-markdown.ts). The reasoning is sanitised
	// on exactly the same path as the answer.
	$: rendered = message.role === 'assistant' ? renderModelMarkdown(split.visible) : '';
	$: reasoningHtml = renderModelMarkdown(split.thinking);

	// AE2 — pre-format the cited sources for the Copy-sources action. Empty when
	// the message has no fetched citations (hides the action). Plain text only —
	// the raw `source_text` is model/document output, but clipboard text is inert
	// (no markup is interpreted), so this needs no HTML sanitisation.
	$: sources = (fetchedCitations ?? []).map((c, i) => {
		const page = c.source_page != null ? ` (p.${c.source_page})` : '';
		return `[${i + 1}] ${c.source_text}${page}`;
	});
</script>

{#if message.kind === 'refusal'}
	<AeMessage from="assistant" data-testid={`lq-ai-message-${message.id}`}>
		<RefusalMessageBubble
			{message}
			{currentUserRole}
			onRerun={() => onRefusalRerun(message)}
			onOverrideRequested={() => onRefusalOverrideRequested(message)}
			onExplainerRequested={() => onRefusalExplainerRequested(message)}
		/>
	</AeMessage>
{:else}
	<AeMessage
		from={message.role === 'user' ? 'user' : 'assistant'}
		data-testid={`lq-ai-message-${message.id}`}
	>
		<MessageContent>
			{#if message.role === 'assistant'}
				{#if reasoningHtml}
					<ReasoningRibbon>
						<!-- eslint-disable-next-line svelte/no-at-html-tags — DOMPurify-sanitized above -->
						{@html reasoningHtml}
					</ReasoningRibbon>
				{/if}
				<div
					class="prose prose-sm dark:prose-invert max-w-none"
					data-testid="lq-ai-message-content"
					use:decorateCitationsInline={{
						citations: fetchedCitations ?? [],
						enabled: !isStreaming
					}}
					use:enhanceCodeBlocks={{ enabled: !isStreaming }}
				>
					<!-- eslint-disable-next-line svelte/no-at-html-tags — DOMPurify-sanitized via renderModelMarkdown -->
					{@html rendered}
				</div>
				{#if isStreaming}
					<div class="mt-1 text-xs text-muted-foreground italic">Streaming…</div>
				{/if}
			{:else}
				<div class="whitespace-pre-wrap text-sm" data-testid="lq-ai-message-content">
					{message.content}
				</div>
			{/if}
		</MessageContent>

		{#if message.role === 'user' && message.is_enhanced}
			<div
				class="mt-1 flex items-center gap-2 flex-wrap justify-end"
				data-testid="provenance-pill-enhanced"
			>
				<ProvenancePill
					kind="enhanced"
					summary="enhanced"
					onTap={() => (enhancedDiffOpen = true)}
				/>
			</div>
			{#if enhancedDiffOpen}
				<EnhancedDiffModal
					original={originalEnhancedPrompt}
					enhanced={message.content}
					on:close={() => (enhancedDiffOpen = false)}
				/>
			{/if}
		{/if}

		{#if message.role === 'assistant'}
			<div class="mt-1 flex items-center gap-2 flex-wrap justify-start w-full">
				<div class="flex items-center gap-2 flex-wrap">
					{#if message.routed_inference_tier}
						<TierBadge
							tier={message.routed_inference_tier}
							provider={message.routed_provider ?? null}
							on:open={() => (tierDetailsOpen = true)}
						/>
					{/if}
					<AppliedSkillsChip
						appliedSkills={message.applied_skills ?? []}
						onSkillClicked={onAppliedSkillClicked}
					/>
				</div>
				<div class="flex items-center gap-1">
					<MessageActionsBar
						answer={split.visible}
						{sources}
						retryDisabled={isStreaming}
						onRetry={() => onRetry(message)}
					/>
					{#if $captureAffordanceInline}
						<button
							type="button"
							class="text-base leading-none px-2 py-1 rounded text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed"
							aria-label={isStreaming
								? 'Capture as skill (available when streaming completes)'
								: 'Capture as skill'}
							title={isStreaming
								? 'Capture as skill (available when streaming completes)'
								: 'Capture as skill'}
							disabled={isStreaming}
							data-testid="lq-ai-message-capture-inline"
							on:click={() => (captureOpen = true)}>📝</button
						>
					{/if}
					<MessageOverflowMenu
						captureInOverflow={!$captureAffordanceInline}
						captureDisabled={isStreaming}
						onCapture={() => (captureOpen = true)}
					/>
				</div>
			</div>

			{#if captureOpen}
				<CaptureSkillModal sourceMessage={message} onClose={() => (captureOpen = false)} />
			{/if}

			{#if tierDetailsOpen}
				<TierDetailsPanel
					tier={message.routed_inference_tier ?? null}
					provider={message.routed_provider ?? null}
					model={message.routed_model ?? null}
					requestedModel={message.requested_model ?? null}
					promptTokens={message.prompt_tokens ?? null}
					completionTokens={message.completion_tokens ?? null}
					costEstimate={message.cost_estimate ?? null}
					on:close={() => (tierDetailsOpen = false)}
				/>
			{/if}

			{#if message.error_code}
				<div class="mt-2 max-w-full" data-testid="lq-ai-message-error">
					<Alert intent="error">
						Error: <strong>{message.error_code}</strong>. The assistant message was persisted with
						the partial content above for audit.
					</Alert>
				</div>
			{/if}

			<!--
			M2-C2 — Citation Engine sidecar chip list. Renders one chip per
			`"<quote>" (Source: [N])` marker the assistant emitted, joined
			to its persisted MessageCitation row. Markers without a row are
			the unverified signal (per `_persist_message_citations` in
			api/app/api/chats.py). The component returns nothing when the
			message has no citation markers — older skills + non-RAG turns
			stay visually unchanged.
		-->
			{#if fetchedCitations !== null}
				<div data-testid="lq-ai-message-citations">
					<!--
					AE3 — the AI Elements "Sources" card: a collapsible "Used N
					sources" rollup of the distinct documents this message cites
					(filename + pages + a representative quote + the 5-state
					verification marker). Sits above the per-quote sidecar chips;
					renders nothing when the message cites no documents.
				-->
					<MessageSources citations={fetchedCitations} />
					<!--
					R6: scan `split.visible` (the same think-stripped text the inline
					decorator sees), NOT the raw content — so a citation marker that
					appears only inside a `<think>` block produces neither a sidecar
					chip nor an inline mark, keeping the two surfaces consistent.
				-->
					<M2Citations citations={fetchedCitations} messageContent={split.visible} />
				</div>
			{/if}
		{/if}
	</AeMessage>
{/if}
