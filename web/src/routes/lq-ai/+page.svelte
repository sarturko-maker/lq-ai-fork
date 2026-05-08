<script lang="ts">
	/**
	 * LQ.AI chat shell — the route that the Quickstart Step 4 walkthrough
	 * exercises end-to-end.
	 *
	 * Layout: sidebar (left) | message list (centre) | attached-files panel (right).
	 * Above the input: skill picker (multi-skill, with frontmatter input form).
	 * Submit: streaming POST /messages, with applied-skills chips + tier badge
	 * surfaced per-message.
	 */
	import { onMount } from 'svelte';

	import { chatsApi, filesApi, messagesApi, projectsApi, skillsApi } from '$lib/lq-ai/api';
	import {
		activeChatStore,
		chatsByProject,
		chatsStore,
		messagesStore,
		projectsStore,
		skillsStore
	} from '$lib/lq-ai/stores';
	import {
		consumeMessageStream
	} from '$lib/lq-ai/sse/parser';
	import type {
		Chat,
		FileMeta,
		Message,
		Project,
		Skill
	} from '$lib/lq-ai/types';

	import ChatSidebar from '$lib/lq-ai/components/ChatSidebar.svelte';
	import AttachedFilesPanel from '$lib/lq-ai/components/AttachedFilesPanel.svelte';
	import SkillPicker from '$lib/lq-ai/components/SkillPicker.svelte';
	import MessageList from '$lib/lq-ai/components/MessageList.svelte';
	import TierBadge from '$lib/lq-ai/components/TierBadge.svelte';

	// ---- state ----
	let activeProject: Project | null = null;
	let archivedToggle = false;

	// Per-chat draft state.
	let composerText = '';
	let attachedSkillNames: string[] = [];
	let skillDetails: Record<string, Skill> = {};
	let skillInputs: Record<string, Record<string, unknown>> = {};

	let chatFiles: FileMeta[] = [];
	let projectFiles: FileMeta[] = [];
	let uploading = false;

	let streamingMessageId: string | null = null;
	let streamAbort: AbortController | null = null;
	let sendError: string | null = null;

	// ---- bootstrap ----
	async function loadShell() {
		try {
			const [projects, chatsPage, skills] = await Promise.all([
				projectsApi.listProjects(),
				chatsApi.listAllChats(),
				skillsApi.listSkills()
			]);
			projectsStore.set(projects);
			chatsStore.set(chatsPage);
			skillsStore.set(skills);
		} catch (e) {
			console.error('lq-ai: bootstrap load failed', e);
		}
	}

	async function selectChat(chat: Chat) {
		activeChatStore.set(chat);
		streamingMessageId = null;
		sendError = null;
		// Reset draft state.
		composerText = '';
		attachedSkillNames = [];
		skillInputs = {};
		// Load messages.
		try {
			const page = await messagesApi.listMessages(chat.id, { limit: 100 });
			messagesStore.set(page.items);
		} catch (e) {
			console.error('lq-ai: failed to load messages', e);
			messagesStore.set([]);
		}
		// Load attached project skills/files context.
		await refreshProjectContext(chat);
	}

	async function refreshProjectContext(chat: Chat) {
		projectFiles = [];
		if (!chat.project_id) return;
		try {
			const project = await projectsApi.getProject(chat.project_id);
			// Update the projects-store entry too.
			projectsStore.update(($projects) =>
				$projects.map((p) => (p.id === project.id ? project : p))
			);
			// Project-attached files are surfaced read-only per Project context inheritance.
			if (project.attached_file_ids && project.attached_file_ids.length > 0) {
				projectFiles = await Promise.all(
					project.attached_file_ids.map((id) => filesApi.getFile(id).catch(() => null))
				).then((items) => items.filter((x): x is FileMeta => x !== null));
			}
		} catch (e) {
			console.error('lq-ai: failed to load project context', e);
		}
	}

	async function createNewChat() {
		try {
			const chat = await chatsApi.createChat({
				project_id: activeProject?.id ?? null
			});
			chatsStore.update(($chats) => [chat, ...$chats]);
			selectChat(chat);
		} catch (e) {
			console.error('lq-ai: failed to create chat', e);
		}
	}

	function selectProject(project: Project | null) {
		activeProject = project;
	}

	function toggleArchived(next: boolean) {
		archivedToggle = next;
		// M1: archived listing reload — refresh both endpoints with `archived` flag.
		Promise.all([
			projectsApi.listProjects({ archived: next ? undefined : false }),
			chatsApi.listAllChats({ archived: next || undefined })
		])
			.then(([p, c]) => {
				projectsStore.set(p);
				chatsStore.set(c);
			})
			.catch((e) => console.error('lq-ai: archive toggle reload failed', e));
	}

	// ---- skill picker handlers ----
	async function attachSkill(name: string) {
		if (attachedSkillNames.includes(name)) return;
		attachedSkillNames = [...attachedSkillNames, name];
		try {
			const detail = await skillsApi.getSkill(name);
			skillDetails = { ...skillDetails, [name]: detail };
		} catch (e) {
			console.error('lq-ai: failed to load skill detail', e);
		}
	}

	function detachSkill(name: string) {
		attachedSkillNames = attachedSkillNames.filter((n) => n !== name);
		const { [name]: _, ...rest } = skillInputs;
		skillInputs = rest;
	}

	function updateSkillInputs(name: string, values: Record<string, unknown>) {
		skillInputs = { ...skillInputs, [name]: values };
	}

	// ---- file panel handlers ----
	async function uploadAttached(file: File) {
		uploading = true;
		try {
			const uploaded = await filesApi.uploadFile(file, {
				project_id: $activeChatStore?.project_id ?? undefined
			});
			chatFiles = [...chatFiles, uploaded];
		} catch (e) {
			console.error('lq-ai: upload failed', e);
		} finally {
			uploading = false;
		}
	}

	async function detachFile(file: FileMeta) {
		// Per the spec the M1 attached-files panel manages chat-local state;
		// the full file-row is left in place and can be re-attached later.
		chatFiles = chatFiles.filter((f) => f.id !== file.id);
	}

	// ---- send + stream ----
	async function sendMessage() {
		const chat = $activeChatStore;
		if (!chat) return;
		if (!composerText.trim()) return;

		// Validate required skill inputs.
		for (const name of attachedSkillNames) {
			const detail = skillDetails[name];
			if (!detail || !detail.inputs) continue;
			const missing = detail.inputs
				.filter((i) => i.required)
				.filter((i) => {
					const v = skillInputs[name]?.[i.name];
					return v === undefined || v === null || v === '';
				});
			if (missing.length > 0) {
				sendError = `Skill "${name}" is missing required inputs: ${missing
					.map((m) => m.name)
					.join(', ')}.`;
				return;
			}
		}

		sendError = null;

		// Optimistically append the user message; the persisted row will
		// supersede it once the start frame arrives.
		const optimisticUserId = `optimistic-${Date.now()}`;
		const userMsg: Message = {
			id: optimisticUserId,
			chat_id: chat.id,
			role: 'user',
			content: composerText,
			applied_skills: attachedSkillNames,
			created_at: new Date().toISOString()
		};
		messagesStore.update(($m) => [...$m, userMsg]);

		const draftAssistantId = `draft-${Date.now()}`;
		const assistantMsg: Message = {
			id: draftAssistantId,
			chat_id: chat.id,
			role: 'assistant',
			content: '',
			applied_skills: [],
			created_at: new Date().toISOString()
		};
		messagesStore.update(($m) => [...$m, assistantMsg]);
		streamingMessageId = draftAssistantId;

		streamAbort = new AbortController();

		try {
			const res = await messagesApi.sendMessageStream(
				chat.id,
				{
					content: composerText,
					skills: attachedSkillNames.length > 0 ? attachedSkillNames : undefined,
					skill_inputs:
						Object.keys(skillInputs).length > 0
							? (skillInputs as Record<string, Record<string, unknown>>)
							: undefined,
					stream: true
				},
				streamAbort.signal
			);
			composerText = '';

			if (!res.body) {
				throw new Error('Empty stream body');
			}

			let assistantId = draftAssistantId;

			await consumeMessageStream(res.body, {
				onStart: (frame) => {
					// Replace the draft id with the persisted id.
					assistantId = frame.lq_ai_message_id;
					streamingMessageId = assistantId;
					messagesStore.update(($m) =>
						$m.map((m) => (m.id === draftAssistantId ? { ...m, id: assistantId } : m))
					);
				},
				onDelta: (frame) => {
					messagesStore.update(($m) =>
						$m.map((m) =>
							m.id === assistantId
								? {
										...m,
										content: (m.content ?? '') + frame.delta,
										routed_inference_tier: frame.routed_inference_tier ?? m.routed_inference_tier,
										applied_skills: frame.applied_skills ?? m.applied_skills
								  }
								: m
						)
					);
				},
				onComplete: (frame) => {
					streamingMessageId = null;
					messagesStore.update(($m) =>
						$m.map((m) =>
							m.id === assistantId
								? {
										...m,
										...frame.message,
										applied_skills: frame.applied_skills ?? frame.message.applied_skills,
										routed_inference_tier:
											frame.routed_inference_tier ?? frame.message.routed_inference_tier,
										routed_provider: frame.routed_provider ?? frame.message.routed_provider,
										citations: frame.citations ?? frame.message.citations ?? []
								  }
								: m
						)
					);
				},
				onError: (frame) => {
					streamingMessageId = null;
					sendError = `${frame.error.code}: ${frame.error.message}`;
					messagesStore.update(($m) =>
						$m.map((m) =>
							m.id === assistantId ? { ...m, error_code: frame.error.code } : m
						)
					);
				}
			});
		} catch (e: unknown) {
			streamingMessageId = null;
			console.error('lq-ai: stream failed', e);
			sendError = e instanceof Error ? e.message : 'Stream failed';
		} finally {
			streamAbort = null;
		}
	}

	function abortStream() {
		streamAbort?.abort();
		streamingMessageId = null;
	}

	function handleAppliedSkillClicked(name: string) {
		// M1: a lightweight info toast. M2 will land a richer skill-inspector
		// panel per the Quickstart Step 6 walkthrough.
		// eslint-disable-next-line no-alert
		alert(`This message used the ${name} skill.\n\n(M2 will land a full skill-inspector panel.)`);
	}

	onMount(() => {
		loadShell();
	});

	$: groups = $chatsByProject;
	$: filteredGroups = activeProject
		? groups.filter((g) => g.project?.id === activeProject?.id)
		: groups;
	$: activeChat = $activeChatStore;
	$: messages = $messagesStore;
	$: projectAttachedSkills = activeChat?.project_id
		? $projectsStore.find((p) => p.id === activeChat?.project_id)?.attached_skill_names ?? []
		: [];
