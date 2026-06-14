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
	 *
	 * R8: migrated to Svelte 5 runes + semantic tokens (the cockpit list-pane
	 * idiom — `bg-muted/40`, selected rows `bg-accent text-accent-foreground`,
	 * `hover:bg-muted/60`); "+ New Chat" is the shadcn `Button` primitive
	 * (runes is what lets its `onclick` forward). No `<style>` block. The
	 * archived checkbox no longer binds a prop — it reports the new value up
	 * via `onToggleArchived` (the parent owns the state).
	 */
	import { Button } from '$lib/components/ui/button';
	import type { Chat, Project } from '../types';

	let {
		groups = [],
		activeChatId = null,
		activeProjectId = null,
		archivedToggle = false,
		onSelectChat = () => undefined,
		onNewChat = () => undefined,
		onSelectProject = () => undefined,
		onToggleArchived = () => undefined,
		hideProjectFilter = false
	}: {
		groups?: Array<{ project: Project | null; chats: Chat[] }>;
		activeChatId?: string | null;
		activeProjectId?: string | null;
		archivedToggle?: boolean;
		onSelectChat?: (chat: Chat) => void;
		onNewChat?: () => void;
		onSelectProject?: (project: Project | null) => void;
		onToggleArchived?: (next: boolean) => void;
		/**
		 * When true, hides the project-filter UI (the "Projects" label, "All chats"
		 * button, and per-project rows in the sidebar header). Used when ChatPanel
		 * is mounted inside a matter workspace that already represents a single
		 * project context — the user shouldn't see redundant project filtering.
		 */
		hideProjectFilter?: boolean;
	} = $props();

	const PROJECT_ROW =
		'block w-full text-left rounded-sm px-3 py-1 text-xs uppercase tracking-wider transition-colors duration-150';
	const CHAT_ROW =
		'block w-full text-left rounded-md px-3 py-1.5 text-sm transition-colors duration-150 ease-out';
</script>

<aside class="flex w-72 flex-col border-r border-border bg-muted/40" data-testid="lq-ai-chat-sidebar">
	<div class="border-b border-border p-3">
		<Button class="w-full" onclick={onNewChat} data-testid="lq-ai-new-chat-btn">+ New Chat</Button>
	</div>

	{#if !hideProjectFilter}
		<div
			class="flex items-center justify-between border-b border-border px-3 py-2 text-xs text-muted-foreground"
		>
			<span>Projects</span>
			<label class="inline-flex cursor-pointer items-center gap-1">
				<input
					type="checkbox"
					checked={archivedToggle}
					onchange={(e) => onToggleArchived(e.currentTarget.checked)}
					data-testid="lq-ai-archived-toggle"
				/>
				<span>Show archived</span>
			</label>
		</div>
	{/if}

	<div class="flex-1 overflow-y-auto p-1">
		{#if !hideProjectFilter}
			<button
				type="button"
				class="{PROJECT_ROW} {activeProjectId === null
					? 'bg-accent font-semibold text-accent-foreground'
					: 'text-muted-foreground hover:bg-muted/60'}"
				onclick={() => onSelectProject(null)}
			>
				All chats
			</button>

			{#each groups as group (group.project?.id ?? '__no_project__')}
				<div class="mt-2">
					<button
						type="button"
						class="{PROJECT_ROW} {activeProjectId === group.project?.id
							? 'font-semibold text-primary'
							: 'text-muted-foreground hover:bg-muted/60'}"
						onclick={() => onSelectProject(group.project)}
						data-testid={`lq-ai-project-${group.project?.id ?? 'no-project'}`}
					>
						{group.project?.name ?? 'Without a project'}
						{#if group.project?.privileged}
							<span
								class="ml-1 inline-block rounded bg-rose-500/10 px-1 py-0.5 align-middle text-[10px] font-semibold text-rose-700 dark:text-rose-300"
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
									class="{CHAT_ROW} {activeChatId === chat.id
										? 'bg-accent font-medium text-accent-foreground'
										: 'text-foreground hover:bg-muted/60'}"
									onclick={() => onSelectChat(chat)}
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
				<div class="px-3 py-6 text-center text-sm text-muted-foreground">
					No chats yet. Click <strong>+ New Chat</strong> to start.
				</div>
			{/if}
		{:else}
			{#each groups as group (group.project?.id ?? '__no_project__')}
				<ul class="mt-0.5">
					{#each group.chats as chat (chat.id)}
						<li>
							<button
								type="button"
								class="{CHAT_ROW} {activeChatId === chat.id
									? 'bg-accent font-medium text-accent-foreground'
									: 'text-foreground hover:bg-muted/60'}"
								onclick={() => onSelectChat(chat)}
								data-testid={`lq-ai-chat-${chat.id}`}
							>
								{chat.title || 'Untitled chat'}
							</button>
						</li>
					{/each}
				</ul>
			{/each}

			{#if groups.every((g) => g.chats.length === 0)}
				<div class="px-3 py-6 text-center text-sm text-muted-foreground">
					No chats yet. Click <strong>+ New Chat</strong> to start.
				</div>
			{/if}
		{/if}
	</div>
</aside>
