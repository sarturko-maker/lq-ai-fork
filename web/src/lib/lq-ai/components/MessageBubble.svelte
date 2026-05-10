<script lang="ts">
	/**
	 * Single message bubble.
	 *
	 * - Assistant content renders as Markdown (M1: client-side via `marked`,
	 *   sanitised with `DOMPurify`; both already deps of the OpenWebUI fork).
	 * - Applied-skills chips on assistant messages.
	 * - Tier badge on assistant messages.
	 * - error_code surfaces as a red-line banner (per Task C8 spec).
	 * - Citations render as a "M2: citations coming soon" placeholder when
	 *   the array is empty (M1 backend ships [] per `MessagePostResponse`).
	 */
	import DOMPurify from 'dompurify';
	import { marked } from 'marked';

	import type { Message } from '../types';
	import AppliedSkillsChip from './AppliedSkillsChip.svelte';
	import TierBadge from './TierBadge.svelte';
	import TierDetailsPanel from './TierDetailsPanel.svelte';

	export let message: Message;
	export let isStreaming: boolean = false;
	export let onAppliedSkillClicked: ((name: string) => void) | undefined = undefined;

	// D2: tier badge opens a click-for-details panel surfacing the
	// resolved provider/model + token usage. Per PRD §1.3 the user
	// can always answer "what just ran?" from the message they
	// received. State stays local to this bubble so multiple open
	// panels are not possible (the modal is exclusive).
	let tierDetailsOpen = false;

	$: bubbleClasses =
		message.role === 'user'
			? 'bg-indigo-600 text-white self-end'
			: message.role === 'assistant'
			? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 border border-gray-200 dark:border-gray-700 self-start'
			: 'bg-gray-100 text-gray-700 self-center text-sm';

	$: rendered =
		message.role === 'assistant'
			? DOMPurify.sanitize(marked.parse(message.content || '', { async: false }) as string)
			: '';
</script>

<div class="flex flex-col max-w-3xl {message.role === 'user' ? 'items-end' : 'items-start'} mb-3" data-testid={`lq-ai-message-${message.id}`}>
	<div class="rounded-lg px-3 py-2 {bubbleClasses} max-w-full">
		{#if message.role === 'assistant'}
			<div
				class="prose prose-sm dark:prose-invert max-w-none"
				data-testid="lq-ai-message-content"
			>
				{@html rendered}
			</div>
			{#if isStreaming}
				<div class="mt-1 text-xs text-gray-500 italic">Streaming…</div>
			{/if}
		{:else}
			<div class="whitespace-pre-wrap text-sm" data-testid="lq-ai-message-content">
				{message.content}
			</div>
		{/if}
	</div>

	{#if message.role === 'assistant'}
		<div class="mt-1 flex items-center gap-2 flex-wrap">
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

		{#if tierDetailsOpen}
			<TierDetailsPanel
				tier={message.routed_inference_tier ?? null}
				provider={message.routed_provider ?? null}
				model={message.routed_model ?? null}
				promptTokens={message.prompt_tokens ?? null}
				completionTokens={message.completion_tokens ?? null}
				costEstimate={message.cost_estimate ?? null}
				on:close={() => (tierDetailsOpen = false)}
			/>
		{/if}

		{#if message.error_code}
			<div
				class="mt-2 px-2 py-1 rounded border border-rose-300 bg-rose-50 text-rose-800 text-xs max-w-full"
				data-testid="lq-ai-message-error"
			>
				Error: <strong>{message.error_code}</strong>. The assistant message was persisted with the
				partial content above for audit.
			</div>
		{/if}

		{#if message.citations && message.citations.length === 0}
			<div class="mt-1 text-xs text-gray-400 italic">
				M2: citation links will land in this message footer.
			</div>
		{/if}
	{/if}
</div>
