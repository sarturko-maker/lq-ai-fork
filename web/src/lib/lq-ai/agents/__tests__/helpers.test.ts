import { describe, expect, it } from 'vitest';
import type { AgentRun, AgentRunStep, AgentThreadDetailResponse } from '$lib/lq-ai/api/agents';
import {
	MATTER_TOOLS,
	MAX_POLL_FAILURES,
	POLL_INTERVAL_MS,
	RAIL_TOOLS,
	STALE_RUNNING_AFTER_MS,
	STEP_SUMMARY_LIMIT,
	agentWorking,
	cancellableRunId,
	composerEnabled,
	groupTurnSteps,
	groupTurnTree,
	subagentTypeOf,
	isStaleRunning,
	latestRunOf,
	railItems,
	railStates,
	shouldContinuePolling,
	shouldContinuePollingThread,
	splitThink,
	threadRailStates,
	statusBadge,
	stepDisplay,
	threadRailSteps,
	uploadsSettled,
	visibleSteps
} from '../helpers';

const T0 = Date.parse('2026-06-10T12:00:00.000Z');

function makeRun(overrides: Partial<AgentRun> = {}): AgentRun {
	return {
		id: 'run-1',
		user_id: 'user-1',
		thread_id: 'thread-1',
		project_id: null,
		status: 'running',
		prompt: 'What is the liability cap?',
		final_answer: null,
		model_alias: 'smart',
		purpose: 'agent_loop',
		max_steps: 20,
		started_at: new Date(T0).toISOString(),
		finished_at: null,
		error: null,
		cost_usd: null,
		...overrides
	};
}

function makeStep(overrides: Partial<AgentRunStep> = {}): AgentRunStep {
	return {
		id: `step-${overrides.seq ?? 1}`,
		run_id: 'run-1',
		seq: 1,
		kind: 'model_turn',
		name: null,
		summary: null,
		parent_step_id: null,
		created_at: new Date(T0).toISOString(),
		...overrides
	};
}

describe('splitThink', () => {
	it('passes plain text through untouched', () => {
		expect(splitThink('The cap is 12 months of fees.')).toEqual({
			thinking: null,
			visible: 'The cap is 12 months of fees.'
		});
	});

	it('handles null and empty input', () => {
		expect(splitThink(null)).toEqual({ thinking: null, visible: '' });
		expect(splitThink(undefined)).toEqual({ thinking: null, visible: '' });
		expect(splitThink('')).toEqual({ thinking: null, visible: '' });
	});

	it('extracts a single think block', () => {
		const { thinking, visible } = splitThink('<think>Let me check.</think>\n\nThe cap is X.');
		expect(thinking).toBe('Let me check.');
		expect(visible).toBe('The cap is X.');
	});

	it('concatenates multiple think blocks', () => {
		const { thinking, visible } = splitThink('<think>a</think>mid<think>b</think>end');
		expect(thinking).toBe('a\n\nb');
		expect(visible).toBe('midend');
	});

	it('treats an unclosed trailing think block as all-reasoning', () => {
		const { thinking, visible } = splitThink('Answer first. <think>cut off mid-tho');
		expect(thinking).toBe('cut off mid-tho');
		expect(visible).toBe('Answer first.');
	});

	it('returns empty visible for think-only text', () => {
		const { thinking, visible } = splitThink('<think>only reasoning</think>');
		expect(thinking).toBe('only reasoning');
		expect(visible).toBe('');
	});

	it('never leaks an orphan closer into visible text on nested openers', () => {
		const { visible } = splitThink('<think>a<think>b</think>c</think>');
		expect(visible).not.toContain('</think>');
		expect(visible).not.toContain('<think>');
		expect(visible).toBe('c');
	});
});

