<script lang="ts">
	/**
	 * Sidebar listing chats grouped by Project, with a "no project" bucket.
	 *
	 * - Toggle to include archived projects/chats (default off).
	 * - "+ New Chat" button (per Quickstart Step 4): respects the active
	 *   Project context — the new chat inherits the project_id when one is
	 *   selected.
	 * - Project picker spans across groups; clicking a Project header
	 *   filters the sidebar to that project's chats.
	 */
	import type { Chat, Project } from '../types';

	export let groups: Array<{ project: Project | null; chats: Chat[] }> = [];
	export let activeChatId: string | null = null;
	export let activeProjectId: string | null = null;
	export let archivedToggle: boolean = false;

	export let onSelectChat: (chat: Chat) => void = () => undefined;
	export let onNewChat: () => void = () => undefined;
	export let onSelectProject: (project: Project | null) => void = () => undefined;
	export let onToggleArchived: (next: boolean) => void = () => undefined;
</script>

<aside
	class="w-72 bg-gray-50 dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800 flex flex-col"
	data-testid="lq-ai-chat-sidebar"
>
	<div class="p-3 border-b border-gray-200 dark:border-gray-800">
		<button
			type="button"
			class="w-full inline-flex items-center justify-center px-3 py-2 rounded-md bg-indigo-600 text-white hover:bg-indigo-700 text-sm font-medium"
			on:click={onNewChat}
			data-testid="lq-ai-new-chat-btn"
		>
			+ New Chat
		</button>
	</div>

	<div class="px-3 py-2 flex items-center justify-between text-xs text-gray-600 dark:text-gray-400">
		<span>Projects</span>
		<label class="inline-flex items-center gap-1 cursor-pointer">
			<input
				type="checkbox"
				bind:checked={archivedToggle}
				on:change={() => onToggleArchived(archivedToggle)}
				data-testid="lq-ai-archived-toggle"
			/>
			<span>Show archived</span>
		</label>
	</div>

	<div class="flex-1 overflow-y-auto">
		<button
			type="button"
			class="block w-full text-left px-3 py-1 text-xs uppercase tracking-wide text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 {activeProjectId ===
			null
				? 'font-semibold text-indigo-700 dark:text-indigo-300'
				: ''}"
			on:click={() => onSelectProject(null)}
		>
			All chats
		</button>

		{#each groups as group (group.project?.id ?? '__no_project__')}
			<div class="mt-2">
				<button
					type="button"
					class="block w-full text-left px-3 py-1 text-sm font-medium {activeProjectId ===
					group.project?.id
						? 'text-indigo-700 dark:text-indigo-300'
						: 'text-gray-700 dark:text-gray-200'} hover:bg-gray-100 dark:hover:bg-gray-800"
					on:click={() => onSelectProject(group.project)}
					data-testid={`lq-ai-project-${group.project?.id ?? 'no-project'}`}
				>
					{group.project?.name ?? 'Without a project'}
					{#if group.project?.privileged}
						<span
							class="ml-1 inline-block px-1 py-0.5 rounded text-[10px] font-semibold bg-rose-100 text-rose-700 align-middle"
							title="Privileged matter — minimum_inference_tier enforced"
						>
							PRIVILEGED
						</span>
					{/if}
				</button>
				<ul class="mt-0.5">
					{#each group.chats as chat (chat.id)}
						<li>
							<button
								type="button"
								class="block w-full text-left px-5 py-1.5 text-sm rounded-sm hover:bg-gray-100 dark:hover:bg-gray-800 {activeChatId ===
								chat.id
									? 'bg-indigo-50 dark:bg-indigo-900/30 text-indigo-800 dark:text-indigo-100'
									: 'text-gray-700 dark:text-gray-300'}"
								on:click={() => onSelectChat(chat)}
								data-testid={`lq-ai-chat-${chat.id}`}
							>
								{chat.title || 'Untitled chat'}
							</button>
						</li>
					{/each}
				</ul>
			</div>
		{/each}

		{#if groups.length === 0}
			<div class="px-3 py-6 text-sm text-gray-500 text-center">
				No chats yet. Click <strong>+ New Chat</strong> to start.
			</div>
		{/if}
	</div>
</aside>
