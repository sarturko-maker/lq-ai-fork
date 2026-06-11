import { describe, expect, it } from 'vitest';
import type { AgentRun, AgentRunStep, AgentThreadDetailResponse } from '$lib/lq-ai/api/agents';
import {
	MATTER_TOOLS,
	MAX_POLL_FAILURES,
	POLL_INTERVAL_MS,
	RAIL_TOOLS,
	STALE_RUNNING_AFTER_MS,
	STEP_SUMMARY_LIMIT,
	composerEnabled,
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

	it('falls back to the raw name for unknown tool calls (never hide what ran)', () => {
		const d = stepDisplay(makeStep({ kind: 'tool_call', name: 'surprise_tool', summary: '{}' }));
		expect(d.title).toBe('Calling surprise_tool…');
	});

	it('renders tool results as monospace with the tool label', () => {
		const d = stepDisplay(
			makeStep({ kind: 'tool_result', name: 'search_documents', summary: 'Top 3 passages…' })
		);
		expect(d.title).toBe('Search documents — result');
		expect(d.mono).toBe(true);
	});

	it('uses the raw name for unknown tool results', () => {
		const d = stepDisplay(makeStep({ kind: 'tool_result', name: 'surprise_tool', summary: 'x' }));
		expect(d.title).toBe('surprise_tool — result');
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
			shouldContinuePollingThread(
				detailWith([live], false),
				T0 + STALE_RUNNING_AFTER_MS + 1000
			)
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

	it('uploadsSettled is true only when every file is ready or failed', () => {
		expect(uploadsSettled([])).toBe(true);
		expect(
			uploadsSettled([{ ingestion_status: 'ready' }, { ingestion_status: 'failed' }])
		).toBe(true);
		expect(uploadsSettled([{ ingestion_status: 'ready' }, { ingestion_status: 'processing' }])).toBe(
			false
		);
		expect(uploadsSettled([{ ingestion_status: 'pending' }])).toBe(false);
		// No status yet (fresh upload response without the field) = not settled.
		expect(uploadsSettled([{ ingestion_status: undefined }])).toBe(false);
	});
});

describe('threadRailStates (F0-S5 review)', () => {
	function detail(
		runs: { run: AgentRun; steps: AgentRunStep[] }[]
	): AgentThreadDetailResponse {
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