</script>

<div class="flex flex-1 overflow-hidden" data-testid="lq-ai-chat-shell">
	<ChatSidebar
		groups={filteredGroups}
		activeChatId={activeChat?.id ?? null}
		activeProjectId={activeProject?.id ?? null}
		{archivedToggle}
		onSelectChat={selectChat}
		onNewChat={createNewChat}
		onSelectProject={selectProject}
		onToggleArchived={toggleArchived}
	/>

	<section class="flex-1 flex flex-col overflow-hidden">
		<div
			class="px-4 py-2 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between"
			data-testid="lq-ai-chat-header"
		>
			{#if activeChat}
				<div>
					<h2 class="text-sm font-semibold text-gray-800 dark:text-gray-100">
						{activeChat.title || 'Untitled chat'}
					</h2>
					{#if activeChat.project_id}
						<p class="text-xs text-gray-500">
							In project: {$projectsStore.find((p) => p.id === activeChat.project_id)?.name ??
								activeChat.project_id}
						</p>
					{/if}
				</div>
				<div class="flex items-center gap-2">
					{#if messages[messages.length - 1]?.role === 'assistant' && messages[messages.length - 1]?.routed_inference_tier}
						<TierBadge
							tier={messages[messages.length - 1].routed_inference_tier ?? null}
							provider={messages[messages.length - 1].routed_provider ?? null}
						/>
					{/if}
				</div>
			{:else}
				<h2 class="text-sm text-gray-500">Pick or create a chat to start.</h2>
			{/if}
		</div>

		<MessageList
			{messages}
			{streamingMessageId}
			onAppliedSkillClicked={handleAppliedSkillClicked}
		/>

		{#if activeChat}
			<div
				class="border-t border-gray-200 dark:border-gray-800 p-3 space-y-2"
				data-testid="lq-ai-composer"
			>
				<SkillPicker
					availableSkills={$skillsStore}
					selectedSkillNames={attachedSkillNames}
					{projectAttachedSkills}
					{skillDetails}
					{skillInputs}
					onAttach={attachSkill}
					onDetach={detachSkill}
					onUpdateInputs={updateSkillInputs}
				/>

				{#if sendError}
					<div
						class="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded px-2 py-1"
						data-testid="lq-ai-send-error"
					>
						{sendError}
					</div>
				{/if}

				<div class="flex items-end gap-2">
					<textarea
						class="flex-1 text-sm border border-gray-300 rounded px-2 py-1 dark:bg-gray-800 resize-none"
						rows="3"
						placeholder="Type a message…"
						bind:value={composerText}
						data-testid="lq-ai-composer-input"
					></textarea>
					{#if streamingMessageId}
						<button
							type="button"
							class="px-3 py-2 rounded-md bg-rose-600 text-white hover:bg-rose-700 text-sm font-medium"
							on:click={abortStream}
							data-testid="lq-ai-abort-btn"
						>
							Stop
						</button>
					{:else}
						<button
							type="button"
							class="px-3 py-2 rounded-md bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 text-sm font-medium"
							on:click={sendMessage}
							disabled={!composerText.trim()}
							data-testid="lq-ai-send-btn"
						>
							Send
						</button>
					{/if}
				</div>
			</div>
		{/if}
	</section>

	{#if activeChat}
		<AttachedFilesPanel
			{chatFiles}
			{projectFiles}
			{uploading}
			onUpload={uploadAttached}
			onDetach={detachFile}
		/>
	{/if}
</div>