describe('staleness', () => {
	it('a fresh running run is not stale and keeps polling', () => {
		const run = makeRun();
		expect(isStaleRunning(run, T0 + 5_000)).toBe(false);
		expect(shouldContinuePolling(run, T0 + 5_000)).toBe(true);
	});

	it('a running run older than the cutoff is stale and stops polling', () => {
		const run = makeRun();
		const later = T0 + STALE_RUNNING_AFTER_MS + 1;
		expect(isStaleRunning(run, later)).toBe(true);
		expect(shouldContinuePolling(run, later)).toBe(false);
	});

	it('terminal runs are never stale and never poll', () => {
		for (const status of ['completed', 'failed', 'cancelled', 'cap_exceeded'] as const) {
			const run = makeRun({ status });
			expect(isStaleRunning(run, T0 + STALE_RUNNING_AFTER_MS * 2)).toBe(false);
			expect(shouldContinuePolling(run, T0)).toBe(false);
		}
	});

	it('an unparseable started_at renders stale rather than polling forever', () => {
		expect(isStaleRunning(makeRun({ started_at: 'not-a-date' }), T0)).toBe(true);
	});

	it('poll cadence is ~2s per the F0-S3 spec', () => {
		expect(POLL_INTERVAL_MS).toBe(2000);
	});

	it('tolerates transient poll failures before giving up', () => {
		expect(MAX_POLL_FAILURES).toBeGreaterThanOrEqual(2);
	});
});

describe('railStates', () => {
	it('returns no states for an empty run (everything renders dim)', () => {
		expect(railStates([], null)).toEqual({});
	});

	it('marks a tool active while its call has no result and the run is working', () => {
		const steps = [makeStep({ seq: 1, kind: 'tool_call', name: 'search_documents' })];
		expect(railStates(steps, 'running')['search_documents']).toBe('active');
	});

	it('marks a tool lit once its result lands', () => {
		const steps = [
			makeStep({ seq: 1, kind: 'tool_call', name: 'search_documents' }),
			makeStep({ seq: 2, kind: 'tool_result', name: 'search_documents' })
		];
		expect(railStates(steps, 'running')['search_documents']).toBe('lit');
	});

	it('never shows active on a settled run, even with an unmatched call', () => {
		const steps = [makeStep({ seq: 1, kind: 'tool_call', name: 'search_documents' })];
		expect(railStates(steps, 'failed')['search_documents']).toBe('lit');
	});

	it('keeps a tool active while one of two overlapping calls is open', () => {
		const steps = [
			makeStep({ seq: 1, kind: 'tool_call', name: 'task' }),
			makeStep({ seq: 2, kind: 'tool_call', name: 'task' }),
			makeStep({ seq: 3, kind: 'tool_result', name: 'task' })
		];
		expect(railStates(steps, 'running')['task']).toBe('active');
	});

	it('ignores model turns (no name)', () => {
		expect(railStates([makeStep({ kind: 'model_turn' })], 'running')).toEqual({});
	});
});

describe('railItems', () => {
	it('returns only the builtins for an unbound run — no demo, no matter tools', () => {
		const names = railItems([], false).map((t) => t.name);
		expect(names).toEqual(RAIL_TOOLS.map((t) => t.name));
		expect(names).not.toContain('demo_read_clause');
		expect(names).not.toContain('search_documents');
		expect(names).toContain('task');
	});

	it('puts the matter document tools first when the run is matter-bound', () => {
		const names = railItems([], true).map((t) => t.name);
		expect(names.slice(0, MATTER_TOOLS.length)).toEqual(['search_documents', 'read_document']);
		expect(names.length).toBe(MATTER_TOOLS.length + RAIL_TOOLS.length);
	});

	it('appends tools observed in steps that the universe did not predict', () => {
		const steps = [makeStep({ seq: 1, kind: 'tool_call', name: 'surprise_tool' })];
		const items = railItems(steps, false);
		expect(items.map((t) => t.name)).toContain('surprise_tool');
		expect(items.length).toBe(RAIL_TOOLS.length + 1);
	});

	it('does not duplicate known or repeated tools', () => {
		const steps = [
			makeStep({ seq: 1, kind: 'tool_call', name: 'search_documents' }),
			makeStep({ seq: 2, kind: 'tool_call', name: 'surprise_tool' }),
			makeStep({ seq: 3, kind: 'tool_call', name: 'surprise_tool' })
		];
		expect(railItems(steps, true).length).toBe(MATTER_TOOLS.length + RAIL_TOOLS.length + 1);
	});

	it('an observed matter tool on an unbound run is still shown (never hide what ran)', () => {
		const steps = [makeStep({ seq: 1, kind: 'tool_call', name: 'search_documents' })];
		expect(railItems(steps, false).map((t) => t.name)).toContain('search_documents');
	});
});

