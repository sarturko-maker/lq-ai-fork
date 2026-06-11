/**
 * Pure helpers for the agents conversation surface (F0-S3), in lib since
 * F0-S7 so both the route page and the extracted ConversationPanel
 * component import them; vitest exercises them without the svelte
 * transformer (the playbooks page-helpers pattern).
 */
import type {
	AgentRun,
	AgentRunStatus,
	AgentRunStep,
	AgentThreadDetailResponse
} from '$lib/lq-ai/api/agents';
import type { FileMeta, Project } from '$lib/lq-ai/types';

/**
 * Honest fallback: a conversation can be bound to a matter that is no
 * longer in the active dropdown list (archived since, or the sandbox) —
 * say so rather than dressing the placeholder up as a name (F0-S4 review).
 */
export function matterName(matters: Project[], projectId: string | null): string | null {
	if (!projectId) return null;
	return matters.find((m) => m.id === projectId)?.name ?? 'Matter (not in your active list)';
}

/** Poll cadence while a run is working (~2 s per F0-S3; SSE replaces this in S5). */
export const POLL_INTERVAL_MS = 2000;

/**
 * Consecutive poll failures tolerated before the page gives up and offers
 * a Retry — one dropped request must not orphan a run that is still
 * progressing server-side.
 */
export const MAX_POLL_FAILURES = 3;

/**
 * Cutoff for runs stuck at 'running': the runner's wall-clock budget is
 * 300 s (execute_agent_run default) plus slack for the failure write.
 * BackgroundTasks die with the api process and no recovery sweep exists yet
 * (deferred to the arq migration), so an older 'running' row will never
 * settle — render it stale and stop polling instead of waiting forever.
 */
export const STALE_RUNNING_AFTER_MS = 330_000;

// nowMs vs the server's started_at: since F0-S7 callers pass a
// server-derived 'now' (serverNowMs() in ./server-clock, fed by every API
// response's Date header), so client clock skew no longer fakes staleness.
export function isStaleRunning(run: Pick<AgentRun, 'status' | 'started_at'>, nowMs: number): boolean {
	if (run.status !== 'running') return false;
	const startedMs = Date.parse(run.started_at);
	if (Number.isNaN(startedMs)) return true;
	return nowMs - startedMs > STALE_RUNNING_AFTER_MS;
}

export function shouldContinuePolling(
	run: Pick<AgentRun, 'status' | 'started_at'>,
	nowMs: number
): boolean {
	return run.status === 'running' && !isStaleRunning(run, nowMs);
}

export interface SplitThink {
	/** Concatenated reasoning text, or null when the source has none. */
	thinking: string | null;
	/** The text with `<think>` blocks removed, trimmed. */
	visible: string;
}

/**
 * Split MiniMax-M3-style `<think>…</think>` blocks out of model text so the
 * UI can collapse the reasoning. UI-only: the API record keeps the honest
 * full text (HANDOFF F0-S3). An unclosed trailing `<think>` (run cut
 * mid-thought) is treated as all-reasoning from that point on.
 */
export function splitThink(text: string | null | undefined): SplitThink {
	if (!text) return { thinking: null, visible: '' };
	const parts: string[] = [];
	let visible = text.replace(/<think>([\s\S]*?)<\/think>/g, (_match, inner: string) => {
		parts.push(inner.trim());
		return '';
	});
	const openIdx = visible.indexOf('<think>');
	if (openIdx !== -1) {
		parts.push(visible.slice(openIdx + '<think>'.length).trim());
		visible = visible.slice(0, openIdx);
	}
	// Nested/duplicated openers can strand an orphan closer in the visible
	// text (e.g. '<think>a<think>b</think>c</think>') — never show tag soup.
	visible = visible.replace(/<\/think>/g, '');
	const thinking = parts.filter(Boolean).join('\n\n');
	return { thinking: thinking || null, visible: visible.trim() };
}

export interface RailTool {
	/** Registered tool name as it appears in step rows. */
	name: string;
	label: string;
	hint: string;
}

/**
 * The matter document tools (F0-S4): injected by the API only when the
 * run is bound to a Matter, so the rail shows them only then — the rail
 * is the honest model-visible universe, never an aspiration.
 */
export const MATTER_TOOLS: readonly RailTool[] = [
	{
		name: 'search_documents',
		label: 'Search documents',
		hint: "Full-text search over the matter's documents"
	},
	{ name: 'read_document', label: 'Read document', hint: "One matter document's full text" }
];

/**
 * The deepagents 0.6.8 builtins — always model-visible. Hardcoded this
 * slice; F1 serves the universe from the practice-area config
 * (ADR-F002). Listing everything the model can call — including the
 * disabled shell — is deliberate (CLAUDE.md: transparency is load-bearing).
 */
