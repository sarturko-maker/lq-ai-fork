<script context="module" lang="ts">
	/**
	 * Pure helpers for slash-invocation detection (Wave D.2 Task 7.1).
	 *
	 * Exposed from a `context="module"` block so vitest can exercise the
	 * regex-based detection logic without mounting the (large) component.
	 * Mirrors the convention SlashPopover uses for its keyboard-action
	 * helpers.
	 *
	 * The detection contract:
	 *   - The popover opens only when the slash sits at the start of a line
	 *     (BOL or immediately after `\n`). Mid-line `/` (e.g., "and/or",
	 *     "TCP/IP") does NOT open the popover.
	 *   - Between the slash and the caret we accept the slash-alias
	 *     character class (lowercase a-z, digits, hyphen) — matching the
	 *     server-side `slash_alias` validator (Task 2.5). Any other char
	 *     (whitespace, uppercase, underscore) terminates the candidate
	 *     query and closes the popover.
	 *   - Empty query is allowed (`/` alone opens the popover with the
	 *     "no-query" empty state per SlashPopover.emptyStateKind()).
	 */
	export type SlashDetection =
		| { open: false }
		| { open: true; query: string; slashIndex: number };

	export function isAtLineStart(text: string, pos: number): boolean {
		if (pos === 0) return true;
		return text[pos - 1] === '\n';
	}

	export function detectSlashAt(text: string, caret: number): SlashDetection {
		if (caret === 0) return { open: false };
		// Walk left from the caret over the legal slash-alias char class.
		let scan = caret;
		while (scan > 0 && /[a-z0-9-]/.test(text[scan - 1])) scan--;
		if (scan === 0 || text[scan - 1] !== '/') return { open: false };
		const slashIndex = scan - 1;
		if (!isAtLineStart(text, slashIndex)) return { open: false };
		return {
			open: true,
			query: text.slice(slashIndex + 1, caret),
			slashIndex
		};
	}
</script>