describe('statusBadge', () => {
	it('labels each lifecycle status', () => {
		expect(statusBadge(makeRun(), T0)).toEqual({ label: 'Working…', tone: 'running' });
		expect(statusBadge(makeRun({ status: 'completed' }), T0)).toEqual({
			label: 'Completed',
			tone: 'ok'
		});
		expect(statusBadge(makeRun({ status: 'failed', error: 'boom' }), T0)).toEqual({
			label: 'Failed',
			tone: 'error'
		});
		expect(statusBadge(makeRun({ status: 'cancelled' }), T0)).toEqual({
			label: 'Cancelled',
			tone: 'neutral'
		});
		expect(statusBadge(makeRun({ status: 'cap_exceeded' }), T0)).toEqual({
			label: 'Step cap reached',
			tone: 'warn'
		});
	});

	it('labels a wall-clock timeout distinctly', () => {
		expect(statusBadge(makeRun({ status: 'failed', error: 'timeout' }), T0)).toEqual({
			label: 'Timed out',
			tone: 'error'
		});
	});

	it('overrides a stuck running status with Stale', () => {
		expect(statusBadge(makeRun(), T0 + STALE_RUNNING_AFTER_MS + 1)).toEqual({
			label: 'Stale',
			tone: 'warn'
		});
	});
});

describe('stepDisplay', () => {
	it('renders known tool calls with a natural-language title; args stay verbatim', () => {
		const d = stepDisplay(
			makeStep({ kind: 'tool_call', name: 'search_documents', summary: '{"query": "cap"}' })
		);
		expect(d.title).toBe("Searching the matter's documents…");
		expect(d.body).toBe('{"query": "cap"}');
		expect(d.mono).toBe(true);
		expect(d.thinking).toBeNull();
	});

	it('renders curated titles for the commercial redline tools', () => {
		expect(
			stepDisplay(makeStep({ kind: 'tool_call', name: 'apply_redline', summary: '{}' })).title
		).toBe('Applying a tracked-changes redline…');
		expect(
			stepDisplay(makeStep({ kind: 'tool_call', name: 'preview_redline', summary: '{}' })).title
		).toBe('Reviewing the proposed redline…');
	});

	it('humanizes unknown tool calls into plain language (no raw identifier shown)', () => {
		const d = stepDisplay(makeStep({ kind: 'tool_call', name: 'surprise_tool', summary: '{}' }));
		expect(d.title).toBe('Surprise tool…');
	});

	it('renders tool results as monospace with the tool label', () => {
		const d = stepDisplay(
			makeStep({ kind: 'tool_result', name: 'search_documents', summary: 'Top 3 passages…' })
		);
		expect(d.title).toBe('Search documents — result');
		expect(d.mono).toBe(true);
	});

	it('humanizes the tool label for unknown tool results', () => {
		const d = stepDisplay(makeStep({ kind: 'tool_result', name: 'surprise_tool', summary: 'x' }));
		expect(d.title).toBe('Surprise tool — result');
	});

	it('splits reasoning out of model turns', () => {
		const d = stepDisplay(
			makeStep({ kind: 'model_turn', summary: '<think>check the tool</think>Calling it now.' })
		);
		expect(d.title).toBe('Model turn');
		expect(d.thinking).toBe('check the tool');
		expect(d.body).toBe('Calling it now.');
		expect(d.mono).toBe(false);
	});

	it('handles a null summary', () => {
		const d = stepDisplay(makeStep({ kind: 'model_turn', summary: null }));
		expect(d.body).toBe('');
		expect(d.thinking).toBeNull();
	});
});

