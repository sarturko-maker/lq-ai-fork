/**
 * INTAKE-5a — the Inbox's pure presentation helpers (ADR-F086).
 *
 * The contracts under test are the ones a regression would quietly break:
 * the server's attention rank always dresses to a person's words (never
 * `awaiting_human`), the tones route through the shared `TONE_TO_DOT` map, the
 * row meta reads as a digest, and the matter deep link is the cockpit's own URL
 * codec — not a hand-built string.
 */
import { describe, expect, it } from 'vitest';

import type { IntakeThread } from '$lib/lq-ai/api/intakeThreads';
import {
	attentionChip,
	attentionStripe,
	authLabel,
	badgeCount,
	canSummarise,
	chainSummaryLine,
	emptyCopy,
	filterQuery,
	matterHref,
	matterLabel,
	matterRef,
	messageSender,
	noteNeedsClamp,
	outcomeLabel,
	receiptChips,
	rowMeta,
	summaryState,
	waitingLine
} from '../intake-panel-helpers';

function thread(over: Partial<IntakeThread> = {}): IntakeThread {
	return {
		id: 't-1',
		mailbox_address: 'commercial@example.test',
		subject: 'NDA for Project Atlas',
		status: 'handled',
		outcome: 'dealt_with',
		label: 'nda',
		outcome_note: 'Answered the counterparty.',
		auth_state: 'pass',
		claimed_reference: null,
		summary: [],
		summary_stale: false,
		message_count: 2,
		last_inbound_at: '2026-08-30T09:00:00Z',
		project: { id: 'p-1', name: 'Project Atlas', reference: 'ORG-COM-0011', archived: false },
		agent_thread_id: 'at-1',
		live_ask: null,
		last_send_error: null,
		waiting_on: null,
		attention_rank: 5,
		...over
	};
}

describe('attention chip (the server ranks; the UI only dresses)', () => {
	it.each([
		[0, 'Needs your decision', 'running'],
		[1, 'Send failed', 'failed'],
		[2, 'Needs a human', 'attention'],
		[3, 'In progress', 'running'],
		[4, 'Replied', 'completed'],
		[5, 'Handled', 'cancelled']
	])('rank %i → %s', (rank, label, dot) => {
		const chip = attentionChip(thread({ attention_rank: rank as number }));
		expect(chip.label).toBe(label);
		expect(chip.dot).toBe(dot);
	});

	it('never leaks a raw status enum to a person', () => {
		const chip = attentionChip(thread({ attention_rank: 9, status: 'awaiting_human' }));
		expect(chip.label).toBe('Awaiting human');
		expect(chip.tone).toBe('neutral');
	});
});

describe('attention stripe (the only new visual device)', () => {
	it.each([
		[0, 'brand'],
		[1, 'destructive'],
		[2, 'warning']
	])('rank %i stripes %s', (rank, stripe) => {
		expect(attentionStripe(thread({ attention_rank: rank as number }))).toBe(stripe);
	});

	it('leaves the quiet ranks unstriped', () => {
		for (const rank of [3, 4, 5, 42]) {
			expect(attentionStripe(thread({ attention_rank: rank }))).toBeNull();
		}
	});
});

describe('rowMeta (the list reads as a digest — plan ruling 7)', () => {
	it('prefers the first summary bullet', () => {
		expect(
			rowMeta(
				thread({
					summary: [
						{ title: 'What they want', text: 'A mutual NDA before diligence.' },
						{ title: 'Where it stands', text: 'Waiting on us.' }
					]
				})
			)
		).toBe('A mutual NDA before diligence.');
	});

	it('falls back to the outcome note, then to an honest placeholder', () => {
		expect(rowMeta(thread({ summary: [] }))).toBe('Answered the counterparty.');
		expect(rowMeta(thread({ summary: [], outcome_note: '   ' }))).toBe(
			'Agent is reading the thread'
		);
	});

	it('says what it is actually waiting for rather than pretending to read', () => {
		const waiting = thread({
			summary: [],
			outcome_note: null,
			status: 'received',
			waiting_on: { thread_id: 't-2', subject: 'NDA — please approve the reply' }
		});
		expect(rowMeta(waiting)).toBe(
			"Waiting for your decision on 'NDA — please approve the reply' before the agent reads this."
		);
		// An empty subject is named honestly, never rendered as an empty quote.
		expect(waitingLine(thread({ waiting_on: { thread_id: 't-2', subject: '  ' } }))).toBe(
			"Waiting for your decision on '(no subject)' before the agent reads this."
		);
		expect(waitingLine(thread())).toBeNull();
	});

	it('prefers the agent’s own account over the queue explanation', () => {
		const both = thread({
			summary: [{ title: 'What they want', text: 'A renewal quote.' }],
			waiting_on: { thread_id: 't-2', subject: 'other' }
		});
		expect(rowMeta(both)).toBe('A renewal quote.');
	});
});

