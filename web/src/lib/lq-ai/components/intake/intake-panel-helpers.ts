/**
 * INTAKE-5a — pure presentation helpers for the lawyer's Inbox (ADR-F086).
 *
 * Framework-free so they are unit-testable without a DOM (the web suite has no
 * `@testing-library/svelte`; the panels themselves are verified live) — the
 * `grids-panel-helpers` precedent.
 *
 * Two rules govern everything here:
 *
 *  - **The order is the server's.** `attention_rank` is computed server-side
 *    (plan ruling 3) precisely so the UI cannot invent a second, disagreeing
 *    queue. These helpers only DRESS a rank; they never re-derive one.
 *  - **Tones route through `TONE_TO_DOT`.** Intake chips reuse the run-status
 *    tone map (plan ruling 8), so an intake dot can never disagree with a run
 *    dot, and no new colour token enters the design language. The only new
 *    visual device is the three attention stripes, which are the existing
 *    brand / destructive / warning tokens.
 *
 * Every string a helper returns is rendered as TEXT by the callers (Svelte
 * interpolation) — never `{@html}`. Subjects, labels, notes, claimed references
 * and summary bullets are all agent- or sender-controlled.
 */
import type { StatusTone } from '$lib/lq-ai/agents/helpers';
import type { IntakeMessage, IntakeThread } from '$lib/lq-ai/api/intakeThreads';
import { cockpitUrl, TONE_TO_DOT } from '$lib/lq-ai/cockpit/helpers';
import type { DotStatus } from '$lib/lq-ai/components/primitives/StatusDot.svelte';

/** The chip a row/detail header shows: a person's words, plus a calm dot. */
export interface IntakeChip {
	label: string;
	tone: StatusTone;
	dot: DotStatus;
}

/** The left stripe on an attention row. `null` = no stripe (transparent). */
export type IntakeStripe = 'brand' | 'destructive' | 'warning' | null;

/**
 * Rank → what a lawyer is told, in their own voice — never `awaiting_human`.
 * Ranks 0–2 are the "attention" set the server's `attention=true` filter returns.
 */
const RANK_CHIP: Record<number, { label: string; tone: StatusTone }> = {
	0: { label: 'Needs your decision', tone: 'running' },
	1: { label: 'Send failed', tone: 'error' },
	2: { label: 'Needs a human', tone: 'warn' },
	3: { label: 'In progress', tone: 'running' },
	4: { label: 'Replied', tone: 'ok' },
	5: { label: 'Handled', tone: 'neutral' }
};

/** Ranks 0, 1 and 2 — the server's own `attention=true` set (plan ruling 3). */
export const ATTENTION_MAX_RANK = 2;

/** Humanise an unexpected status value rather than leaking the enum verbatim. */
function humaniseStatus(status: string): string {
	const words = status.replace(/[_-]+/g, ' ').trim();
	if (!words) return 'Unknown';
	return words.charAt(0).toUpperCase() + words.slice(1);
}

/**
 * The status chip for one thread. Driven by the server's `attention_rank`; an
 * unknown rank (a future widening) falls back to the humanised status rather
 * than rendering nothing — the row must never lose its chip.
 */
export function attentionChip(thread: Pick<IntakeThread, 'attention_rank' | 'status'>): IntakeChip {
	const known = RANK_CHIP[thread.attention_rank];
	const { label, tone } = known ?? { label: humaniseStatus(thread.status), tone: 'neutral' };
	return { label, tone, dot: TONE_TO_DOT[tone] };
}

/**
 * The 3px left stripe: only the three ranks a human is expected to act on carry
 * one, so the Inbox reads as a queue at a glance and the quiet rows stay quiet.
 */
export function attentionStripe(thread: Pick<IntakeThread, 'attention_rank'>): IntakeStripe {
	switch (thread.attention_rank) {
		case 0:
			return 'brand';
		case 1:
			return 'destructive';
		case 2:
			return 'warning';
		default:
			return null;
	}
}

/** True when the server would have returned this row under `attention=true`. */
export function needsAttention(thread: Pick<IntakeThread, 'attention_rank'>): boolean {
	return thread.attention_rank >= 0 && thread.attention_rank <= ATTENTION_MAX_RANK;
}

/**
 * The grey meta line under a subject. Plan ruling 7: the FIRST summary bullet's
 * text, so the Inbox itself reads as a digest of what the agent understood; the
 * agent's outcome note is the fallback, and a thread the agent has not concluded
 * yet says so honestly instead of showing an empty line.
 */
export function rowMeta(thread: Pick<IntakeThread, 'summary' | 'outcome_note'>): string {
	const first = thread.summary?.[0]?.text?.trim();
	if (first) return first;
	const note = thread.outcome_note?.trim();
	if (note) return note;
	return 'Agent is reading the thread';
}