describe('visibleSteps', () => {
	const answer = 'The cap is twelve months of fees.';
	const closing = (summary: string) => makeStep({ seq: 4, kind: 'model_turn', summary });
	const earlier = [
		makeStep({ seq: 1, kind: 'model_turn', summary: '[requested tools: search_documents]' }),
		makeStep({ seq: 2, kind: 'tool_call', name: 'search_documents', summary: '{"query":"cap"}' }),
		makeStep({ seq: 3, kind: 'tool_result', name: 'search_documents', summary: 'passages' })
	];

	it('drops the closing model turn when it duplicates the final answer', () => {
		const steps = [...earlier, closing(answer)];
		const run = makeRun({ status: 'completed', final_answer: answer });
		expect(visibleSteps(steps, run).map((s) => s.seq)).toEqual([1, 2, 3]);
	});

	it('drops the bounded closing turn of a long final answer', () => {
		const long = 'a'.repeat(STEP_SUMMARY_LIMIT + 500);
		const bounded = long.slice(0, STEP_SUMMARY_LIMIT - 1) + '…';
		const steps = [...earlier, closing(bounded)];
		const run = makeRun({ status: 'completed', final_answer: long });
		expect(visibleSteps(steps, run)).toHaveLength(3);
	});

	it('dedups astral-character answers (server bounds by code points, not UTF-16 units)', () => {
		const long = '🎉'.repeat(STEP_SUMMARY_LIMIT + 100); // each emoji = 1 code point, 2 UTF-16 units
		const serverBounded =
			Array.from(long)
				.slice(0, STEP_SUMMARY_LIMIT - 1)
				.join('') + '…'; // exactly what the runner's _bounded persists
		const steps = [...earlier, closing(serverBounded)];
		const run = makeRun({ status: 'completed', final_answer: long });
		expect(visibleSteps(steps, run)).toHaveLength(3);
	});

	it('keeps a closing turn that differs from the final answer', () => {
		const steps = [...earlier, closing('something else entirely')];
		const run = makeRun({ status: 'completed', final_answer: answer });
		expect(visibleSteps(steps, run)).toHaveLength(4);
	});

	it('keeps everything when the run is not completed or has no answer', () => {
		const steps = [...earlier, closing(answer)];
		expect(visibleSteps(steps, makeRun({ status: 'running' }))).toHaveLength(4);
		expect(visibleSteps(steps, makeRun({ status: 'completed', final_answer: null }))).toHaveLength(
			4
		);
		expect(visibleSteps(steps, null)).toHaveLength(4);
	});

	it('never drops a non-model-turn tail', () => {
		const steps = [...earlier];
		const run = makeRun({ status: 'completed', final_answer: 'passages' });
		expect(visibleSteps(steps, run)).toHaveLength(3);
	});
});

