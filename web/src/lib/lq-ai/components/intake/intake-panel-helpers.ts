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

/**
 * The grey meta line under a subject. Plan ruling 7: the FIRST summary bullet's
 * text, so the Inbox itself reads as a digest of what the agent understood; the
 * agent's outcome note is the fallback, and a thread the agent has not concluded
 * yet says so honestly instead of showing an empty line.
 */
export function rowMeta(
	thread: Pick<IntakeThread, 'summary' | 'outcome_note' | 'waiting_on'>
): string {
	const first = thread.summary?.[0]?.text?.trim();
	if (first) return first;
	const note = thread.outcome_note?.trim();
	if (note) return note;
	// INTAKE-5a.1: the honest reason an unread thread is unread. A conversation runs
	// one run at a time, so a thread whose sibling is paused on the lawyer is not
	// being read at all — saying it was is the bug this replaces.
	return waitingLine(thread) ?? 'Agent is reading the thread';
}

/**
 * "Waiting for your decision on 'X' before the agent reads this." — or `null` when
 * the server did not say this thread is blocked on a sibling's ask. Server-computed
 * (`waiting_on`); the client never guesses at a queue.
 */
export function waitingLine(thread: Pick<IntakeThread, 'waiting_on'>): string | null {
	const waiting = thread.waiting_on;
	if (!waiting) return null;
	const subject = waiting.subject?.trim() || '(no subject)';
	return `Waiting for your decision on '${subject}' before the agent reads this.`;
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

/** The matter this thread landed in, as the Inbox shows it (mono reference,
 *  else the name, else an honest placeholder for a hard-deleted project). */
export function matterRef(thread: Pick<IntakeThread, 'project'>): string {
	const project = thread.project;
	if (!project) return 'Matter deleted';
	return project.reference?.trim() || project.name;
}

/**
 * The matter as the DETAIL names it: "ORG-COM-0013 · Contoso hosting renewal"
 * (INTAKE-5a.1). The reference is what a person quotes; the name is what the matter
 * IS, and since the agent now writes that name it is worth reading. The LIST keeps
 * the bare reference — beside a subject line the name would say the same thing twice.
 */
export function matterLabel(thread: Pick<IntakeThread, 'project'>): string {
	const project = thread.project;
	if (!project) return 'Matter deleted';
	const reference = project.reference?.trim();
	const name = project.name?.trim();
	if (reference && name) return `${reference} · ${name}`;
	return reference || name || 'Matter';
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
 * them: a full page means "at least this many", which the badge marks with a
 * trailing `+` rather than pretending the page size is the truth. Zero → no badge
 * at all.
 */
export function badgeCount(attentionRows: number, pageSize = 100): string | null {
	if (attentionRows <= 0) return null;
	// A full page is "at least this many", which the badge marks with a `+`; only
	// past 99 does it stop naming the number, because that is where the badge runs
	// out of room. A short probe page therefore reports its own honest count
	// (`5+`), never a borrowed `99+`.
	if (attentionRows < pageSize) return String(attentionRows);
	return attentionRows > 99 ? '99+' : `${attentionRows}+`;
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

/**
 * The "What the agent did" chips (INTAKE-5a.1): outcome, sender check, and the
 * agent's own label when it wrote one. Same shape and the same `TONE_TO_DOT` map as
 * the list's status chip, so nothing here can introduce a colour the design language
 * does not already have. The label is agent text — rendered as text, never HTML.
 */
export function receiptChips(
	thread: Pick<IntakeThread, 'outcome' | 'auth_state' | 'label'>
): IntakeChip[] {
	const chips: { label: string; tone: StatusTone }[] = [
		{ label: outcomeLabel(thread.outcome), tone: outcomeTone(thread.outcome) },
		{ label: authLabel(thread.auth_state), tone: authTone(thread.auth_state) }
	];
	const label = thread.label?.trim();
	if (label) chips.push({ label, tone: 'neutral' });
	return chips.map((chip) => ({ ...chip, dot: TONE_TO_DOT[chip.tone] }));
}

function outcomeTone(outcome: string | null): StatusTone {
	if (outcome === 'dealt_with') return 'ok';
	if (outcome === 'needs_human') return 'warn';
	return 'neutral';
}

function authTone(authState: string): StatusTone {
	if (authState === 'pass') return 'ok';
	if (authState === 'fail') return 'error';
	return 'neutral';
}

/**
 * Whether the outcome note is long enough to clamp. The note is clamped to three
 * lines with a "Show more" toggle; offering that toggle on a one-line note is noise,
 * and measuring the rendered height would mean reading layout in a component that
 * otherwise never touches the DOM. A character budget is the honest approximation:
 * roughly three lines of the note's own column.
 */
export const NOTE_CLAMP_CHARS = 180;

export function noteNeedsClamp(note: string | null): boolean {
	return (note?.trim().length ?? 0) > NOTE_CLAMP_CHARS;
}

/** Statuses that mean a run is (or should be) working this thread right now. */
const UNSETTLED_STATUSES = new Set(['received', 'processing']);

/**
 * Whether "Summarise now" applies (INTAKE-5a.1) — the client half of the endpoint's
 * own refusals, so the lawyer is not offered a button that would 409:
 *
 *  - nothing to backfill if the thread already has a summary;
 *  - nothing to summarise if it never ran (no conversation);
 *  - a live ask on this conversation means the run will write one itself;
 *  - a closed matter composes no binding, so the pass would write nothing.
 *
 * The server re-checks every one of these — this only decides whether to offer it.
 */
export function canSummarise(
	thread: Pick<IntakeThread, 'summary' | 'agent_thread_id' | 'live_ask' | 'status' | 'project'>
): boolean {
	if (thread.summary && thread.summary.length > 0) return false;
	if (!thread.agent_thread_id) return false;
	if (thread.live_ask) return false;
	if (thread.project?.archived) return false;
	return !UNSETTLED_STATUSES.has(thread.status);
}

/** Whose email this is, for a message header. Falls back honestly. */
export function messageSender(
	message: Pick<IntakeMessage, 'direction' | 'from_addr'>,
	mailboxAddress: string
): string {
	if (message.direction === 'out') return `Sent from ${mailboxAddress}`;
	return message.from_addr?.trim() || 'Unknown sender';
}
