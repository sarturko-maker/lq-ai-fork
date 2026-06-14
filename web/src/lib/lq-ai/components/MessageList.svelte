<script lang="ts">
	import type { Message } from '../types';
	import MessageBubble from './MessageBubble.svelte';
	import {
		Conversation,
		ConversationContent,
		ConversationEmptyState,
		ConversationScrollButton
	} from '$lib/lq-ai/components/ai-elements/conversation/index.js';

	// AE1 (ADR-F011): MessageList is now the AI Elements **Conversation** —
	// a scroll container with sticky scroll-to-bottom. The previous
	// `afterUpdate` hard-scroll is gone: ConversationContent's
	// StickToBottomContext auto-scrolls on append UNLESS the user has scrolled
	// up (then the floating ScrollButton appears). Runes so the vendored
	// runes components compose cleanly.
	let {
		messages = [],
		streamingMessageId = null,
		onAppliedSkillClicked = undefined,
		// Wave D.1 T15 — refusal-bubble forwarding (pure pass-through to the bubble).
		currentUserRole = 'member',
		onRefusalRerun = () => {},
		onRefusalOverrideRequested = () => {},
		onRefusalExplainerRequested = () => {},
		// AE2 — per-message Retry (re-run the preceding prompt). Pass-through.
		onRetry = () => {},
		// Wave D.1 T20 — enhanced-prompt originals (content → typed original).
		enhancementOriginals = {}
	}: {
		messages?: Message[];
		streamingMessageId?: string | null;
		onAppliedSkillClicked?: (name: string) => void;
		currentUserRole?: 'admin' | 'member' | 'viewer';
		onRefusalRerun?: (msg: Message) => void;
		onRefusalOverrideRequested?: (msg: Message) => void;
		onRefusalExplainerRequested?: (msg: Message) => void;
		onRetry?: (msg: Message) => void;
		enhancementOriginals?: Record<string, string>;
	} = $props();
</script>

<div class="min-h-0 flex-1">
	<Conversation class="h-full">
		<ConversationContent class="min-h-0 flex-1 overflow-y-auto" data-testid="lq-ai-message-list">
			{#each messages as msg (msg.id)}
				<MessageBubble
					message={msg}
					isStreaming={streamingMessageId === msg.id}
					{onAppliedSkillClicked}
					{currentUserRole}
					{onRefusalRerun}
					{onRefusalOverrideRequested}
					{onRefusalExplainerRequested}
					{onRetry}
					originalEnhancedPrompt={enhancementOriginals[msg.content]}
				/>
			{/each}

			{#if messages.length === 0}
				<ConversationEmptyState
					title="No messages yet"
					description="Attach a skill, optionally upload a file, and send a message."
				/>
			{/if}
		</ConversationContent>
		<ConversationScrollButton data-testid="lq-ai-scroll-bottom" aria-label="Scroll to latest" />
	</Conversation>
</div>