describe('groupTurnSteps (AE6 Tool+Task pairing)', () => {
	it('pairs an adjacent tool_call + tool_result into one tool row', () => {
		const rows = groupTurnSteps([
			makeStep({ seq: 1, kind: 'tool_call', name: 'search_documents', summary: '{"q":"cap"}' }),
			makeStep({ seq: 2, kind: 'tool_result', name: 'search_documents', summary: 'passages' })
		]);
		expect(rows).toHaveLength(1);
		expect(rows[0]).toMatchObject({ kind: 'tool', name: 'search_documents', nested: false });
		const row = rows[0];
		if (row.kind !== 'tool') throw new Error('expected tool row');
		expect(row.call?.summary).toBe('{"q":"cap"}');
		expect(row.result?.summary).toBe('passages');
		// The row is keyed on the dispatching call so it stays stable as the
		// result settles in (no remount when the pair completes).
		expect(row.id).toBe(rows[0].id);
	});

	it('keeps a model_turn as its own reasoning row, interleaved in order', () => {
		const rows = groupTurnSteps([
			makeStep({ seq: 1, kind: 'model_turn', summary: '<think>plan</think>ok' }),
			makeStep({ seq: 2, kind: 'tool_call', name: 'read_document' }),
			makeStep({ seq: 3, kind: 'tool_result', name: 'read_document' })
		]);
		expect(rows.map((r) => r.kind)).toEqual(['reasoning', 'tool']);
	});

	it('does NOT pair across a name mismatch (back-to-back distinct tools)', () => {
		const rows = groupTurnSteps([
			makeStep({ seq: 1, kind: 'tool_call', name: 'search_documents' }),
			makeStep({ seq: 2, kind: 'tool_call', name: 'read_document' })
		]);
		expect(rows).toHaveLength(2);
		expect(rows.every((r) => r.kind === 'tool')).toBe(true);
		const [a, b] = rows;
		if (a.kind !== 'tool' || b.kind !== 'tool') throw new Error('expected tool rows');
		expect(a.result).toBeNull();
		expect(b.result).toBeNull();
	});

	it('leaves a result unpaired when subagent steps separate it from its call', () => {
		// The `task` dispatch interleaves nested children before its result —
		// adjacency-only pairing keeps the dispatch and its result as separate
		// cards rather than mis-pairing across the nesting.
		const rows = groupTurnSteps([
			makeStep({ seq: 1, kind: 'tool_call', name: 'task' }),
			makeStep({ seq: 2, kind: 'tool_call', name: 'grep', parent_step_id: 'step-1' }),
			makeStep({ seq: 3, kind: 'tool_result', name: 'grep', parent_step_id: 'step-1' }),
			makeStep({ seq: 4, kind: 'tool_result', name: 'task' })
		]);
		// dispatch (call-only) · nested grep pair · dispatch result (orphan)
		expect(rows).toHaveLength(3);
		const [dispatch, nested, orphan] = rows;
		if (dispatch.kind !== 'tool' || nested.kind !== 'tool' || orphan.kind !== 'tool') {
			throw new Error('expected tool rows');
		}
		expect(dispatch).toMatchObject({ name: 'task', nested: false });
		expect(dispatch.result).toBeNull();
		expect(nested).toMatchObject({ name: 'grep', nested: true });
		expect(nested.result?.summary).toBe(null);
		expect(orphan).toMatchObject({ name: 'task', call: null });
		expect(orphan.result?.kind).toBe('tool_result');
	});

	it('returns an empty list for no steps', () => {
		expect(groupTurnSteps([])).toEqual([]);
	});
});

describe('subagentTypeOf (UX-B-5 delegation label)', () => {
	it('parses subagent_type from the task call args digest', () => {
		const call = makeStep({
			kind: 'tool_call',
			name: 'task',
			summary: '{"description": "review the RFQ", "subagent_type": "document-researcher"}'
		});
		expect(subagentTypeOf(call)).toBe('document-researcher');
	});

	it('returns null when absent / no summary / null call', () => {
		expect(subagentTypeOf(makeStep({ kind: 'tool_call', name: 'task', summary: '{}' }))).toBeNull();
		expect(subagentTypeOf(makeStep({ kind: 'tool_call', name: 'task', summary: null }))).toBeNull();
		expect(subagentTypeOf(null)).toBeNull();
	});
});

describe('groupTurnTree (UX-B-5 subagent delegation boundary)', () => {
	it('folds a task call + its nested children + its result into one delegation', () => {
		const rows = groupTurnSteps([
			makeStep({
				seq: 1,
				kind: 'tool_call',
				name: 'task',
				summary: '{"description": "review", "subagent_type": "document-researcher"}'
			}),
			makeStep({ seq: 2, kind: 'tool_call', name: 'grep', parent_step_id: 'step-1' }),
			makeStep({ seq: 3, kind: 'tool_result', name: 'grep', parent_step_id: 'step-1' }),
			makeStep({ seq: 4, kind: 'tool_result', name: 'task' })
		]);
		const segments = groupTurnTree(rows);
		expect(segments).toHaveLength(1);
		const seg = segments[0];
		if (seg.kind !== 'delegation') throw new Error('expected a delegation segment');
		expect(seg.subagentType).toBe('document-researcher');
		// The nested grep call+result paired into ONE child row (adjacency).
		expect(seg.children).toHaveLength(1);
		expect(seg.children[0]).toMatchObject({ kind: 'tool', name: 'grep' });
		// The task's own result (the subagent's return) folds in as the result.
		expect(seg.result?.kind).toBe('tool');
		expect(seg.header.name).toBe('task');
	});

	it('leaves a turn with NO delegation as flat top-level rows (the common case)', () => {
		const rows = groupTurnSteps([
			makeStep({ seq: 1, kind: 'tool_call', name: 'search_documents' }),
			makeStep({ seq: 2, kind: 'tool_result', name: 'search_documents' }),
			makeStep({ seq: 3, kind: 'model_turn', summary: 'here is the answer' })
		]);
		const segments = groupTurnTree(rows);
		expect(segments.every((s) => s.kind === 'row')).toBe(true);
		expect(segments).toHaveLength(2); // paired tool row + reasoning row
	});

	it('keeps an unknown subagent type as null (label degrades, never crashes)', () => {
		const rows = groupTurnSteps([
			makeStep({ seq: 1, kind: 'tool_call', name: 'task', summary: '{"description": "x"}' }),
			makeStep({ seq: 2, kind: 'model_turn', summary: 'inside', parent_step_id: 'step-1' }),
			makeStep({ seq: 3, kind: 'tool_result', name: 'task' })
		]);
		const segments = groupTurnTree(rows);
		const seg = segments[0];
		if (seg.kind !== 'delegation') throw new Error('expected a delegation segment');
		expect(seg.subagentType).toBeNull();
		expect(seg.children).toHaveLength(1);
	});

	it('returns an empty list for no rows', () => {
		expect(groupTurnTree([])).toEqual([]);
	});
});

