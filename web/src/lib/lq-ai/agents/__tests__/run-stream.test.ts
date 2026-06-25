import { describe, expect, it } from 'vitest';
import type { AgentRun, AgentThreadDetailResponse } from '$lib/lq-ai/api/agents';
import {
	applyAnswerText,
	applyRunPart,
	applyStepPart,
	dealVerdictLabel,
	dealVerdictTone,
	parseDealChangePayload,
	parseRopaChangePayload,
	parseRunPayload,
	parseStepPayload,
	type StreamStepPayload
} from '../run-stream';

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
		started_at: '2026-06-11T12:00:00.000Z',
		finished_at: null,
		error: null,
		cost_usd: null,
		...overrides
	};
}

function makeDetail(): AgentThreadDetailResponse {
	return {
		thread: {
			id: 'thread-1',
			user_id: 'user-1',
			project_id: null,
			title: 'What is the liability cap?',
			created_at: '2026-06-11T12:00:00.000Z',
			last_run_at: '2026-06-11T12:00:00.000Z',
			last_run_status: 'running'
		},
		runs: [{ run: makeRun(), steps: [] }],
		continuable: false
	};
}

function payload(overrides: Partial<StreamStepPayload> = {}): StreamStepPayload {
	return {
		id: 'step-1',
		run_id: 'run-1',
		seq: 1,
		kind: 'model_turn',
		name: null,
		summary: 'thinking',
		parent_step_id: null,
		created_at: '2026-06-11T12:00:01.000Z',
		...overrides
	};
}

describe('parseStepPayload', () => {
	it('accepts a well-formed payload and carries parent_step_id', () => {
		const parsed = parseStepPayload({
			id: 's1',
			run_id: 'r1',
			seq: 3,
			kind: 'tool_call',
			name: 'task',
			summary: '{"description":"x"}',
			parent_step_id: 's0',
			created_at: '2026-06-11T12:00:00Z'
		});
		expect(parsed).not.toBeNull();
		expect(parsed?.parent_step_id).toBe('s0');
		expect(parsed?.kind).toBe('tool_call');
	});

	it('rejects malformed payloads instead of throwing', () => {
		expect(parseStepPayload(null)).toBeNull();
		expect(parseStepPayload('nope')).toBeNull();
		expect(parseStepPayload({ id: 's1' })).toBeNull();
		expect(parseStepPayload(payload({ kind: 'weird' as never }))).toBeNull();
	});
});

describe('parseRunPayload', () => {
	it('accepts terminal statuses and carries the error', () => {
		expect(parseRunPayload({ status: 'failed', error: 'timeout' })).toEqual({
			status: 'failed',
			error: 'timeout'
		});
	});

	it('rejects unknown statuses', () => {
		expect(parseRunPayload({ status: 'exploded' })).toBeNull();
		expect(parseRunPayload(null)).toBeNull();
	});
});

describe('applyStepPart', () => {
	it('inserts a new step in seq order', () => {
		let detail = makeDetail();
		detail = applyStepPart(
			detail,
			payload({ id: 'step-2', seq: 2, kind: 'tool_call', name: 'task' })
		);
		detail = applyStepPart(detail, payload({ id: 'step-1', seq: 1 }));
		expect(detail.runs[0].steps.map((s) => s.seq)).toEqual([1, 2]);
		expect(detail.runs[0].steps[1].name).toBe('task');
	});

	it('replaces by id — re-emitted parts reconcile, never duplicate', () => {
		let detail = makeDetail();
		detail = applyStepPart(detail, payload({ summary: 'first' }));
		detail = applyStepPart(detail, payload({ summary: 'replayed' }));
		expect(detail.runs[0].steps).toHaveLength(1);
		expect(detail.runs[0].steps[0].summary).toBe('replayed');
	});

	it('replaces by seq when the id differs (poll/stream same-row race)', () => {
		let detail = makeDetail();
		detail = applyStepPart(detail, payload({ id: 'step-a', seq: 1 }));
		detail = applyStepPart(detail, payload({ id: 'step-b', seq: 1, summary: 'newer' }));
		expect(detail.runs[0].steps).toHaveLength(1);
		expect(detail.runs[0].steps[0].summary).toBe('newer');
	});

	it('drops payloads for runs the detail does not hold', () => {
		const detail = makeDetail();
		const next = applyStepPart(detail, payload({ run_id: 'run-unknown' }));
		expect(next).toBe(detail);
	});

	it('does not mutate the input detail', () => {
		const detail = makeDetail();
		applyStepPart(detail, payload());
		expect(detail.runs[0].steps).toHaveLength(0);
	});
});

