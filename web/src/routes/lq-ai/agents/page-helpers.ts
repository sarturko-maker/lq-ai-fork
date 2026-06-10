/**
 * Pure helpers for the `/lq-ai/agents` page (F0-S3), extracted to a sibling
 * `.ts` file so vitest can exercise them without the svelte transformer
 * (the playbooks page-helpers pattern).
 */
import type { AgentRun, AgentRunStatus, AgentRunStep } from '$lib/lq-ai/api/agents';

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

// TODO(F0-S5): nowMs is the client clock vs the server's started_at — a fast
// client clock (>~5.5 min) would mark fresh runs stale. Acceptable for the
// local-dev preview; derive 'now' from a response header when SSE lands.
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
 * The F0-S3 preview agent's tool universe: the one capability the API
 * injects (api/app/api/agent_runs.py) plus the deepagents 0.6.8 builtins.
 * Hardcoded this slice; F1 serves it from the practice-area config
 * (ADR-F002). Listing everything the model can call — including the
 * disabled shell — is deliberate (CLAUDE.md: transparency is load-bearing).
 */
export const RAIL_TOOLS: readonly RailTool[] = [
	{ name: 'demo_read_clause', label: 'Read clause', hint: 'Fetch contract clause text (preview capability)' },
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
 * Rail items for a run: the known universe plus any tool name observed in
 * the steps that we did not predict — never hide what actually ran.
 */
export function railItems(steps: AgentRunStep[]): RailTool[] {
	const known = new Set(RAIL_TOOLS.map((t) => t.name));
	const extras: RailTool[] = [];
	for (const step of steps) {
		if (step.kind !== 'tool_call' || !step.name || known.has(step.name)) continue;
		known.add(step.name);
		extras.push({ name: step.name, label: step.name, hint: 'Tool observed in this run' });
	}
	return [...RAIL_TOOLS, ...extras];
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

export function stepDisplay(step: AgentRunStep): StepDisplay {
	if (step.kind === 'tool_call') {
		return { title: `Tool call — ${step.name ?? 'unknown'}`, body: step.summary ?? '', thinking: null, mono: true };
	}
	if (step.kind === 'tool_result') {
		return { title: `Result — ${step.name ?? 'unknown'}`, body: step.summary ?? '', thinking: null, mono: true };
	}
	const { thinking, visible } = splitThink(step.summary);
	return { title: 'Model turn', body: visible, thinking, mono: false };
}
