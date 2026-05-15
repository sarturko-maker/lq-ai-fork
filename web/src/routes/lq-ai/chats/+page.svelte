<script lang="ts">
	/**
	 * /lq-ai/chats — thin route wrapper around <ChatPanel>.
	 *
	 * The chat composition was extracted into a reusable component in
	 * Wave C Task 0 so /lq-ai/matters/[id] can mount the same surface
	 * inside the matter workspace. URL query params:
	 *
	 *   ?id={chatId}       — auto-selects that chat on load
	 *   ?project_id={id}   — filters chat list to that project
	 */
	import { page } from '$app/stores';
	import ChatPanel from '$lib/lq-ai/components/ChatPanel.svelte';

	$: initialChatId = $page.url.searchParams.get('id') ?? undefined;
	$: projectIdFilter = $page.url.searchParams.get('project_id') ?? undefined;
</script>

<ChatPanel {projectIdFilter} {initialChatId} />