/**
 * Whether the detail opens on the summary, on a flagged-stale summary, or on the
 * email chain. `none` wins over `stale`: a thread that never had a summary has
 * nothing to flag as out of date — it shows the chain expanded instead.
 */
export function summaryState(
	thread: Pick<IntakeThread, 'summary' | 'summary_stale'>
): 'fresh' | 'stale' | 'none' {
	if (!thread.summary || thread.summary.length === 0) return 'none';
	return thread.summary_stale ? 'stale' : 'fresh';
}

/**
 * Deep link into the conversation where the approve/edit/respond card already
 * lives (plan ruling 2 — the Inbox never renders a second approval surface).
 * Null when the thread has no conversation bound (the project was hard-deleted,
 * or the conversation was never created) — the caller disables the button.
 */
export function conversationHref(
	thread: Pick<IntakeThread, 'project' | 'agent_thread_id'>
): string | null {
	if (!thread.agent_thread_id) return null;
	return cockpitUrl({ matter: thread.project?.id ?? null, thread: thread.agent_thread_id });
}

/** The matter this thread landed in, as the Inbox shows it (mono reference,
 *  else the name, else an honest placeholder for a hard-deleted project). */
export function matterRef(thread: Pick<IntakeThread, 'project'>): string {
	const project = thread.project;
	if (!project) return 'Matter deleted';
	return project.reference?.trim() || project.name;
}

/** Deep link to the matter this thread landed in; null when it is gone. */
export function matterHref(thread: Pick<IntakeThread, 'project'>): string | null {
	if (!thread.project) return null;
	return cockpitUrl({ matter: thread.project.id });
}

/** "Show the 4 emails · 3 received · 1 sent" — the collapsed chain's one line. */
export function chainSummaryLine(messages: Pick<IntakeMessage, 'direction'>[]): string {
	const total = messages.length;
	const sent = messages.filter((m) => m.direction === 'out').length;
	const received = total - sent;
	const head = `Show the ${total} email${total === 1 ? '' : 's'}`;
	return `${head} · ${received} received · ${sent} sent`;
}

/**
 * The rail badge for the Inbox nav entry. The list endpoint returns ITEMS, not a
 * count, so the shell asks for one bounded page of attention rows and counts
 * them: a full page means "at least this many", which the badge says as `99+`
 * rather than pretending the page size is the truth. Zero → no badge at all.
 */
export function badgeCount(attentionRows: number, pageSize = 100): string | null {
	if (attentionRows <= 0) return null;
	return attentionRows >= pageSize ? '99+' : String(attentionRows);
}

/** How many rows in a page a human is expected to act on (the segmented
 *  filter's "Needs you" count when the caller already holds the page). */
export function attentionCount(threads: Pick<IntakeThread, 'attention_rank'>[]): number {
	return threads.filter(needsAttention).length;
}

/** The three segments of the Inbox filter, in the user's voice. */
export type InboxFilter = 'attention' | 'all' | 'handled';

export const INBOX_FILTERS: { id: InboxFilter; label: string }[] = [
	{ id: 'attention', label: 'Needs you' },
	{ id: 'all', label: 'All' },
	{ id: 'handled', label: 'Handled' }
];

/** Translate a filter segment into `listIntakeThreads` query options. */
export function filterQuery(filter: InboxFilter): { attention?: boolean; status?: string } {
	switch (filter) {
		case 'attention':
			return { attention: true };
		case 'handled':
			return { status: 'handled' };
		case 'all':
			return {};
	}
}

/** Empty-state copy: an empty "Needs you" is good news, not an absence. */
export function emptyCopy(filter: InboxFilter): string {
	return filter === 'attention' ? 'Nothing needs you right now.' : 'No email threads yet.';
}

/** The agent's closed outcome, in a person's words (never `dealt_with`). */
export function outcomeLabel(outcome: string | null): string {
	if (outcome === 'dealt_with') return 'Dealt with';
	if (outcome === 'needs_human') return 'Handed to a human';
	if (!outcome) return 'Not concluded yet';
	return humaniseStatus(outcome);
}

/**
 * What the provider's sender-authentication check said. `fail` is the one that
 * matters: it is the spoof signal the detail raises as a warning banner BEFORE
 * a human acts on the email (plan ruling 3 / security posture).
 */
export function authLabel(authState: string): string {
	if (authState === 'pass') return 'Sender check passed';
	if (authState === 'fail') return 'Sender authentication failed';
	return 'Sender check unavailable';
}

/** Whose email this is, for a message header. Falls back honestly. */
export function messageSender(
	message: Pick<IntakeMessage, 'direction' | 'from_addr'>,
	mailboxAddress: string
): string {
	if (message.direction === 'out') return `Sent from ${mailboxAddress}`;
	return message.from_addr?.trim() || 'Unknown sender';
}