export const RAIL_TOOLS: readonly RailTool[] = [
	{ name: 'write_todos', label: 'Plan', hint: 'Keep a working plan of subtasks' },
	{ name: 'task', label: 'Subagents', hint: 'Fan work out to a subagent' },
	{ name: 'ls', label: 'List files', hint: 'Agent workspace' },
	{ name: 'read_file', label: 'Read file', hint: 'Agent workspace' },
	{ name: 'write_file', label: 'Write file', hint: 'Agent workspace' },
	{ name: 'edit_file', label: 'Edit file', hint: 'Agent workspace' },
	{ name: 'glob', label: 'Find files', hint: 'Agent workspace' },
	{ name: 'grep', label: 'Search files', hint: 'Agent workspace' },
	{ name: 'execute', label: 'Shell', hint: 'Disabled — no sandbox in the preview' }
];

/**
 * Rail items for a run: the known universe (matter tools first when the
 * run is matter-bound) plus any tool name observed in the steps that we
 * did not predict — never hide what actually ran.
 */
export function railItems(steps: AgentRunStep[], matterBound: boolean): RailTool[] {
	const base = matterBound ? [...MATTER_TOOLS, ...RAIL_TOOLS] : [...RAIL_TOOLS];
	const known = new Set(base.map((t) => t.name));
	const extras: RailTool[] = [];
	for (const step of steps) {
		if (step.kind !== 'tool_call' || !step.name || known.has(step.name)) continue;
		known.add(step.name);
		extras.push({ name: step.name, label: step.name, hint: 'Tool observed in this run' });
	}
	return [...base, ...extras];
}

/** dim = never used · active = call in flight (run still working) · lit = used. */
export type RailState = 'dim' | 'active' | 'lit';

export function railStates(
	steps: AgentRunStep[],
	runStatus: AgentRunStatus | null
): Record<string, RailState> {
	const states: Record<string, RailState> = {};
	const openCalls = new Map<string, number>();
	for (const step of steps) {
		if (!step.name) continue;
		if (step.kind === 'tool_call') {
			states[step.name] = 'lit';
			openCalls.set(step.name, (openCalls.get(step.name) ?? 0) + 1);
		} else if (step.kind === 'tool_result') {
			openCalls.set(step.name, Math.max(0, (openCalls.get(step.name) ?? 0) - 1));
		}
	}
	if (runStatus === 'running') {
		for (const [name, count] of openCalls) {
			if (count > 0) states[name] = 'active';
		}
	}
	return states;
}

export type StatusTone = 'running' | 'ok' | 'warn' | 'error' | 'neutral';

export interface StatusBadge {
	label: string;
	tone: StatusTone;
}

export function statusBadge(
	run: Pick<AgentRun, 'status' | 'started_at' | 'error'>,
	nowMs: number
): StatusBadge {
	if (isStaleRunning(run, nowMs)) return { label: 'Stale', tone: 'warn' };
	switch (run.status) {
		case 'running':
			return { label: 'Working…', tone: 'running' };
		case 'completed':
			return { label: 'Completed', tone: 'ok' };
		case 'failed':
			return run.error === 'timeout'
				? { label: 'Timed out', tone: 'error' }
				: { label: 'Failed', tone: 'error' };
		case 'cancelled':
			return { label: 'Cancelled', tone: 'neutral' };
		case 'cap_exceeded':
			return { label: 'Step cap reached', tone: 'warn' };
	}
}

export interface StepDisplay {
	title: string;
	/** Non-reasoning body text (may be empty). */
	body: string;
	/** Collapsed reasoning for model turns; null otherwise. */
	thinking: string | null;
	/** Render the body in a monospace block (tool args / output digests). */
	mono: boolean;
}

/**
 * Natural-language tool-call titles (maintainer feedback on live S3:
 * "tool calls should use natural language"). UI phrasing only — the raw
 * tool name stays in the step row's `name` and the args in `summary`,
 * shown verbatim in the mono body; the record stays honest.
 */
const TOOL_CALL_TITLES: Record<string, string> = {
	search_documents: "Searching the matter's documents…",
	read_document: 'Reading a matter document…',
	write_todos: 'Updating the plan…',
	task: 'Delegating to a subagent…',
	ls: 'Listing workspace files…',
	read_file: 'Reading a workspace file…',
	write_file: 'Writing a workspace file…',
	edit_file: 'Editing a workspace file…',
	glob: 'Finding workspace files…',
	grep: 'Searching workspace files…',
	execute: 'Running a shell command…'
};

function toolLabel(name: string): string {
	const known = [...MATTER_TOOLS, ...RAIL_TOOLS].find((t) => t.name === name);
	return known?.label ?? name;
}

