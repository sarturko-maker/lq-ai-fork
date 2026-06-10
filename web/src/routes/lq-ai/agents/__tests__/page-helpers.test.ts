import { describe, expect, it } from 'vitest';
import type { AgentRun, AgentRunStep } from '$lib/lq-ai/api/agents';
import {
	POLL_INTERVAL_MS,
	RAIL_TOOLS,
	STALE_RUNNING_AFTER_MS,
	isStaleRunning,
	railItems,
	railStates,
	shouldContinuePolling,
	splitThink,
	statusBadge,
	stepDisplay
} from '../page-helpers';

const T0 = Date.parse('2026-06-10T12:00:00.000Z');

function makeRun(overrides: Partial<AgentRun> = {}): AgentRun {
	return {
		id: 'run-1',
		user_id: 'user-1',
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
});

describe('railStates', () => {
	it('returns no states for an empty run (everything renders dim)', () => {
		expect(railStates([], null)).toEqual({});
	});

	it('marks a tool active while its call has no result and the run is working', () => {
		const steps = [makeStep({ seq: 1, kind: 'tool_call', name: 'demo_read_clause' })];
		expect(railStates(steps, 'running')['demo_read_clause']).toBe('active');
	});

	it('marks a tool lit once its result lands', () => {
		const steps = [
			makeStep({ seq: 1, kind: 'tool_call', name: 'demo_read_clause' }),
			makeStep({ seq: 2, kind: 'tool_result', name: 'demo_read_clause' })
		];
		expect(railStates(steps, 'running')['demo_read_clause']).toBe('lit');
	});

	it('never shows active on a settled run, even with an unmatched call', () => {
		const steps = [makeStep({ seq: 1, kind: 'tool_call', name: 'demo_read_clause' })];
		expect(railStates(steps, 'failed')['demo_read_clause']).toBe('lit');
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
	it('returns the preview tool universe for an empty run', () => {
		expect(railItems([])).toEqual([...RAIL_TOOLS]);
		expect(RAIL_TOOLS.map((t) => t.name)).toContain('demo_read_clause');
		expect(RAIL_TOOLS.map((t) => t.name)).toContain('task');
	});

	it('appends tools observed in steps that the universe did not predict', () => {
		const steps = [makeStep({ seq: 1, kind: 'tool_call', name: 'surprise_tool' })];
		const items = railItems(steps);
		expect(items.map((t) => t.name)).toContain('surprise_tool');
		expect(items.length).toBe(RAIL_TOOLS.length + 1);
	});

	it('does not duplicate known or repeated tools', () => {
		const steps = [
			makeStep({ seq: 1, kind: 'tool_call', name: 'demo_read_clause' }),
			makeStep({ seq: 2, kind: 'tool_call', name: 'surprise_tool' }),
			makeStep({ seq: 3, kind: 'tool_call', name: 'surprise_tool' })
		];
		expect(railItems(steps).length).toBe(RAIL_TOOLS.length + 1);
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
	it('renders tool calls as monospace with the tool name in the title', () => {
		const d = stepDisplay(
			makeStep({ kind: 'tool_call', name: 'demo_read_clause', summary: '{"topic": "cap"}' })
		);
		expect(d.title).toBe('Tool call — demo_read_clause');
		expect(d.body).toBe('{"topic": "cap"}');
		expect(d.mono).toBe(true);
		expect(d.thinking).toBeNull();
	});

	it('renders tool results as monospace', () => {
		const d = stepDisplay(
			makeStep({ kind: 'tool_result', name: 'demo_read_clause', summary: 'Clause 7.2 …' })
		);
		expect(d.title).toBe('Result — demo_read_clause');
		expect(d.mono).toBe(true);
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