<script lang="ts">
	/**
	 * ChatPanel — reusable chat composition surface.
	 *
	 * Extracted from /lq-ai/chats/+page.svelte in Wave C Task 0 so that
	 * /lq-ai/matters/[id] can mount the same surface inside the matter rail.
	 *
	 * Props:
	 *   projectIdFilter  — when set, scopes the chat list to chats in this
	 *                      project and hides the redundant project-filter UI
	 *                      inside ChatSidebar.
	 *   initialChatId    — when set, auto-selects that chat after loadShell().
	 *
	 * Layout: sidebar (left) | message list (centre) | attached-files panel (right).
	 * Above the input: skill picker (multi-skill, with frontmatter input form).
	 * Submit: streaming POST /messages, with applied-skills chips + tier badge
	 * surfaced per-message.
	 */
	import { get } from 'svelte/store';
	import { onMount, tick } from 'svelte';
	import { goto } from '$app/navigation';

	import {
		chatsApi,
		filesApi,
		messagesApi,
		modelsApi,
		projectsApi,
		skillsApi
	} from '$lib/lq-ai/api';
	import type { ModelListResponse } from '$lib/lq-ai/api/models';
	import { defaultSelection, groupModels } from '$lib/lq-ai/api/models';
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
		SavedPrompt,
		Skill
	} from '$lib/lq-ai/types';

	import ChatSidebar from '$lib/lq-ai/components/ChatSidebar.svelte';
	import AttachedFilesPanel from '$lib/lq-ai/components/AttachedFilesPanel.svelte';
	import SkillPicker from '$lib/lq-ai/components/SkillPicker.svelte';
	import ModelPicker from '$lib/lq-ai/components/ModelPicker.svelte';
	import MessageList from '$lib/lq-ai/components/MessageList.svelte';
	import TierBadge from '$lib/lq-ai/components/TierBadge.svelte';
	import SavedPromptsPanel from '$lib/lq-ai/components/SavedPromptsPanel.svelte';
	// AE7 (ADR-F011) — AI Elements Suggestion chips. Backed by the user's own
	// SavedPrompts (an honest, user-owned data source) as empty-state starters —
	// NOT invented model follow-ups (no honest source for those exists).
	import { Suggestion, Suggestions } from '$lib/lq-ai/components/ai-elements/suggestion/index.js';
	import AmbientFooter from '$lib/lq-ai/components/AmbientFooter.svelte';
	import EnhancePromptExpansion from '$lib/lq-ai/components/EnhancePromptExpansion.svelte';
	import AttachKBModal from '$lib/lq-ai/components/AttachKBModal.svelte';
	import TierFloorOverrideModal from '$lib/lq-ai/components/TierFloorOverrideModal.svelte';
	import ReceiptsDrawer, {
		readPersistedOpen as readReceiptsDrawerOpen
	} from '$lib/lq-ai/components/ReceiptsDrawer.svelte';
	import SlashPopover from '$lib/lq-ai/components/SlashPopover.svelte';
	// AE5 (ADR-F011) — AI Elements Prompt Input toolbar icons (lucide, the
	// established icon set; no emoji glyphs).
	import Paperclip from '@lucide/svelte/icons/paperclip';
	import Sparkles from '@lucide/svelte/icons/sparkles';
	import ScrollText from '@lucide/svelte/icons/scroll-text';
	import Send from '@lucide/svelte/icons/send';
	import Square from '@lucide/svelte/icons/square';
	import type { SkillAutocompleteItem } from '$lib/lq-ai/types';
	import { auth } from '$lib/lq-ai/auth/store';
	import { createEventDispatcher } from 'svelte';
	import { fade } from 'svelte/transition';
	import { motionMs } from '$lib/lq-ai/cockpit/helpers';

	// ---- component props ----
	export let projectIdFilter: string | undefined = undefined;
	export let initialChatId: string | undefined = undefined;

	// ---- responsive shell (R8) ----
	// Mirrors cockpit/Cockpit.svelte: below 880px the two fixed side panes
	// leave the flex row and become off-canvas drawers behind header toggles
	// plus a shared scrim. The drawers slide via a CSS transform that
	// motion-reduce:transition-none disables; the scrim fade is gated through
	// the shared motionMs() helper. (R8 owned the chat-shell layout; AE5 ≡ R9
	// then migrated ChatPanel's header + composer off the legacy --lq-* tokens
	// to semantic tokens — fixing the dark-mode column gap.)
	let viewportWidth = 1280;
	$: isNarrow = viewportWidth < 880;
	let navDrawerOpen = false;
	let filesDrawerOpen = false;
	// Drawer wrapper refs — focus moves into the just-opened drawer (a11y:
	// matches the cockpit dialog idiom), and a closed drawer is made `inert`
	// below so its off-canvas controls leave the tab order + a11y tree.
	let sidebarDrawerEl: HTMLDivElement | null = null;
	let filesDrawerEl: HTMLDivElement | null = null;
	// Leaving the narrow layout always closes the drawers.
	$: if (!isNarrow) {
		navDrawerOpen = false;
		filesDrawerOpen = false;
	}
	$: sidebarWrapClass = isNarrow
		? `absolute inset-y-0 left-0 z-40 flex w-72 max-w-[85%] bg-background shadow-lg transition-transform duration-200 ease-out motion-reduce:transition-none ${navDrawerOpen ? 'translate-x-0' : '-translate-x-full'}`
		: 'flex w-72 shrink-0';
	$: filesWrapClass = isNarrow
		? `absolute inset-y-0 right-0 z-40 flex w-72 max-w-[85%] bg-background shadow-lg transition-transform duration-200 ease-out motion-reduce:transition-none ${filesDrawerOpen ? 'translate-x-0' : 'translate-x-full'}`
		: 'flex shrink-0';

	async function toggleNavDrawer() {
		navDrawerOpen = !navDrawerOpen;
		if (navDrawerOpen) {
			filesDrawerOpen = false;
			// Wait for the reactive `inert` to clear before focusing the panel.
			await tick();
			sidebarDrawerEl?.focus();
		}
	}
	async function toggleFilesDrawer() {
		filesDrawerOpen = !filesDrawerOpen;
		if (filesDrawerOpen) {
			navDrawerOpen = false;
			await tick();
			filesDrawerEl?.focus();
		}
	}
	function closeDrawers() {
		navDrawerOpen = false;
		filesDrawerOpen = false;
	}
	function onShellKey(e: KeyboardEvent) {
		if (e.key === 'Escape' && (navDrawerOpen || filesDrawerOpen)) closeDrawers();
	}

	// ---- state ----
	let activeProject: Project | null = null;
	let archivedToggle = false;

	// Per-chat draft state.
	let composerText = '';
	// AE7 — the caller's saved prompts, surfaced from SavedPromptsPanel's single
	// fetch (no duplicate request). Rendered as AE Suggestion starter chips on an
	// empty conversation.
	let savedPromptChips: SavedPrompt[] = [];

	/** Append a saved-prompt body to the composer (stack onto any in-progress
	 *  draft), or set it when the composer is empty. Shared by the
	 *  SavedPromptsPanel quick-insert and the AE7 starter chips. */
	function insertIntoComposer(text: string): void {
		composerText = composerText.trim() ? `${composerText.trimEnd()}\n\n${text}` : text;
	}
	let attachedSkillNames: string[] = [];
	let skillDetails: Record<string, Skill> = {};
	let skillInputs: Record<string, Record<string, unknown>> = {};

	// Wave D.2 Task 7.2 — per-attachment provenance.
	// Parallel map keyed by slug (mirrors `attachedSkillNames`). Default
	// ('picker') is applied at attach-time for any slug not already
	// tagged, so picker-driven attaches and the slash flow are
	// disambiguated for receipts/audit. Reset alongside
	// `attachedSkillNames` whenever the chat changes. Plain Record
	// (not Map) so Svelte 4 reactivity tracks the assignment.
	let attachmentSources: Record<string, string> = {};

	// Wave D.1 T20 follow-on (deferral A + B) — Enhance Prompt tracking.
	// `pendingEnhancement` holds the most recent "Use enhanced" outcome
	// from EnhancePromptExpansion; we use it on send to (a) inject
	// `'enhance-prompt'` into the user-message `skills[]` payload so
	// `MessageResponse.is_enhanced` flips true (per ADR 0007), and (b)
	// remember the original prompt the user typed before the skill
	// expanded it so the ✨ enhanced pill can open a tap-to-diff modal.
	// Map keyed by the persisted message id (resolved after the start
	// frame) — the original is otherwise unrecoverable server-side
	// because the user-message row stores only the enhanced content.
	let pendingEnhancement: { original: string; enhanced: string } | null = null;
	let enhancementOriginals: Record<string, string> = {};

	// D0 — model picker state. `availableModels` holds the merged list from
	// `GET /api/v1/models`; `modelByChat` persists the per-chat selection
	// client-side (keyed by chat_id) so switching between chats doesn't
	// reset the user's choice. `currentModelId` is the selection for the
	// active chat, falling back to the picker's default when the chat has
	// no remembered choice yet.
	let availableModels: ModelListResponse = { object: 'list', data: [] };
	let modelByChat: Record<string, string> = {};

	let chatFiles: FileMeta[] = [];
	let projectFiles: FileMeta[] = [];
	let uploading = false;

	let streamingMessageId: string | null = null;
	let streamAbort: AbortController | null = null;
	let sendError: string | null = null;

	// T6 — Enhance Prompt panel reference. Parent calls expansionPanel.open().
	let expansionPanel: EnhancePromptExpansion | null = null;

	// T12 — Attach-KB modal state. The composer 📎 button mounts the shared
	// AttachKBModal scoped to the active chat's project. Successful attaches
	// bubble up to the matter workspace via the `kbsAttached` event so the
	// matter rail can refresh its KB list. The modal is only meaningful when
	// the active chat lives inside a project (legal matter); for project-less
	// chats the 📎 button is hidden.
	let attachKbModalOpen = false;
	const dispatch = createEventDispatcher<{ kbsAttached: { kbIds: string[] } }>();

	// Wave D.1 T19 — Receipts drawer state. The composer 📜 button toggles
	// the right-side receipts drawer (T18). Open state is restored from
	// localStorage when the active chat changes, so it survives reloads and
	// chat switches.
	let receiptsDrawerOpen = false;

	function openAttachKbModal(): void {
		attachKbModalOpen = true;
	}

	function closeAttachKbModal(): void {
		attachKbModalOpen = false;
	}

	async function handleKbsAttached(kbIds: string[]): Promise<void> {
		attachKbModalOpen = false;
		// Refresh the local projects-store entry so the modal's "currently
		// attached" badge + the matter rail's KB list see the new ids without
		// waiting for a chat re-select. The parent matter page also listens
		// to `kbsAttached` and re-fetches the matter top-level for routes
		// that hold matter state of their own.
		const projectId = composerProjectId;
		if (projectId) {
			try {
				const updated = await projectsApi.getProject(projectId);
				projectsStore.update(($projects) =>
					$projects.map((p) => (p.id === updated.id ? updated : p))
				);
			} catch (e) {
				console.error('lq-ai: failed to refresh project after KB attach', e);
			}
		}
		dispatch('kbsAttached', { kbIds });
	}

	// Wave D.1 T15 — refusal-bubble flow. ChatPanel owns the override-modal
	// state and the three per-message callbacks (re-run, override-requested,
	// explainer). On override success the refusal row is replaced in-place by
	// the new kind='ai' Message; admin-only override is enforced by the
	// RefusalMessageBubble's showOverrideButton(role) helper — we still pass
	// the real role here so members/viewers never see the button at all.
	let overrideModalOpen = false;
	let overrideMessage: Message | null = null;

	function handleRefusalOverrideRequested(msg: Message): void {
		overrideMessage = msg;
		overrideModalOpen = true;
	}

	function closeOverrideModal(): void {
		overrideModalOpen = false;
		overrideMessage = null;
	}

	function rerunPrecedingPrompt(msg: Message): void {
		// Find the immediately-preceding user message and re-dispatch its
		// content through the existing sendMessage() flow. Re-using the
		// composer path keeps streaming + applied-skills + model selection
		// consistent with a normal turn. Shared by the refusal "re-run" and the
		// AE2 per-message "Retry" action.
		const list = get(messagesStore);
		const idx = list.findIndex((m) => m.id === msg.id);
		if (idx <= 0) return;
		for (let i = idx - 1; i >= 0; i--) {
			const candidate = list[i];
			const isUser = candidate.kind === 'user' || candidate.role === 'user';
			if (isUser && candidate.content) {
				composerText = candidate.content;
				void sendMessage();
				return;
			}
		}
	}

	function handleRefusalRerun(msg: Message): void {
		// Future: surface a "re-running…" indicator on the refusal row while the
		// stream is in flight.
		rerunPrecedingPrompt(msg);
	}

	// AE2 (ADR-F011) — per-message Retry on any assistant message; identical
	// re-dispatch path as the refusal re-run.
	function handleAssistantRetry(msg: Message): void {
		rerunPrecedingPrompt(msg);
	}

	function handleRefusalExplainerRequested(_msg: Message): void {
		// JIT explainer for the tier-floor refusal. M1 surfaces the trust
		// page anchor; v1.1+ may swap to an inline modal carrying the §7.4
		// copy without leaving the chat.
		if (typeof window !== 'undefined') {
			window.open('/lq-ai/trust#tier-floors', '_blank', 'noopener');
		}
	}

	function handleOverrideSuccess(newAiMessage: Message): void {
		// Replace the refusal row in-place so the operator's mental model
		// (one turn → one bubble) survives the override path. The new
		// kind='ai' Message carries the routed_inference_tier + provider, so
		// the assistant rendering path takes over for that slot.
		const replacing = overrideMessage;
		if (replacing) {
			messagesStore.update(($m) =>
				$m.map((m) => (m.id === replacing.id ? newAiMessage : m))
			);
		}
		closeOverrideModal();
	}

	// ---- bootstrap ----
	async function loadShell() {
		try {
			const [projects, chatsPage, skills] = await Promise.all([
				projectsApi.listProjects(),
				chatsApi.listAllChats(projectIdFilter ? { project_id: projectIdFilter } : {}),
				skillsApi.listSkills()
			]);
			projectsStore.set(projects);
			chatsStore.set(chatsPage);
			skillsStore.set(skills);
		} catch (e) {
			console.error('lq-ai: bootstrap load failed', e);
		}
		// D0 — model list. Best-effort: if the gateway is unreachable the
		// picker shows an empty state and the composer falls back to the
		// "smart" alias on send so the chat still works.
		try {
			availableModels = await modelsApi.listModels();
		} catch (e) {
			console.error('lq-ai: model list load failed', e);
			availableModels = { object: 'list', data: [] };
		}
	}

	function selectModel(id: string): void {
		const chat = $activeChatStore;
		if (!chat) return;
		modelByChat = { ...modelByChat, [chat.id]: id };
	}

	async function selectChat(chat: Chat) {
		activeChatStore.set(chat);
		streamingMessageId = null;
		sendError = null;
		// Reset draft state.
		composerText = '';
		attachedSkillNames = [];
		attachmentSources = {};
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
				project_id: projectIdFilter ?? activeProject?.id ?? null
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
		// M1: archived listing reload. Per the backend OpenAPI sketch, omitting
		// `archived` is equivalent to `archived=false`; `archived=true` returns
		// archived rows only. So when the operator flips the toggle on we pass
		// `archived: true`; when off, we omit the flag.
		const baseOpts = projectIdFilter ? { project_id: projectIdFilter } : {};
		Promise.all([
			projectsApi.listProjects(next ? { archived: true } : {}),
			chatsApi.listAllChats(next ? { ...baseOpts, archived: true } : baseOpts)
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
		// Wave D.2 Task 7.2 — default attach provenance to 'picker'. The
		// slash-invocation flow (onSlashSelect) pre-tags the slug with
		// 'slash' BEFORE calling attachSkill, so this default only fires
		// for SkillPicker-driven attaches. Don't overwrite an existing
		// tag — that would silently demote 'slash' to 'picker' in any
		// future re-entrant attach path.
		if (!attachmentSources[name]) {
			attachmentSources = { ...attachmentSources, [name]: 'picker' };
		}
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
		const next = { ...skillInputs };
		delete next[name];
		skillInputs = next;
		// Wave D.2 Task 7.2 — drop the parallel provenance entry so a
		// re-attach starts fresh (and so the map doesn't accumulate
		// orphaned slugs across the lifetime of a chat).
		const nextSources = { ...attachmentSources };
		delete nextSources[name];
		attachmentSources = nextSources;
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

		// Wave D.1 T20 follow-on: if the operator clicked "Use enhanced"
		// and the composer still holds the AI-enhanced text, inject
		// `'enhance-prompt'` into the skills payload so the persisted
		// user-message row carries it in `applied_skills` (ADR 0007
		// denormalization). `message_to_response` then flips
		// `is_enhanced=true`, which MessageBubble keys the ✨ pill off.
		// We also remember the original text keyed by the enhanced
		// content so the tap-to-diff modal can recover it; session-only
		// (lost on reload — the server stores only the enhanced text).
		const sentSkillsForUser = [...attachedSkillNames];
		let isEnhancedSend = false;
		if (pendingEnhancement && pendingEnhancement.enhanced === composerText) {
			isEnhancedSend = true;
			if (!sentSkillsForUser.includes('enhance-prompt')) {
				sentSkillsForUser.push('enhance-prompt');
			}
			enhancementOriginals = {
				...enhancementOriginals,
				[composerText]: pendingEnhancement.original
			};
		}

		// Optimistically append the user message; the persisted row will
		// supersede it once the start frame arrives.
		const optimisticUserId = `optimistic-${Date.now()}`;
		const userMsg: Message = {
			id: optimisticUserId,
			chat_id: chat.id,
			role: 'user',
			content: composerText,
			applied_skills: sentSkillsForUser,
			is_enhanced: isEnhancedSend,
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

		// Wave D.2 Task 7.2 — send via the rich `attached_skills` shape so
		// per-attachment provenance (slash vs picker) reaches the backend
		// for receipts/audit attribution. The legacy `skills: list[str]`
		// field is dropped — both formats are accepted in parallel by the
		// API (api/app/schemas/chats.py: AttachedSkillRef + dedupe), and
		// `attached_skills` is the canonical Wave D.2 surface. Slugs not
		// in `attachmentSources` (defensive — shouldn't happen since
		// attachSkill() seeds 'picker') fall back to 'picker' so audit
		// records always carry a source.
		const attachedSkillsPayload = sentSkillsForUser.map((slug) => ({
			slug,
			source: attachmentSources[slug] ?? 'picker'
		}));

		try {
			const res = await messagesApi.sendMessageStream(
				chat.id,
				{
					content: composerText,
					model: currentModelId ?? undefined,
					attached_skills:
						attachedSkillsPayload.length > 0 ? attachedSkillsPayload : undefined,
					skill_inputs:
						Object.keys(skillInputs).length > 0
							? (skillInputs as Record<string, Record<string, unknown>>)
							: undefined,
					stream: true
				},
				streamAbort.signal
			);
			composerText = '';
			// Clear the pending-enhancement marker now that the send is in
			// flight. The enhancementOriginals map keeps the captured
			// original keyed by content so the pill's tap-to-diff still
			// resolves it after the user types another message.
			pendingEnhancement = null;

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
		// Navigate to the skill detail page so the user can read the source,
		// fork it, or try it. A richer in-chat skill-inspector side panel is
		// a future-release item (DE-012); detail-page navigation gives users
		// the same answer ("what is this skill?") without modal noise.
		void goto(`/lq-ai/skills/${encodeURIComponent(name)}`);
	}

	// T6 — Enhance Prompt callbacks. The panel is mounted inline below the
	// composer; parent owns composerText so the panel never reaches into the DOM.
	function handleUseEnhanced(enhanced: string, _interactionId: string): void {
		// Capture the original (current composer text) BEFORE replacing it so
		// the diff modal can show what the user originally typed. T20 deferral
		// A+B follow-on.
		pendingEnhancement = { original: composerText, enhanced };
		composerText = enhanced;
	}

	function handleEditEnhanced(enhanced: string, _interactionId: string): void {
		// Same capture — operator may still send the (possibly hand-edited)
		// enhanced text. We record the AI-generated baseline; if the operator
		// edits further the diff view shows the AI's enhanced version, which
		// is the right reference for "what did the skill change about my
		// prompt" rather than "what did I subsequently tweak."
		pendingEnhancement = { original: composerText, enhanced };
		composerText = enhanced;
	}

	function handleKeepOriginal(_interactionId: string | null): void {
		// composerText stays; clear any pending enhancement so a subsequent
		// send doesn't falsely mark the message as enhanced.
		pendingEnhancement = null;
	}

	function handleEnhanceDismiss(): void {
		// Panel closed by X; no composerText change needed. Clear the
		// pending-enhancement record so an out-of-band close doesn't
		// leak into a subsequent send.
		pendingEnhancement = null;
	}

	function handleComposerKeydown(e: KeyboardEvent): void {
		// When the slash popover is open it owns Arrow/Enter/Escape via its
		// own <svelte:window on:keydown>, which stopPropagation()s. Those
		// keystrokes don't reach this handler. We only need to prevent the
		// composer's own shortcuts (Cmd/Ctrl+E) from firing while the
		// popover is open so the operator can finish skill selection
		// without accidentally launching Enhance Prompt.
		if (slashOpen) return;
		if ((e.metaKey || e.ctrlKey) && e.key === 'e') {
			e.preventDefault();
			expansionPanel?.open();
		}
	}

	// Wave D.2 Task 7.1 — slash-invocation popover wiring.
	//
	// `slashOpen` is the visibility flag for <SlashPopover>; when true the
	// popover is mounted and steals Arrow/Enter/Escape via its own window
	// keydown listener. `slashQuery` is the live query passed to the
	// popover (it re-fetches on change). `slashStartIndex` is the position
	// of the leading `/` in `composerText` — captured so onSlashSelect()
	// can splice it out cleanly when the user picks a result.
	//
	// Detection runs on every input event. The plan-text snippet's
	// detection logic lives in the module-scope `detectSlashAt` helper at
	// the top of this file so it's unit-testable.
	let slashOpen = false;
	let slashQuery = '';
	let slashStartIndex = -1;

	function onComposerInput(e: Event): void {
		const ta = e.target as HTMLTextAreaElement;
		// `bind:value` has already updated `composerText` before this
		// handler fires; we read from the textarea directly anyway so the
		// caret position and value are guaranteed consistent.
		const detection = detectSlashAt(ta.value, ta.selectionStart);
		if (detection.open) {
			slashOpen = true;
			slashQuery = detection.query;
			slashStartIndex = detection.slashIndex;
		} else {
			slashOpen = false;
			slashQuery = '';
			slashStartIndex = -1;
		}
	}

	function onSlashSelect(item: SkillAutocompleteItem): void {
		// Splice the "/<query>" fragment out of the composer text. The
		// before/after slices use the captured slashStartIndex (rather
		// than re-detecting) so a race with concurrent typing can't
		// remove the wrong span.
		if (slashStartIndex >= 0) {
			const before = composerText.slice(0, slashStartIndex);
			const after = composerText.slice(slashStartIndex + 1 + slashQuery.length);
			composerText = (before + after).replace(/^\s*/, '');
		}
		// Attach via the existing handler so the SkillPicker UI + the
		// send-handler's `attachedSkillNames` list pick up the selection.
		// Wave D.2 Task 7.2 — pre-tag the slug with 'slash' BEFORE
		// attachSkill() runs so its default-to-'picker' guard sees an
		// existing entry and leaves the slash provenance intact. The
		// send handler reads `attachmentSources` to populate
		// `attached_skills[].source` on the outbound payload.
		attachmentSources = { ...attachmentSources, [item.slug]: 'slash' };
		void attachSkill(item.slug);
		slashOpen = false;
		slashQuery = '';
		slashStartIndex = -1;
	}

	function onSlashDismiss(): void {
		slashOpen = false;
		slashQuery = '';
		slashStartIndex = -1;
	}

	onMount(async () => {
		await loadShell();
		if (initialChatId) {
			const found = get(chatsStore).find((c) => c.id === initialChatId);
			if (found) await selectChat(found);
		}
		// One-shot composer prefill — read + clear so a refresh doesn't
		// re-prefill. Used by the standalone /lq-ai/saved-prompts page when
		// the user clicks "Use in chat" on a saved prompt. sessionStorage
		// (not URL) keeps prompt content out of referrers + browser history.
		if (typeof window !== 'undefined' && window.sessionStorage) {
			const stash = window.sessionStorage.getItem('lq-ai:composer-prefill');
			if (stash) {
				window.sessionStorage.removeItem('lq-ai:composer-prefill');
				composerText = stash;
			}
		}
	});

	$: groups = $chatsByProject;
	$: filteredGroups = projectIdFilter
		? groups.filter((g) => g.project?.id === projectIdFilter)
		: activeProject
			? groups.filter((g) => g.project?.id === activeProject?.id)
			: groups;
	$: activeChat = $activeChatStore;
	$: messages = $messagesStore;
	$: projectAttachedSkills = activeChat?.project_id
		? $projectsStore.find((p) => p.id === activeChat?.project_id)?.attached_skill_names ?? []
		: [];

	// T12 — derive the project id + attached-KB ids the AttachKBModal needs.
	// Pulled from the live projects store so an attach that happens via the
	// matter rail (or from another chat in the same matter) reflects in the
	// modal's "currently attached" badge without a manual refresh.
	$: composerProjectId = activeChat?.project_id ?? null;
	$: composerAttachedKbIds = composerProjectId
		? $projectsStore.find((p) => p.id === composerProjectId)?.attached_knowledge_base_ids ?? []
		: [];

	// Wave D.1 T19 — Restore receipts drawer open-state when the active
	// chat changes. Keyed by chat ID so each chat remembers its own drawer
	// state across reloads + chat switches.
	$: if (activeChat?.id) {
		receiptsDrawerOpen = readReceiptsDrawerOpen(activeChat.id);
	}

	// D0 — current selection for the active chat. Falls back to the
	// picker's default (``smart`` if available, else the first row) when
	// the user hasn't picked yet for this chat.
	$: currentModelId = activeChat
		? modelByChat[activeChat.id] ??
		  defaultSelection(groupModels(availableModels))?.id ??
		  null
		: null;

	// Wave D.1 T15 — role for the refusal-bubble override-button gate.
	// Reads from the LQ.AI auth store (auth/store.ts); falls back to
	// 'member' when the session has no role surfaced yet so the override
	// path stays gated. The User.is_admin legacy flag is treated as
	// equivalent to role === 'admin' for back-compat with sessions
	// established before the explicit role column landed.
	$: currentUserRole = (() => {
		const user = $auth.user;
		if (!user) return 'member' as const;
		if (user.role === 'admin' || user.role === 'member' || user.role === 'viewer') {
			return user.role;
		}
		return user.is_admin ? ('admin' as const) : ('member' as const);
	})();

	// AmbientFooter — derive provider/tier from the latest assistant message.
	// Wave B will wire these from a dedicated trust endpoint.
	$: footerProvider = (() => {
		const lastAssistant = [...messages].reverse().find((m) => m.role === 'assistant');
		return lastAssistant?.routed_provider ?? 'no provider';
	})();
	$: footerTier = (() => {
		const lastAssistant = [...messages].reverse().find((m) => m.role === 'assistant');
		return lastAssistant?.routed_inference_tier != null
			? String(lastAssistant.routed_inference_tier)
			: 'default';
	})();

	// §7.1 — long-prompt framing: at >500 word-tokens we shift the ✨ affordance
	// from "Enhance" (expand a short prompt) to "Refine" (tighten/restructure a
	// long prompt). Word-count is a coarse proxy for token-count; sufficient
	// for the title/aria copy since the underlying API call is identical.
	const ENHANCE_REFINE_TOKEN_THRESHOLD = 500;
	$: composerWordCount = composerText.trim() ? composerText.trim().split(/\s+/).length : 0;
	$: enhanceIsRefine = composerWordCount > ENHANCE_REFINE_TOKEN_THRESHOLD;
	$: enhanceButtonTitle = enhanceIsRefine
		? 'Refine prompt with AI (Cmd/Ctrl+E)'
		: 'Enhance with AI (Cmd/Ctrl+E)';
	$: enhanceButtonAriaLabel = enhanceIsRefine ? 'Refine prompt' : 'Enhance prompt';
</script>

<svelte:window bind:innerWidth={viewportWidth} on:keydown={onShellKey} />

<div
	class="relative flex flex-1 h-full min-h-0 overflow-hidden"
	data-testid="lq-ai-chat-shell"
>
	<div
		class={sidebarWrapClass}
		data-testid={isNarrow ? 'lq-ai-sidebar-drawer' : undefined}
		bind:this={sidebarDrawerEl}
		role={isNarrow ? 'dialog' : undefined}
		aria-label={isNarrow ? 'Chat list' : undefined}
		tabindex="-1"
		inert={(isNarrow && !navDrawerOpen) || undefined}
	>
		<ChatSidebar
			groups={filteredGroups}
			activeChatId={activeChat?.id ?? null}
			activeProjectId={activeProject?.id ?? null}
			{archivedToggle}
			hideProjectFilter={!!projectIdFilter}
			onSelectChat={selectChat}
			onNewChat={createNewChat}
			onSelectProject={selectProject}
			onToggleArchived={toggleArchived}
		/>
	</div>

	<section class="flex-1 flex flex-col overflow-hidden min-w-0 bg-background text-foreground">
		<div
			class="px-4 py-2 border-b border-border flex items-center gap-2"
			data-testid="lq-ai-chat-header"
		>
			{#if isNarrow}
				<button
					type="button"
					class="shrink-0 rounded-md px-2 py-1 text-lg leading-none text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
					aria-label="Toggle chat list"
					aria-expanded={navDrawerOpen}
					on:click={toggleNavDrawer}
					data-testid="lq-ai-nav-toggle"
				>
					☰
				</button>
			{/if}
			{#if activeChat}
				<div class="min-w-0 flex-1">
					<h2 class="text-base font-semibold text-foreground truncate">
						{activeChat.title || 'Untitled chat'}
					</h2>
					{#if activeChat.project_id}
						<p class="text-xs text-muted-foreground truncate">
							In project: {$projectsStore.find((p) => p.id === activeChat.project_id)?.name ??
								activeChat.project_id}
						</p>
					{/if}
				</div>
				<div class="flex items-center gap-2 shrink-0">
					{#if messages[messages.length - 1]?.role === 'assistant' && messages[messages.length - 1]?.routed_inference_tier}
						<TierBadge
							tier={messages[messages.length - 1].routed_inference_tier ?? null}
							provider={messages[messages.length - 1].routed_provider ?? null}
						/>
					{/if}
					{#if isNarrow}
						<button
							type="button"
							class="shrink-0 rounded-md px-2 py-1 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
							aria-label="Toggle attached files"
							aria-expanded={filesDrawerOpen}
							on:click={toggleFilesDrawer}
							data-testid="lq-ai-files-toggle"
						>
							Files
						</button>
					{/if}
				</div>
			{:else}
				<h2 class="text-sm text-muted-foreground flex-1">Pick or create a chat to start.</h2>
			{/if}
		</div>

		<MessageList
			{messages}
			{streamingMessageId}
			onAppliedSkillClicked={handleAppliedSkillClicked}
			{currentUserRole}
			onRefusalRerun={handleRefusalRerun}
			onRefusalOverrideRequested={handleRefusalOverrideRequested}
			onRefusalExplainerRequested={handleRefusalExplainerRequested}
			onRetry={handleAssistantRetry}
			{enhancementOriginals}
		/>

		{#if activeChat}
			<div class="border-t border-border p-3 space-y-2" data-testid="lq-ai-composer">
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

				<SavedPromptsPanel
					onInsert={insertIntoComposer}
					onPromptsLoaded={(prompts) => (savedPromptChips = prompts)}
				/>

				<!-- AE7 (ADR-F011) — AI Elements Suggestion starter chips. Shown
				     only on an empty conversation, and ONLY when the user has saved
				     prompts: these are the user's own SavedPrompts (an honest,
				     user-owned source), offered as one-click starters — NOT
				     model-invented follow-ups (no honest source for those exists).
				     The label is the prompt name; clicking fills the composer with
				     its body. The message_count gate avoids a chip flash while a
				     populated chat's messages are still loading (the store is []
				     until the fetch resolves). -->
				{#if messages.length === 0 && (activeChat?.message_count ?? 0) === 0 && savedPromptChips.length > 0}
					<div data-testid="lq-ai-suggestions">
						<Suggestions>
							{#each savedPromptChips as prompt (prompt.id)}
								<Suggestion
									suggestion={prompt.name}
									title={prompt.prompt_text}
									onclick={() => insertIntoComposer(prompt.prompt_text)}
									data-testid="lq-ai-suggestion"
								/>
							{/each}
						</Suggestions>
					</div>
				{/if}

				{#if sendError}
					<div
						class="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-md px-2 py-1"
						data-testid="lq-ai-send-error"
					>
						{sendError}
					</div>
				{/if}

				<!-- AE5 (ADR-F011) — AI Elements Prompt Input: one unified rounded
				     shell holding the textarea + a bottom toolbar (model selector +
				     tools left, submit/stop right). Hand-built (option-2) on our
				     existing composer pipeline; the registry `prompt-input` item is
				     not vendored (it pulls the `ai` SDK transport we reject). -->
				<div class="relative" data-testid="lq-ai-prompt-input">
					<div
						class="rounded-xl border border-input bg-card shadow-sm transition-colors focus-within:border-ring focus-within:ring-1 focus-within:ring-ring"
					>
						<textarea
							class="block w-full resize-none bg-transparent px-3.5 pt-3 pb-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
							rows="3"
							placeholder="Type a message…"
							bind:value={composerText}
							data-testid="lq-ai-composer-input"
							on:keydown={handleComposerKeydown}
							on:input={onComposerInput}
						></textarea>
						<div
							class="flex items-center justify-between gap-1 px-2 pb-2"
							data-testid="lq-ai-prompt-toolbar"
						>
							<div class="flex items-center gap-1">
								<ModelPicker
									models={availableModels}
									selectedId={currentModelId}
									onSelect={selectModel}
									dropUp
								/>
								{#if composerProjectId}
									<button
										type="button"
										class="inline-flex items-center justify-center h-8 w-8 rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-40 disabled:cursor-default"
										aria-label="Attach knowledge base"
										title="Attach a knowledge base to this matter"
										on:click={openAttachKbModal}
										data-testid="lq-ai-attach-kb-btn"
									>
										<Paperclip class="size-4" aria-hidden="true" />
									</button>
								{/if}
								<button
									type="button"
									class="inline-flex items-center justify-center h-8 w-8 rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-40 disabled:cursor-default"
									aria-label={enhanceButtonAriaLabel}
									title={enhanceButtonTitle}
									on:click={() => expansionPanel?.open()}
									disabled={!composerText.trim() || !!streamingMessageId}
									data-testid="lq-ai-enhance-btn"
									data-enhance-mode={enhanceIsRefine ? 'refine' : 'enhance'}
								>
									<Sparkles class="size-4" aria-hidden="true" />
								</button>
								<button
									type="button"
									class="inline-flex items-center justify-center h-8 w-8 rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-40 disabled:cursor-default"
									aria-label="Toggle receipts drawer"
									title="Toggle receipts"
									on:click={() => (receiptsDrawerOpen = !receiptsDrawerOpen)}
									data-testid="lq-ai-receipts-toggle"
								>
									<ScrollText class="size-4" aria-hidden="true" />
								</button>
							</div>
							<div class="flex items-center gap-1">
								{#if streamingMessageId}
									<button
										type="button"
										class="inline-flex items-center gap-1.5 h-8 rounded-lg px-3 text-sm font-medium transition focus-visible:outline-2 focus-visible:outline-ring bg-destructive text-white hover:opacity-90"
										on:click={abortStream}
										aria-label="Stop generating"
										title="Stop generating"
										data-testid="lq-ai-abort-btn"
									>
										<Square class="size-4" aria-hidden="true" />
										<span>Stop</span>
									</button>
								{:else}
									<button
										type="button"
										class="inline-flex items-center gap-1.5 h-8 rounded-lg px-3 text-sm font-medium transition focus-visible:outline-2 focus-visible:outline-ring bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-40 disabled:cursor-default"
										on:click={sendMessage}
										disabled={!composerText.trim()}
										aria-label="Send message"
										title="Send message"
										data-testid="lq-ai-send-btn"
									>
										<Send class="size-4" aria-hidden="true" />
										<span>Send</span>
									</button>
								{/if}
							</div>
						</div>
					</div>
					{#if slashOpen}
						<div class="lq-composer-popover" data-testid="lq-ai-slash-popover-anchor">
							<SlashPopover
								query={slashQuery}
								onSelect={onSlashSelect}
								onDismiss={onSlashDismiss}
							/>
						</div>
					{/if}
				</div>

				<EnhancePromptExpansion
					bind:this={expansionPanel}
					originalText={composerText}
					chatId={activeChat?.id ?? null}
					onUseEnhanced={handleUseEnhanced}
					onEditEnhanced={handleEditEnhanced}
					onKeepOriginal={handleKeepOriginal}
					onDismiss={handleEnhanceDismiss}
				/>
			</div>
		{/if}
		<AmbientFooter provider={footerProvider} tier={footerTier} />
	</section>

	{#if activeChat}
		<div
			class={filesWrapClass}
			data-testid={isNarrow ? 'lq-ai-files-drawer' : undefined}
			bind:this={filesDrawerEl}
			role={isNarrow ? 'dialog' : undefined}
			aria-label={isNarrow ? 'Attached files' : undefined}
			tabindex="-1"
			inert={(isNarrow && !filesDrawerOpen) || undefined}
		>
			<AttachedFilesPanel
				{chatFiles}
				{projectFiles}
				{uploading}
				onUpload={uploadAttached}
				onDetach={detachFile}
			/>
		</div>
	{/if}

	{#if activeChat && receiptsDrawerOpen}
		<ReceiptsDrawer
			bind:open={receiptsDrawerOpen}
			chatId={activeChat.id}
			onClose={() => (receiptsDrawerOpen = false)}
		/>
	{/if}

	{#if isNarrow && (navDrawerOpen || filesDrawerOpen)}
		<!-- Shared scrim: tokenised wash (never a black sheet); closes whichever
		     drawer is open. Escape also closes (onShellKey). -->
		<button
			type="button"
			class="absolute inset-0 z-30 cursor-default bg-foreground/20"
			aria-label="Close panel"
			data-testid="lq-ai-chat-scrim"
			transition:fade={{ duration: motionMs(120) }}
			on:click={closeDrawers}
		></button>
	{/if}
</div>

{#if composerProjectId && attachKbModalOpen}
	<AttachKBModal
		bind:open={attachKbModalOpen}
		projectId={composerProjectId}
		attachedKbIds={composerAttachedKbIds}
		onClose={closeAttachKbModal}
		onAttach={handleKbsAttached}
		onDetach={() => {}}
	/>
{/if}

{#if overrideMessage}
	<TierFloorOverrideModal
		bind:open={overrideModalOpen}
		messageId={overrideMessage.id}
		originalTier={overrideMessage.requested_tier ?? 'unknown'}
		enforcedTier={overrideMessage.enforced_tier ?? 'unknown'}
		onClose={closeOverrideModal}
		onSuccess={handleOverrideSuccess}
	/>
{/if}

<style>
	/* AE5 (ADR-F011): ChatPanel's shell + composer now use semantic tokens
	   (bg-background/border-border/bg-card/bg-primary…), which are driven by
	   the `.dark` class and so render correctly in dark mode — this replaces
	   the legacy `--lq-*` composer styles whose dark values weren't resolving
	   on the chat column (the standing dark-mode column gap). The only scoped
	   rule left is the slash-popover anchor positioning. */
	.lq-composer-popover {
		position: absolute;
		bottom: calc(100% + 4px);
		left: 0;
		z-index: 50;
	}
</style>