describe('conversations (F0-S5)', () => {
	function detailWith(
		runs: { run: AgentRun; steps: AgentRunStep[] }[],
		continuable: boolean
	): AgentThreadDetailResponse {
		return {
			thread: {
				id: 'thread-1',
				user_id: 'user-1',
				project_id: null,
				title: 'What is the liability cap?',
				created_at: new Date(T0).toISOString(),
				last_run_at: new Date(T0).toISOString(),
				last_run_status: runs.length ? runs[runs.length - 1].run.status : null
			},
			runs,
			continuable
		};
	}

	it('latestRunOf returns the last run, null for empty/none', () => {
		expect(latestRunOf(null)).toBeNull();
		expect(latestRunOf(detailWith([], false))).toBeNull();
		const first = makeRun({ id: 'run-1', status: 'completed' });
		const second = makeRun({ id: 'run-2' });
		const d = detailWith(
			[
				{ run: first, steps: [] },
				{ run: second, steps: [] }
			],
			false
		);
		expect(latestRunOf(d)?.id).toBe('run-2');
	});

	it('threadRailSteps concatenates steps across runs in conversation order', () => {
		const d = detailWith(
			[
				{
					run: makeRun({ id: 'run-1', status: 'completed' }),
					steps: [makeStep({ seq: 1, kind: 'tool_call', name: 'search_documents' })]
				},
				{
					run: makeRun({ id: 'run-2' }),
					steps: [makeStep({ seq: 1, kind: 'tool_call', name: 'read_document' })]
				}
			],
			false
		);
		expect(threadRailSteps(d).map((s) => s.name)).toEqual(['search_documents', 'read_document']);
		expect(threadRailSteps(null)).toEqual([]);
	});

	it('shouldContinuePollingThread tracks only the newest run', () => {
		const settled = { run: makeRun({ id: 'run-1', status: 'completed' }), steps: [] };
		const live = { run: makeRun({ id: 'run-2', status: 'running' }), steps: [] };
		expect(shouldContinuePollingThread(detailWith([settled, live], false), T0 + 1000)).toBe(true);
		expect(shouldContinuePollingThread(detailWith([live, settled], false), T0 + 1000)).toBe(false);
		expect(shouldContinuePollingThread(null, T0)).toBe(false);
		// A stale 'running' run stops the poll (same cutoff as single runs).
		expect(
			shouldContinuePollingThread(detailWith([live], false), T0 + STALE_RUNNING_AFTER_MS + 1000)
		).toBe(false);
	});

	it('composerEnabled: new chat always; open thread only when continuable and settled', () => {
		expect(composerEnabled(null, T0)).toBe(true);
		const completed = { run: makeRun({ status: 'completed' }), steps: [] };
		expect(composerEnabled(detailWith([completed], true), T0 + 1000)).toBe(true);
		expect(composerEnabled(detailWith([completed], false), T0 + 1000)).toBe(false);
		const running = { run: makeRun({ status: 'running' }), steps: [] };
		expect(composerEnabled(detailWith([running], false), T0 + 1000)).toBe(false);
	});

	it('agentWorking: createRun in flight OR newest run still running (PRIV-9a)', () => {
		// submitting true → working even before a run row exists to poll.
		expect(agentWorking(null, T0, true)).toBe(true);
		// idle new chat, not submitting → not working.
		expect(agentWorking(null, T0, false)).toBe(false);
		const running = { run: makeRun({ status: 'running' }), steps: [] };
		const completed = { run: makeRun({ status: 'completed' }), steps: [] };
		expect(agentWorking(detailWith([running], false), T0 + 1000, false)).toBe(true);
		expect(agentWorking(detailWith([completed], false), T0 + 1000, false)).toBe(false);
		// A stale 'running' run is NOT working (same cutoff as the poll).
		expect(
			agentWorking(detailWith([running], false), T0 + STALE_RUNNING_AFTER_MS + 1000, false)
		).toBe(false);
	});

	it('cancellableRunId: the live stream run, else the newest run iff running (PRIV-9a)', () => {
		const running = { run: makeRun({ id: 'run-2', status: 'running' }), steps: [] };
		const completed = { run: makeRun({ id: 'run-1', status: 'completed' }), steps: [] };
		// Streaming: cancel the streamed run regardless of the polled snapshot.
		expect(cancellableRunId(detailWith([running], false), 'stream-run')).toBe('stream-run');
		// Not streaming: cancel the newest run only when it's actually running.
		expect(cancellableRunId(detailWith([running], false), null)).toBe('run-2');
		expect(cancellableRunId(detailWith([completed], false), null)).toBeNull();
		// Nothing to cancel yet (createRun POST hasn't returned a run to poll).
		expect(cancellableRunId(null, null)).toBeNull();
	});

	it('uploadsSettled is true only when every file is ready or failed', () => {
		expect(uploadsSettled([])).toBe(true);
		expect(uploadsSettled([{ ingestion_status: 'ready' }, { ingestion_status: 'failed' }])).toBe(
			true
		);
		expect(
			uploadsSettled([{ ingestion_status: 'ready' }, { ingestion_status: 'processing' }])
		).toBe(false);
		expect(uploadsSettled([{ ingestion_status: 'pending' }])).toBe(false);
		// No status yet (fresh upload response without the field) = not settled.
		expect(uploadsSettled([{ ingestion_status: undefined }])).toBe(false);
	});
});

