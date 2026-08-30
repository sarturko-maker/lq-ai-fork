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
	formatHitlArgs,
	editableDraft,
	approvalDecision,
	respondDecision
} from '../HitlConfirmCard.svelte';

/** One `draft_email_reply` pause digest, as the runner writes it (sort_keys). */
function draftSummary(
	args: Record<string, unknown> = {
		body: 'Thanks — we have it.',
		subject: 'Re: NDA',
		to: ['counterparty@example.net']
	},
	allowed: string[] = ['approve', 'edit', 'reject']
): string {
	return JSON.stringify([{ allowed_decisions: allowed, args, tool: 'draft_email_reply' }]);
}

describe('parseHitlActions', () => {
	it('parses the runner digest shape (sort_keys — args before tool)', () => {
		expect(
			parseHitlActions('[{"args":{"recipient":"counterparty"},"tool":"apply_redline"}]')
		).toEqual([
			{ tool: 'apply_redline', args: { recipient: 'counterparty' }, allowedDecisions: [] }
		]);
	});

	it('carries the server-sent allowed_decisions, dropping non-string entries', () => {
		expect(
			parseHitlActions(
				'[{"allowed_decisions":["approve","edit",7],"args":{},"tool":"draft_email_reply"}]'
			)
		).toEqual([
			{ tool: 'draft_email_reply', args: {}, allowedDecisions: ['approve', 'edit'] }
		]);
	});

	it('returns [] for null / non-JSON / a non-array JSON value', () => {
		expect(parseHitlActions(null)).toEqual([]);
		expect(parseHitlActions('{oops')).toEqual([]);
		expect(parseHitlActions('{}')).toEqual([]);
	});

	it('skips an array item that has no string tool', () => {
		expect(parseHitlActions('[{"args":{"x":1}},{"tool":"apply_redline"}]')).toEqual([
			{ tool: 'apply_redline', args: {}, allowedDecisions: [] }
		]);
	});

	it('defaults args to {} when missing or not a plain object', () => {
		expect(
			parseHitlActions('[{"tool":"a"},{"tool":"b","args":[1,2]},{"tool":"c","args":"nope"}]')
		).toEqual([
			{ tool: 'a', args: {}, allowedDecisions: [] },
			{ tool: 'b', args: {}, allowedDecisions: [] },
			{ tool: 'c', args: {}, allowedDecisions: [] }
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

// ---------------------------------------------------------------------------
// INTAKE-4b (ADR-F087): the email-reply review surface.
// ---------------------------------------------------------------------------

describe('editableDraft', () => {
	it('renders the pending draft when the server allows edit', () => {
		expect(editableDraft(parseHitlActions(draftSummary()))).toEqual({
			to: 'counterparty@example.net',
			subject: 'Re: NDA',
			body: 'Thanks — we have it.'
		});
	});

	it('joins several recipients for the read-only "replying to" line', () => {
		const draft = editableDraft(
			parseHitlActions(draftSummary({ body: 'b', subject: 's', to: ['a@x.test', 'b@x.test'] }))
		);
		expect(draft?.to).toBe('a@x.test, b@x.test');
	});

	it('is null when the server did not allow edit (the button would 422)', () => {
		expect(editableDraft(parseHitlActions(draftSummary(undefined, ['approve', 'reject'])))).toBe(
			null
		);
	});

	it('is null for any other tool, and for a pre-F087 digest with no verbs', () => {
		expect(
			editableDraft(parseHitlActions('[{"allowed_decisions":["edit"],"tool":"apply_redline"}]'))
		).toBe(null);
		expect(editableDraft(parseHitlActions('[{"tool":"draft_email_reply","args":{}}]'))).toBe(null);
	});

	it('is null when the turn gated MORE than one call', () => {
		// One decision is fanned across every gated call, so an editor here would
		// silently apply this draft's text to the other call too.
		const summary = JSON.stringify([
			{ allowed_decisions: ['approve', 'edit', 'reject'], args: {}, tool: 'draft_email_reply' },
			{ allowed_decisions: ['approve', 'reject'], args: {}, tool: 'apply_redline' }
		]);
		expect(editableDraft(parseHitlActions(summary))).toBe(null);
	});

	it('tolerates missing / oddly-typed args rather than throwing', () => {
		expect(editableDraft(parseHitlActions(draftSummary({ to: 'solo@x.test' })))).toEqual({
			to: 'solo@x.test',
			subject: '',
			body: ''
		});
		expect(editableDraft(parseHitlActions(draftSummary({ to: 42, subject: null })))).toEqual({
			to: '',
			subject: '',
			body: ''
		});
	});
});

describe('approvalDecision', () => {
	const original = { to: 'a@x.test', subject: 'Re: NDA', body: 'Thanks.' };

	it('is a plain approve when nothing changed (the checkpointed call runs as-is)', () => {
		expect(approvalDecision(original, { ...original })).toEqual({ type: 'approve' });
	});

	it('ignores surrounding whitespace on the subject line', () => {
		expect(
			approvalDecision(original, { ...original, subject: 'Re: NDA ' })
		).toEqual({ type: 'approve' });
	});

	it('never emits a recipients edit — the bridge derives them (ADR-F086/F087)', () => {
		const decision = approvalDecision(original, { ...original, body: 'Changed.' });
		expect(decision).toEqual({ type: 'edit', edited_args: { body: 'Changed.' } });
		expect(JSON.stringify(decision)).not.toContain('"to"');
	});

	it('sends only the changed fields — plus body, which the wire always carries', () => {
		expect(approvalDecision(original, { ...original, subject: 'Re: the NDA' })).toEqual({
			type: 'edit',
			edited_args: { subject: 'Re: the NDA', body: 'Thanks.' }
		});
	});

	it('keeps an edited body verbatim (leading/trailing whitespace is the lawyer’s)', () => {
		expect(approvalDecision(original, { ...original, body: 'Thanks.\n\nBest,\n' })).toEqual({
			type: 'edit',
			edited_args: { body: 'Thanks.\n\nBest,\n' }
		});
	});
});

describe('respondDecision', () => {
	it('is a reject carrying the note (the agent sees it as the tool result)', () => {
		expect(respondDecision('  say we need the DPA first  ')).toEqual({
			type: 'reject',
			message: 'say we need the DPA first'
		});
	});

	it('is a plain refusal when the note is empty', () => {
		expect(respondDecision('   ')).toEqual({ type: 'reject' });
	});
});