export function stepDisplay(step: AgentRunStep): StepDisplay {
	if (step.kind === 'tool_call') {
		const name = step.name ?? 'unknown';
		return {
			title: TOOL_CALL_TITLES[name] ?? `Calling ${name}…`,
			body: step.summary ?? '',
			thinking: null,
			mono: true
		};
	}
	if (step.kind === 'tool_result') {
		const name = step.name ?? 'unknown';
		return {
			title: `${toolLabel(name)} — result`,
			body: step.summary ?? '',
			thinking: null,
			mono: true
		};
	}
	const { thinking, visible } = splitThink(step.summary);
	return { title: 'Model turn', body: visible, thinking, mono: false };
}

/**
 * Mirror of the runner's step-summary bound (`_SUMMARY_LIMIT` in
 * api/app/agents/runner.py) — needed to recognise the closing model
 * turn, whose summary is the BOUNDED final answer.
 */
export const STEP_SUMMARY_LIMIT = 2000;

function boundedLikeServer(text: string): string {
	// Python's len/slicing count CODE POINTS; JS .length/.slice count
	// UTF-16 units — astral chars (emoji) near the bound would desync the
	// mirror and resurrect the duplicate (F0-S4 review). Array.from
	// iterates code points, matching the server exactly.
	const points = Array.from(text);
	if (points.length <= STEP_SUMMARY_LIMIT) return text;
	return points.slice(0, STEP_SUMMARY_LIMIT - 1).join('') + '…';
}

/**
 * Steps to render: drops the closing model turn when it duplicates the
 * final answer (maintainer feedback on live S3 — the same text rendered
 * twice). UI-only de-dup; the API record keeps every step. The closing
 * turn's summary is exactly the server-bounded final answer, so the
 * comparison is exact, not fuzzy — anything else (e.g. a turn that
 * differs from the answer) still renders.
 */
export function visibleSteps(
	steps: AgentRunStep[],
	run: Pick<AgentRun, 'status' | 'final_answer'> | null
): AgentRunStep[] {
	if (!run || run.status !== 'completed' || !run.final_answer) return steps;
	const last = steps[steps.length - 1];
	if (!last || last.kind !== 'model_turn' || last.summary === null) return steps;
	if (last.summary === boundedLikeServer(run.final_answer)) return steps.slice(0, -1);
	return steps;
}

// ---------------------------------------------------------------------------
// Conversations (F0-S5, ADR-F008)
// ---------------------------------------------------------------------------

/** The conversation's newest run — drives the badge, polling, and the rail. */
export function latestRunOf(detail: AgentThreadDetailResponse | null): AgentRun | null {
	if (!detail || detail.runs.length === 0) return null;
	return detail.runs[detail.runs.length - 1].run;
}

/**
 * Every step across the conversation's runs, in order — the rail's
 * "lit = used in this conversation" universe. The active pulse still
 * comes from the latest run's status via railStates.
 */
export function threadRailSteps(detail: AgentThreadDetailResponse | null): AgentRunStep[] {
	if (!detail) return [];
	return detail.runs.flatMap((r) => r.steps);
}

/**
 * Rail states for a conversation: lit = used anywhere in the thread,
 * but the ACTIVE pulse may only come from the NEWEST run — an unmatched
 * tool_call in an earlier, settled turn must not pulse "in use" forever
 * (F0-S5 review). ``latestStatus`` is the newest run's status with the
 * page's staleness override already applied.
 */
export function threadRailStates(
	detail: AgentThreadDetailResponse | null,
	latestStatus: AgentRunStatus | null
): Record<string, RailState> {
	const lit = railStates(threadRailSteps(detail), null);
	if (!detail || detail.runs.length === 0) return lit;
	const latestSteps = detail.runs[detail.runs.length - 1].steps;
	return { ...lit, ...railStates(latestSteps, latestStatus) };
}

/** Poll the thread while its newest run is still working (and not stale). */
export function shouldContinuePollingThread(
	detail: AgentThreadDetailResponse | null,
	nowMs: number
): boolean {
	const latest = latestRunOf(detail);
	return latest !== null && shouldContinuePolling(latest, nowMs);
}

/**
 * Whether the composer may send right now: a fresh page (no conversation
 * open) always can; an open conversation only when the server says a
 * follow-up would be accepted AND its newest run isn't still working
 * (the advisory `continuable` flag — POST re-checks, ADR-F008).
 */
export function composerEnabled(
	detail: AgentThreadDetailResponse | null,
	nowMs: number
): boolean {
	if (detail === null) return true;
	return detail.continuable && !shouldContinuePollingThread(detail, nowMs);
}

/** All composer uploads settled (ready or failed) — stop the file poller. */
export function uploadsSettled(files: Pick<FileMeta, 'ingestion_status'>[]): boolean {
	return files.every(
		(f) => f.ingestion_status === 'ready' || f.ingestion_status === 'failed'
	);
}
