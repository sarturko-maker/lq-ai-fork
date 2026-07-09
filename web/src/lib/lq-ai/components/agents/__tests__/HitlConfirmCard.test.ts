/**
 * Unit tests for the HitlConfirmCard logic helpers (HITL-3, ADR-F071).
 *
 * Mirrors the RefusalMessageBubble pattern: the pure helpers are exported from
 * the component's `<script module>` block and exercised here without a DOM (NO
 * @testing-library/svelte). The Svelte template is glue — it composes these
 * helpers and wires the Approve/Refuse callbacks. The digest is untrusted
 * model/tool output, so these tests pin the DEFENSIVE parsing contract.
 */
import { describe, expect, it } from 'vitest';
import {
	parseHitlActions,
	hitlToolNames,
	hitlAskLine,
	formatHitlArgs
} from '../HitlConfirmCard.svelte';

describe('parseHitlActions', () => {
	it('parses the runner digest shape (sort_keys — args before tool)', () => {
		expect(
			parseHitlActions('[{"args":{"recipient":"counterparty"},"tool":"apply_redline"}]')
		).toEqual([{ tool: 'apply_redline', args: { recipient: 'counterparty' } }]);
	});

	it('returns [] for null / non-JSON / a non-array JSON value', () => {
		expect(parseHitlActions(null)).toEqual([]);
		expect(parseHitlActions('{oops')).toEqual([]);
		expect(parseHitlActions('{}')).toEqual([]);
	});

	it('skips an array item that has no string tool', () => {
		expect(parseHitlActions('[{"args":{"x":1}},{"tool":"apply_redline"}]')).toEqual([
			{ tool: 'apply_redline', args: {} }
		]);
	});

	it('defaults args to {} when missing or not a plain object', () => {
		expect(
			parseHitlActions('[{"tool":"a"},{"tool":"b","args":[1,2]},{"tool":"c","args":"nope"}]')
		).toEqual([
			{ tool: 'a', args: {} },
			{ tool: 'b', args: {} },
			{ tool: 'c', args: {} }
		]);
	});
});

describe('hitlToolNames', () => {
	it("returns the parsed actions' tool names", () => {
		const actions = parseHitlActions(
			'[{"tool":"apply_redline","args":{}},{"tool":"send_email","args":{}}]'
		);
		expect(hitlToolNames(actions, null)).toEqual(['apply_redline', 'send_email']);
	});

	it('falls back to the step name when no actions parsed', () => {
		expect(hitlToolNames([], 'apply_redline')).toEqual(['apply_redline']);
	});

	it('returns [] when there are no actions and no fallback', () => {
		expect(hitlToolNames([], null)).toEqual([]);
	});
});

describe('hitlAskLine', () => {
	it('gives a generic ask with no tools, and distinct non-empty wording for one vs many', () => {
		const generic = hitlAskLine([]);
		const one = hitlAskLine(['apply_redline']);
		const two = hitlAskLine(['apply_redline', 'preview_redline']);
		expect(generic.length).toBeGreaterThan(0);
		expect(one.length).toBeGreaterThan(0);
		expect(two.length).toBeGreaterThan(0);
		// One-action vs many-action phrasing must read differently (without pinning copy).
		expect(two).not.toBe(one);
		expect(generic).not.toBe(one);
	});
});

describe('formatHitlArgs', () => {
	it('returns an empty string for no args', () => {
		expect(formatHitlArgs({})).toBe('');
	});

	it('pretty-prints args as JSON', () => {
		expect(formatHitlArgs({ a: 1 })).toContain('"a": 1');
	});
});
