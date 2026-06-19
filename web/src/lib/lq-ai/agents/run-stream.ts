/**
 * Pure reducers applying SSE v2 parts onto the polled thread-detail
 * shape — F0-S7.
 *
 * The stream and the poller feed ONE render model
 * (`AgentThreadDetailResponse`): `data-step` parts upsert by row id
 * (the spec's same-id reconciliation — duplicates from replay/DB-tail
 * are idempotent), `data-run` settles the run, the terminal text block
 * carries the settled final answer. Every function returns fresh
 * objects (Svelte reactivity is assignment-driven).
 */
import type {
	AgentRunStatus,
	AgentRunStep,
	AgentRunStepKind,
	AgentThreadDetailResponse
} from '$lib/lq-ai/api/agents';

/** The `data-step` part payload — mirrors one settled agent_run_steps row. */
export interface StreamStepPayload {
	id: string;
	run_id: string;
	seq: number;
	kind: AgentRunStepKind;
	name: string | null;
	summary: string | null;
	/** Innermost ancestor tool dispatch — subagent identity (F0-S7). */
	parent_step_id: string | null;
	created_at: string | null;
}

/** The `data-run` part payload — the run's settled terminal state. */
export interface StreamRunPayload {
	status: AgentRunStatus;
	error: string | null;
}

function isStepKind(value: unknown): value is AgentRunStepKind {
	return value === 'model_turn' || value === 'tool_call' || value === 'tool_result';
}

/**
 * Validate a `data-step` part's payload. The stream is server-emitted
 * but still parsed wire input — malformed payloads are dropped (return
 * null), never rendered or thrown on; the poller remains the truth.
 */
export function parseStepPayload(data: unknown): StreamStepPayload | null {
	if (typeof data !== 'object' || data === null) return null;
	const d = data as Record<string, unknown>;
	if (typeof d.id !== 'string' || typeof d.run_id !== 'string') return null;
	if (typeof d.seq !== 'number' || !isStepKind(d.kind)) return null;
	return {
		id: d.id,
		run_id: d.run_id,
		seq: d.seq,
		kind: d.kind,
		name: typeof d.name === 'string' ? d.name : null,
		summary: typeof d.summary === 'string' ? d.summary : null,
		parent_step_id: typeof d.parent_step_id === 'string' ? d.parent_step_id : null,
		created_at: typeof d.created_at === 'string' ? d.created_at : null
	};
}

/**
 * The `data-ropa-change` part payload (PRIV-9b, ADR-F024) — one ROPA register
 * row the agent just changed. Drives the cockpit's live changed-row highlight;
 * nothing durable derives from it (the settled re-read decides — ADR-F004).
 */
export interface RopaChangePayload {
	/** Register table the row lives in: processing_activity | system | vendor. */
	kind: string;
	/** The entity id — matched against the register's `{#each}` row ids. */
	id: string;
	/** create | retire | link | unlink | tag — carried for honesty; v1 wash is verb-agnostic. */
	verb: string;
}

/**
 * Validate a `data-ropa-change` part's payload. Only `id` is load-bearing (the
 * highlight matches rows by id); a malformed frame is dropped (null) and simply
 * doesn't highlight — the poller still carries the true register.
 */
export function parseRopaChangePayload(data: unknown): RopaChangePayload | null {
	if (typeof data !== 'object' || data === null) return null;
	const d = data as Record<string, unknown>;
	if (typeof d.id !== 'string' || d.id === '') return null;
	return {
		kind: typeof d.kind === 'string' ? d.kind : '',
		id: d.id,
		verb: typeof d.verb === 'string' ? d.verb : ''
	};
}

/** Validate a `data-run` part's payload (see parseStepPayload). */
export function parseRunPayload(data: unknown): StreamRunPayload | null {
	if (typeof data !== 'object' || data === null) return null;
	const d = data as Record<string, unknown>;
	const status = d.status;
	if (
		status !== 'running' &&
		status !== 'completed' &&
		status !== 'failed' &&
		status !== 'cancelled' &&
		status !== 'cap_exceeded'
	) {
		return null;
	}
	return { status, error: typeof d.error === 'string' ? d.error : null };
}

function toStep(payload: StreamStepPayload): AgentRunStep {
	return {
		id: payload.id,
		run_id: payload.run_id,
		seq: payload.seq,
		kind: payload.kind,
		name: payload.name,
		summary: payload.summary,
		parent_step_id: payload.parent_step_id,
		// The wire payload always carries the persisted timestamp; the
		// fallback keeps the type honest without inventing a render value.
		created_at: payload.created_at ?? ''
	};
}

/**
 * Upsert one settled step into its run's turn: replace by row id, else
 * insert in `seq` order. A payload for a run the detail doesn't hold
 * (yet) is dropped — the reconcile fetch will carry it.
 */
export function applyStepPart(
	detail: AgentThreadDetailResponse,
	payload: StreamStepPayload
): AgentThreadDetailResponse {
	const runIdx = detail.runs.findIndex((r) => r.run.id === payload.run_id);
	if (runIdx === -1) return detail;
	const turn = detail.runs[runIdx];
	const step = toStep(payload);
	const existing = turn.steps.findIndex((s) => s.id === step.id || s.seq === step.seq);
	const steps =
		existing !== -1
			? turn.steps.map((s, i) => (i === existing ? step : s))
			: [...turn.steps, step].sort((a, b) => a.seq - b.seq);
	const runs = detail.runs.map((r, i) => (i === runIdx ? { ...r, steps } : r));
	return { ...detail, runs };
}

/**
 * Settle a run from the `data-run` part. `continuable` stays UNCHANGED
 * — it is the server's advisory composite (checkpoint existence etc.);
 * the post-stream reconcile fetch refreshes it honestly.
 */
export function applyRunPart(
	detail: AgentThreadDetailResponse,
	runId: string,
	payload: StreamRunPayload
): AgentThreadDetailResponse {
	const runs = detail.runs.map((r) =>
		r.run.id === runId
			? { ...r, run: { ...r.run, status: payload.status, error: payload.error } }
			: r
	);
	return { ...detail, runs };
}

/**
 * Set a run's final answer from the terminal text block. The block IS
 * the settled `final_answer` (the emitter builds it from the run row,
 * never from parsing turns) — rendering it before the reconcile fetch
 * is still settled-rows-decide (ADR-F004).
 */
export function applyAnswerText(
	detail: AgentThreadDetailResponse,
	runId: string,
	text: string
): AgentThreadDetailResponse {
	const runs = detail.runs.map((r) =>
		r.run.id === runId ? { ...r, run: { ...r.run, final_answer: text } } : r
	);
	return { ...detail, runs };
}
