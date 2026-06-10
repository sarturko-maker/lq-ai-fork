/**
 * /api/v1/agents/runs — create / get / list deep-agent runs.
 *
 * F0-S2 landed the run records; this module is the S3 polling surface
 * (render-deterministic per ADR-F004: the UI reads settled step rows,
 * never a stream — SSE v2 upgrades this in F0-S5). Wire shapes mirror
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