describe('applyRunPart / applyAnswerText', () => {
	it('settles status and error on the addressed run only', () => {
		const detail = makeDetail();
		const next = applyRunPart(detail, 'run-1', { status: 'failed', error: 'timeout' });
		expect(next.runs[0].run.status).toBe('failed');
		expect(next.runs[0].run.error).toBe('timeout');
		expect(detail.runs[0].run.status).toBe('running'); // input untouched
	});

	it('leaves continuable for the reconcile fetch to refresh', () => {
		const next = applyRunPart(makeDetail(), 'run-1', { status: 'completed', error: null });
		expect(next.continuable).toBe(false);
	});

	it('sets the final answer from the terminal text block', () => {
		const next = applyAnswerText(makeDetail(), 'run-1', 'Twelve months of fees.');
		expect(next.runs[0].run.final_answer).toBe('Twelve months of fees.');
	});
});

describe('parseRopaChangePayload (PRIV-9b, ADR-F024)', () => {
	it('parses a well-formed change frame', () => {
		expect(parseRopaChangePayload({ kind: 'system', id: 'sys-1', verb: 'create' })).toEqual({
			kind: 'system',
			id: 'sys-1',
			verb: 'create'
		});
	});

	it('keeps id load-bearing and defaults missing kind/verb to empty strings', () => {
		expect(parseRopaChangePayload({ id: 'v-1' })).toEqual({ kind: '', id: 'v-1', verb: '' });
	});

	it('drops a frame with no usable id (no highlight; the poller carries the truth)', () => {
		expect(parseRopaChangePayload({ kind: 'vendor', verb: 'retire' })).toBeNull();
		expect(parseRopaChangePayload({ id: '' })).toBeNull();
		expect(parseRopaChangePayload({ id: 42 })).toBeNull();
		expect(parseRopaChangePayload(null)).toBeNull();
		expect(parseRopaChangePayload('nope')).toBeNull();
	});
});

describe('parseDealChangePayload (C5b-3, ADR-F032)', () => {
	it('parses a well-formed verdict frame for a change and a comment', () => {
		expect(parseDealChangePayload({ ref: 'C1', verdict: 'accept' })).toEqual({
			ref: 'C1',
			verdict: 'accept'
		});
		expect(parseDealChangePayload({ ref: 'Com:2', verdict: 'reply' })).toEqual({
			ref: 'Com:2',
			verdict: 'reply'
		});
	});

	it('drops a frame missing the ref (no chip; the saved .docx carries the truth)', () => {
		expect(parseDealChangePayload({ verdict: 'accept' })).toBeNull();
		expect(parseDealChangePayload({ ref: '', verdict: 'accept' })).toBeNull();
		expect(parseDealChangePayload({ ref: 7, verdict: 'accept' })).toBeNull();
	});

	it('drops a frame whose verdict is missing or outside the taxonomy', () => {
		expect(parseDealChangePayload({ ref: 'C1' })).toBeNull();
		expect(parseDealChangePayload({ ref: 'C1', verdict: 'maybe' })).toBeNull();
		expect(parseDealChangePayload({ ref: 'C1', verdict: 99 })).toBeNull();
		expect(parseDealChangePayload(null)).toBeNull();
		expect(parseDealChangePayload('nope')).toBeNull();
	});

	it('labels and tones every verdict in the closed taxonomy', () => {
		expect(dealVerdictLabel('accept')).toBe('accepted');
		expect(dealVerdictLabel('reject')).toBe('rejected');
		expect(dealVerdictLabel('counter')).toBe('countered');
		expect(dealVerdictLabel('leave_open')).toBe('left open');
		expect(dealVerdictLabel('escalate')).toBe('escalated');
		expect(dealVerdictLabel('reply')).toBe('replied');

		expect(dealVerdictTone('accept')).toBe('positive');
		expect(dealVerdictTone('reject')).toBe('negative');
		expect(dealVerdictTone('counter')).toBe('info');
		expect(dealVerdictTone('reply')).toBe('info');
		expect(dealVerdictTone('escalate')).toBe('warning');
		expect(dealVerdictTone('leave_open')).toBe('neutral');
	});
});
