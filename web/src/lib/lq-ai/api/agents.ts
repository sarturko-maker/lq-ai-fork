/**
 * /api/v1/agents — deep-agent runs and conversations (threads).
 *
 * F0-S2 landed the run records; S3 made this the polling surface
 * (render-deterministic per ADR-F004: the UI reads settled step rows,
 * never a stream — SSE v2 upgrades this in F0-S7). F0-S5 adds threads
 * (ADR-F008): a conversation = ordered runs sharing durable agent state;
 * the UI polls the thread detail while a run is live. Wire shapes mirror
 * api/app/schemas/agent_runs.py; types are module-local because only the
 * Agents surface consumes them.
 */
import { apiRequest } from './client';

/** Lifecycle of a run (CHECK constraint on agent_runs.status). */
export type AgentRunStatus = 'running' | 'completed' | 'failed' | 'cancelled' | 'cap_exceeded';

/** Observable loop events a step row records. */
export type AgentRunStepKind = 'model_turn' | 'tool_call' | 'tool_result';

export interface AgentRun {
	id: string;
	user_id: string;
	/** The conversation this run belongs to (F0-S5, ADR-F008). */
	thread_id: string;
	/** The Matter this run is bound to; null = blank workspace (F0-S4). */
	project_id: string | null;
	status: AgentRunStatus;
	prompt: string;
	final_answer: string | null;
	model_alias: string;
	purpose: string;
	max_steps: number;
	started_at: string;
	finished_at: string | null;
	error: string | null;
	/** Decimal on the wire; NULL until the F1 R4 cost brake fills it. */
	cost_usd: string | number | null;
}

export interface AgentRunStep {
	id: string;
	run_id: string;
	seq: number;
	kind: AgentRunStepKind;
	/** Tool name; null for model turns. */
	name: string | null;
	/**
	 * Bounded digest (~2000 chars) of the turn / tool args / tool output.
	 * Non-null on the wire today (NOT NULL column); kept nullable
	 * deliberately so a future relaxation can't crash render paths.
	 */
	summary: string | null;
	created_at: string;
}

export interface AgentRunDetailResponse {
	run: AgentRun;
	steps: AgentRunStep[];
}

export interface AgentRunListResponse {
	runs: AgentRun[];
	total_count: number;
	limit: number;
	offset: number;
}

export interface AgentRunCreate {
	prompt: string;
	model_alias?: string;
	max_steps?: number;
	/**
	 * Bind the run to a Matter (F0-S4): the agent gets search_documents /
	 * read_document over the matter's ingested files. Another user's
	 * project id → 404 server-side, never 403.
	 */
	project_id?: string | null;
	/**
	 * Continue this conversation (F0-S5, ADR-F008). The Matter binding is
	 * the THREAD's — omit project_id on follow-ups (422 otherwise). 409
	 * thread_busy / thread_not_continuable when the thread can't take a
	 * follow-up.
	 */
	thread_id?: string | null;
}

export interface AgentThread {
	id: string;
	user_id: string;
	/** The conversation's Matter binding; runs inherit it (ADR-F008). */
	project_id: string | null;
	/** Bounded first prompt until auto-titling lands (F1/F2). */
	title: string;
	created_at: string;
	last_run_at: string;
	/** The NEWEST run's status — the conversation list badge. */
	last_run_status: AgentRunStatus | null;
}

export interface AgentThreadListResponse {
	threads: AgentThread[];
	total_count: number;
	limit: number;
	offset: number;
}

/** One conversation turn: the run plus its steps in seq order. */
export interface AgentRunWithSteps {
	run: AgentRun;
	steps: AgentRunStep[];
}

export interface AgentThreadDetailResponse {
	thread: AgentThread;
	/** Oldest first — conversation order. */
	runs: AgentRunWithSteps[];
	/**
	 * Whether a follow-up would be accepted (latest run completed AND
	 * checkpoint state exists). Advisory — POST re-checks server-side.
	 */
	continuable: boolean;
}

/** POST /api/v1/agents/runs — 202; the run executes in the background. */
export async function createRun(body: AgentRunCreate): Promise<AgentRun> {
	return apiRequest<AgentRun>('/agents/runs', { method: 'POST', body });
}

/** GET /api/v1/agents/runs/{id} — run + steps ordered by seq (the polling contract). */
export async function getRun(id: string): Promise<AgentRunDetailResponse> {
	return apiRequest<AgentRunDetailResponse>(`/agents/runs/${encodeURIComponent(id)}`);
}

/** GET /api/v1/agents/runs — caller's runs, newest first. */
export async function listRuns(
	opts: { limit?: number; offset?: number } = {}
): Promise<AgentRunListResponse> {
	const params = new URLSearchParams();
	if (opts.limit !== undefined) params.set('limit', String(opts.limit));
	if (opts.offset !== undefined) params.set('offset', String(opts.offset));
	const qs = params.toString();
	return apiRequest<AgentRunListResponse>(`/agents/runs${qs ? `?${qs}` : ''}`);
}

/** GET /api/v1/agents/threads — caller's conversations, newest activity first. */
export async function listThreads(
	opts: { limit?: number; offset?: number } = {}
): Promise<AgentThreadListResponse> {
	const params = new URLSearchParams();
	if (opts.limit !== undefined) params.set('limit', String(opts.limit));
	if (opts.offset !== undefined) params.set('offset', String(opts.offset));
	const qs = params.toString();
	return apiRequest<AgentThreadListResponse>(`/agents/threads${qs ? `?${qs}` : ''}`);
}

/** GET /api/v1/agents/threads/{id} — the whole conversation (the polling contract). */
export async function getThread(id: string): Promise<AgentThreadDetailResponse> {
	return apiRequest<AgentThreadDetailResponse>(`/agents/threads/${encodeURIComponent(id)}`);
}
