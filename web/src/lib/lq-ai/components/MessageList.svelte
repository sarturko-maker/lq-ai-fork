<script lang="ts">
	import { afterUpdate } from 'svelte';

	import type { Message } from '../types';
	import MessageBubble from './MessageBubble.svelte';

	export let messages: Message[] = [];
	export let streamingMessageId: string | null = null;
	export let onAppliedSkillClicked: ((name: string) => void) | undefined = undefined;

	let scroller: HTMLDivElement;

	afterUpdate(() => {
		// Stick to bottom while messages stream in. The user can still scroll
		// up; this is a lightweight auto-scroll that re-anchors on each
		// message append.
		if (scroller) {
			scroller.scrollTop = scroller.scrollHeight;
		}
	});
</script>

<div
	bind:this={scroller}
	class="flex-1 overflow-y-auto px-4 py-4 flex flex-col"
	data-testid="lq-ai-message-list"
>
	{#each messages as msg (msg.id)}
		<MessageBubble
			message={msg}
			isStreaming={streamingMessageId === msg.id}
			{onAppliedSkillClicked}
		/>
	{/each}

	{#if messages.length === 0}
		<div class="flex-1 flex items-center justify-center text-gray-400 text-sm italic">
			No messages yet. Attach a skill, optionally upload a file, and send a message.
		</div>
	{/if}
</div>