describe('threadRailStates (F0-S5 review)', () => {
	function detail(runs: { run: AgentRun; steps: AgentRunStep[] }[]): AgentThreadDetailResponse {
		return {
			thread: {
				id: 'thread-1',
				user_id: 'user-1',
				project_id: null,
				title: 't',
				created_at: new Date(T0).toISOString(),
				last_run_at: new Date(T0).toISOString(),
				last_run_status: null
			},
			runs,
			continuable: false
		};
	}

	it('an unmatched tool_call in an EARLIER settled turn stays lit, never pulses', () => {
		const d = detail([
			{
				run: makeRun({ id: 'run-1', status: 'completed' }),
				steps: [makeStep({ seq: 1, kind: 'tool_call', name: 'search_documents' })]
			},
			{
				run: makeRun({ id: 'run-2', status: 'running' }),
				steps: [makeStep({ seq: 1, kind: 'tool_call', name: 'read_document' })]
			}
		]);
		const states = threadRailStates(d, 'running');
		expect(states['search_documents']).toBe('lit');
		expect(states['read_document']).toBe('active');
	});

	it('settled conversations show everything lit, nothing active', () => {
		const d = detail([
			{
				run: makeRun({ id: 'run-1', status: 'completed' }),
				steps: [makeStep({ seq: 1, kind: 'tool_call', name: 'search_documents' })]
			}
		]);
		expect(threadRailStates(d, 'completed')['search_documents']).toBe('lit');
	});

	it('empty inputs yield no states', () => {
		expect(threadRailStates(null, null)).toEqual({});
	});
});
