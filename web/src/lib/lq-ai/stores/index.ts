/**
 * Reactive stores driving the LQ.AI chat shell.
 *
 * - `projectsStore`: list of the user's active projects (sidebar grouping).
 * - `chatsStore`: list of the user's active chats (sidebar list).
 * - `skillsStore`: list of available skills (skill picker source).
 * - `activeChatStore`: the currently-open chat (header + main pane).
 * - `messagesStore`: messages for the active chat (streaming-aware).
 */
import { writable, derived, type Readable, type Writable } from 'svelte/store';

import type { Chat, Message, Project, SkillSummary } from '../types';

export const projectsStore: Writable<Project[]> = writable([]);
export const chatsStore: Writable<Chat[]> = writable([]);
export const skillsStore: Writable<SkillSummary[]> = writable([]);
export const activeChatStore: Writable<Chat | null> = writable(null);
export const messagesStore: Writable<Message[]> = writable([]);

/** Group active chats by project, with a synthetic "no project" bucket. */
export const chatsByProject: Readable<Array<{ project: Project | null; chats: Chat[] }>> = derived(
	[chatsStore, projectsStore],
	([$chats, $projects]) => {
		const byId = new Map<string, Project>();
		for (const p of $projects) byId.set(p.id, p);

		const groups = new Map<string | null, Chat[]>();
		for (const chat of $chats) {
			if (chat.archived_at) continue;
			const key = chat.project_id ?? null;
			if (!groups.has(key)) groups.set(key, []);
			groups.get(key)!.push(chat);
		}
		// Stable ordering: projects in the input order; the no-project bucket last.
		const out: Array<{ project: Project | null; chats: Chat[] }> = [];
		for (const p of $projects) {
			const list = groups.get(p.id);
			if (list && list.length > 0) {
				list.sort((a, b) => b.updated_at.localeCompare(a.updated_at));
				out.push({ project: p, chats: list });
			}
		}
		const orphan = groups.get(null);
		if (orphan && orphan.length > 0) {
			orphan.sort((a, b) => b.updated_at.localeCompare(a.updated_at));
			out.push({ project: null, chats: orphan });
		}
		return out;
	}
);
