/**
 * The lawyer's Inbox read API — INTAKE-5a (ADR-F086, plan rulings 1/2/3/7/9).
 *
 * Surface (mirrors `api/app/api/intake_threads.py` + `api/app/schemas/intake.py`
 * field for field):
 *
 *   - GET /api/v1/intake/threads             — the caller's threads, attention first
 *   - GET /api/v1/intake/threads/{id}        — one thread + its emails, oldest first
 *
 * Both are owner-fenced server-side (the thread's matter's owner; an orphaned
 * thread falls back to the mailbox owner) and return 404 — never 403 — for
 * anything the caller does not own. A `project_id` filter the caller does not own
 * matches nothing rather than 404ing, so the filter cannot probe for foreign
 * matters.
 *
 * These shapes DO carry email content (subject, addresses, bodies): plan ruling 9
 * — it is the owner's own post, shown to the owner. Every string here is rendered
 * as TEXT (Svelte interpolation), never `{@html}`, and never logged.
 *
 * Human attach (`POST /intake/threads/{id}/attach`) is INTAKE-5b — deliberately
 * absent here.
 */
import { apiRequest } from './client';

/** One bullet of the agent's account of a thread (`IntakeSummaryItem`).
 *  Both fields are bounded plain single-line text server-side (control
 *  characters and line breaks are REJECTED at write time, not stripped). */
export interface IntakeSummaryItem {
	title: string;
	text: string;
}

/** The matter an intake thread landed in (`IntakeThreadProjectRead`).
 *  Null on the parent field only when the project row was hard-deleted. */
export interface IntakeThreadProject {
	id: string;
	name: string;
	reference: string | null;
	archived: boolean;
}

/** The conversation's live HITL ask, when there is one (`IntakeLiveAskRead`).
 *  The Inbox renders NO approval card of its own (plan ruling 2) — it deep-links
 *  to the conversation where `HitlConfirmCard` already works. */
export interface IntakeLiveAsk {
	run_id: string;
	tool_names: string[];
	allowed_decisions: string[];
}

/** Thread lifecycle (`intake_threads.status` CHECK). */
export type IntakeThreadStatus =
	| 'received'
	| 'processing'
	| 'awaiting_human'
	| 'replied'
	| 'handled'
	| 'error';

/** The agent's closed conclusion (`IntakeOutcome`), null until a run records one. */
export type IntakeOutcome = 'dealt_with' | 'needs_human';

/** Sender-authenticity signal from the provider (`AuthState`). */
export type IntakeAuthState = 'pass' | 'fail' | 'unknown';

/** One row of the Inbox (`IntakeThreadRead`). */
export interface IntakeThread {
	id: string;
	mailbox_address: string;
	/** Single-line neutralised server-side; still rendered as text, never HTML. */
	subject: string;
	status: IntakeThreadStatus | string;
	outcome: IntakeOutcome | string | null;
	label: string | null;
	outcome_note: string | null;
	auth_state: IntakeAuthState | string;
	claimed_reference: string | null;
	summary: IntakeSummaryItem[];
	/** The agent's last run settled without rewriting the summary. */
	summary_stale: boolean;
	message_count: number;
	last_inbound_at: string | null;
	project: IntakeThreadProject | null;
	agent_thread_id: string | null;
	live_ask: IntakeLiveAsk | null;
	/** The error CLASS of the newest failed outbound send — never a provider
	 *  message, body or address. */
	last_send_error: string | null;
	/** Server-computed queue position, ascending (plan ruling 3): 0 = a live ask,
	 *  1 = a failed send, 2 = waiting for a human, 3 = still working, 4 = replied,
	 *  5 = handled. Computed server-side so the UI cannot invent a second,
	 *  disagreeing order. */
	attention_rank: number;
}

export interface IntakeThreadListResponse {
	items: IntakeThread[];
	/** Opaque; pass back as `cursor`. Null on the last page. */
	next_cursor: string | null;
}

/** One email on a thread (`IntakeMessageRead`). */
export interface IntakeMessage {
	id: string;
	/** 'in' = received, 'out' = the approved reply we sent. */
	direction: 'in' | 'out' | string;
	from_addr: string | null;
	to_addrs: string[];
	subject: string | null;
	/** Rendered with `white-space: pre-wrap` — no HTML, no markdown, no link
	 *  activation (plan ruling 9). */
	body_text: string | null;
	attachment_filenames: string[];
	/** Parallel to `attachment_filenames` (same length, same order): the `files`
	 *  row this attachment was ingested into, or null where unresolved. */
	file_ids: (string | null)[];
	provider_timestamp: string | null;
	run_id: string | null;
	send_error: string | null;
}

export interface IntakeThreadDetail {
	thread: IntakeThread;
	/** Oldest first. */
	messages: IntakeMessage[];
	/** True when the chain was longer than the server cap and the newest
	 *  messages were dropped — the reader is told, never silently shortchanged. */
	messages_truncated: boolean;
}

export interface ListIntakeThreadsOptions {
	/** Narrow to one matter's threads (the matter-level Inbox tab). */
	projectId?: string;
	status?: IntakeThreadStatus | string;
	/** Only threads a human is expected to act on (attention ranks 0, 1 and 2). */
	attention?: boolean;
	limit?: number;
	cursor?: string;
}

/** GET /api/v1/intake/threads — one page of the Inbox, attention first. */
export async function listIntakeThreads(
	opts: ListIntakeThreadsOptions = {}
): Promise<IntakeThreadListResponse> {
	const params = new URLSearchParams();
	if (opts.projectId) params.set('project_id', opts.projectId);
	if (opts.status) params.set('status', opts.status);
	if (opts.attention) params.set('attention', 'true');
	if (opts.limit !== undefined) params.set('limit', String(opts.limit));
	if (opts.cursor) params.set('cursor', opts.cursor);
	const qs = params.toString();
	return apiRequest<IntakeThreadListResponse>(`/intake/threads${qs ? `?${qs}` : ''}`);
}

/** GET /api/v1/intake/threads/{id} — the thread plus its emails, oldest first.
 *  404 (never 403) for a thread the caller does not own. */
export async function getIntakeThread(threadId: string): Promise<IntakeThreadDetail> {
	return apiRequest<IntakeThreadDetail>(`/intake/threads/${encodeURIComponent(threadId)}`);
}