describe('the receipt card (INTAKE-5a.1)', () => {
	it('turns outcome, sender check and label into chips on the shared tone map', () => {
		expect(
			receiptChips(thread({ outcome: 'dealt_with', auth_state: 'pass', label: 'nda' }))
		).toEqual([
			{ label: 'Dealt with', tone: 'ok', dot: 'completed' },
			{ label: 'Sender check passed', tone: 'ok', dot: 'completed' },
			{ label: 'nda', tone: 'neutral', dot: 'cancelled' }
		]);
	});

	it('flags a failed sender check and drops an absent label', () => {
		const chips = receiptChips(
			thread({ outcome: 'needs_human', auth_state: 'fail', label: '   ' })
		);
		expect(chips).toEqual([
			{ label: 'Handed to a human', tone: 'warn', dot: 'attention' },
			{ label: 'Sender authentication failed', tone: 'error', dot: 'failed' }
		]);
	});

	it('clamps only a note long enough to need it', () => {
		expect(noteNeedsClamp('Short note.')).toBe(false);
		expect(noteNeedsClamp(null)).toBe(false);
		expect(noteNeedsClamp('x'.repeat(181))).toBe(true);
	});

	it('names the matter as reference AND name, degrading honestly', () => {
		expect(matterLabel(thread())).toBe('ORG-COM-0011 · Project Atlas');
		expect(matterLabel(thread({ project: { ...thread().project!, reference: null } }))).toBe(
			'Project Atlas'
		);
		expect(matterLabel(thread({ project: null }))).toBe('Matter deleted');
		// The LIST keeps the bare reference — the row already shows the subject.
		expect(matterRef(thread())).toBe('ORG-COM-0011');
	});
});

describe('“Summarise now” is offered only where it would work', () => {
	const settled = () => thread({ summary: [], status: 'replied', agent_thread_id: 'at-1' });

	it('is offered for a settled, summary-less thread with a conversation', () => {
		expect(canSummarise(settled())).toBe(true);
	});

	it.each([
		['it already has one', { summary: [{ title: 'a', text: 'b' }] }],
		['it never ran', { agent_thread_id: null }],
		['a decision is live', { live_ask: { run_id: 'r', tool_names: [], allowed_decisions: [] } }],
		[
			'the matter is closed',
			{ project: { id: 'p-1', name: 'n', reference: null, archived: true } }
		],
		['a run is still working it', { status: 'processing' }]
	])('is withheld when %s', (_why, over) => {
		expect(canSummarise({ ...settled(), ...(over as Partial<IntakeThread>) })).toBe(false);
	});
});

describe('summaryState', () => {
	const bullet = [{ title: 'What they want', text: 'An NDA.' }];

	it('is fresh with a summary and no stale flag', () => {
		expect(summaryState(thread({ summary: bullet }))).toBe('fresh');
	});

	it('is stale when the last run settled without rewriting it', () => {
		expect(summaryState(thread({ summary: bullet, summary_stale: true }))).toBe('stale');
	});

	it('is none when there is nothing to show — even if flagged stale', () => {
		expect(summaryState(thread({ summary: [], summary_stale: true }))).toBe('none');
	});
});

describe('deep links go through the cockpit URL codec', () => {
	it('links and names the matter, honestly when it is gone', () => {
		expect(matterHref(thread())).toBe('/lq-ai?matter=p-1');
		expect(matterRef(thread())).toBe('ORG-COM-0011');
		expect(matterRef(thread({ project: { ...thread().project!, reference: null } }))).toBe(
			'Project Atlas'
		);
		expect(matterHref(thread({ project: null }))).toBeNull();
		expect(matterRef(thread({ project: null }))).toBe('Matter deleted');
	});
});

describe('chain summary line', () => {
	it('counts both directions', () => {
		expect(
			chainSummaryLine([
				{ direction: 'in' },
				{ direction: 'out' },
				{ direction: 'in' },
				{ direction: 'in' }
			])
		).toBe('Show the 4 emails · 3 received · 1 sent');
	});

	it('singularises one email', () => {
		expect(chainSummaryLine([{ direction: 'in' }])).toBe('Show the 1 email · 1 received · 0 sent');
	});
});

describe('rail badge', () => {
	it('is absent at zero and exact below the page size', () => {
		expect(badgeCount(0)).toBeNull();
		expect(badgeCount(7)).toBe('7');
	});

	it('marks a full page with a `+` rather than pretending it is the truth', () => {
		// Only past 99 does the badge stop naming the number; a short probe page
		// reports its own honest count, never a borrowed `99+`.
		expect(badgeCount(100)).toBe('99+');
		expect(badgeCount(99, 99)).toBe('99+');
		expect(badgeCount(98, 99)).toBe('98');
		expect(badgeCount(5, 5)).toBe('5+');
	});
});

describe('filters + copy in the user’s voice', () => {
	it('maps segments onto the server query', () => {
		expect(filterQuery('attention')).toEqual({ attention: true });
		expect(filterQuery('handled')).toEqual({ status: 'handled' });
		expect(filterQuery('all')).toEqual({});
	});

	it('says an empty queue is good news', () => {
		expect(emptyCopy('attention')).toBe('Nothing needs you right now.');
		expect(emptyCopy('all')).toBe('No email threads yet.');
	});

	it('never shows a raw outcome or auth enum', () => {
		expect(outcomeLabel('dealt_with')).toBe('Dealt with');
		expect(outcomeLabel('needs_human')).toBe('Handed to a human');
		expect(outcomeLabel(null)).toBe('Not concluded yet');
		expect(authLabel('fail')).toBe('Sender authentication failed');
		expect(authLabel('pass')).toBe('Sender check passed');
		expect(authLabel('unknown')).toBe('Sender check unavailable');
	});
});

describe('message sender attribution', () => {
	it('names the mailbox for what we sent, the sender for what arrived', () => {
		expect(messageSender({ direction: 'out', from_addr: null }, 'commercial@example.test')).toBe(
			'Sent from commercial@example.test'
		);
		expect(messageSender({ direction: 'in', from_addr: 'them@x.test' }, 'us@x.test')).toBe(
			'them@x.test'
		);
		expect(messageSender({ direction: 'in', from_addr: '  ' }, 'us@x.test')).toBe('Unknown sender');
	});
});
