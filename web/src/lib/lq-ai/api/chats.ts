/**
 * /api/v1/chats — list / create / get / patch / delete.
 */
import { apiRequest } from './client';
import type { Chat, ChatCreate, ChatUpdate, PaginatedChats } from '../types';

export interface ListChatsOptions {
	project_id?: string;
	archived?: boolean;
	cursor?: string;
	limit?: number;
}

/** GET /api/v1/chats — cursor-paginated. */
export async function listChats(opts: ListChatsOptions = {}): Promise<PaginatedChats> {
	const params = new URLSearchParams();
	if (opts.project_id) params.set('project_id', opts.project_id);
	if (opts.archived) params.set('archived', 'true');
	if (opts.cursor) params.set('cursor', opts.cursor);
	if (opts.limit) params.set('limit', String(opts.limit));
	const qs = params.toString();
	return apiRequest<PaginatedChats>(`/chats${qs ? `?${qs}` : ''}`);
}

/** Helper: pages through `/chats` until the cursor is exhausted (M1 sidebar use). */
export async function listAllChats(opts: ListChatsOptions = {}): Promise<Chat[]> {
	const all: Chat[] = [];
	let cursor: string | undefined = opts.cursor;
	const limit = opts.limit ?? 100;
	// Hard cap iterations to avoid runaway loops on a misbehaving backend.
	for (let i = 0; i < 100; i += 1) {
		const page: PaginatedChats = await listChats({ ...opts, cursor, limit });
		all.push(...page.items);
		if (!page.next_cursor) break;
		cursor = page.next_cursor;
	}
	return all;
}

/** POST /api/v1/chats */
export async function createChat(body: ChatCreate = {}): Promise<Chat> {
	return apiRequest<Chat>('/chats', { method: 'POST', body });
}

/** GET /api/v1/chats/{id} */
export async function getChat(id: string): Promise<Chat> {
	return apiRequest<Chat>(`/chats/${encodeURIComponent(id)}`);
}

/** PATCH /api/v1/chats/{id} */
export async function patchChat(id: string, body: ChatUpdate): Promise<Chat> {
	return apiRequest<Chat>(`/chats/${encodeURIComponent(id)}`, { method: 'PATCH', body });
}

/** DELETE /api/v1/chats/{id} (soft-delete / archive). */
export async function archiveChat(id: string): Promise<void> {
	await apiRequest<void>(`/chats/${encodeURIComponent(id)}`, { method: 'DELETE' });
}
