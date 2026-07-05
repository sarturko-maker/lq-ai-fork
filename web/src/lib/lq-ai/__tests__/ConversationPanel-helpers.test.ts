/**
 * Unit tests for the `buildRunPayload` helper exported from ConversationPanel's
 * `<script module>` block (Svelte 5 idiom — same pattern as DocumentEditorPanel-
 * helpers.test.ts). No DOM or @testing-library/svelte needed: the function is
 * purely computational.
 */
import { describe, expect, it } from 'vitest';
import { buildRunPayload, formatRunCostUSD } from '../components/agents/ConversationPanel.svelte';

const ALL_PROFILES = ['economy', 'balanced', 'generous'] as const;

describe('buildRunPayload — follow-up (detail present)', () => {
	const detail = { thread: { id: 'thread-abc' } };

	it('uses thread_id and omits project_id when detail is provided', () => {
		const payload = buildRunPayload({ prompt: 'hello', budgetProfile: 'balanced', detail });
		expect(payload.thread_id).toBe('thread-abc');
		expect('project_id' in payload).toBe(false);
	});

	it('always includes budget_profile for every explicit profile value', () => {
		for (const profile of ALL_PROFILES) {
			const payload = buildRunPayload({ prompt: 'p', budgetProfile: profile, detail });
			expect(payload.budget_profile).toBe(profile);
		}
	});

	it('OMITS budget_profile for the "" Default option (server resolves — ADR-F063)', () => {
		const payload = buildRunPayload({ prompt: 'p', budgetProfile: '', detail });
		expect('budget_profile' in payload).toBe(false);
		expect(payload.thread_id).toBe('thread-abc');
	});

	it('forwards the prompt exactly', () => {
		const payload = buildRunPayload({
			prompt: 'What is the liability cap?',
			budgetProfile: 'economy',
			detail
		});
		expect(payload.prompt).toBe('What is the liability cap?');
	});
});

describe('buildRunPayload — new conversation (no detail)', () => {
	it('uses project_id and omits thread_id when detail is absent', () => {
		const payload = buildRunPayload({
			prompt: 'hello',
			budgetProfile: 'balanced',
			selectedMatterId: 'proj-1'
		});
		expect(payload.project_id).toBe('proj-1');
		expect('thread_id' in payload).toBe(false);
	});

	it('always includes budget_profile for every explicit profile value', () => {
		for (const profile of ALL_PROFILES) {
			const payload = buildRunPayload({
				prompt: 'p',
				budgetProfile: profile,
				selectedMatterId: 'proj-1'
			});
			expect(payload.budget_profile).toBe(profile);
		}
	});

	it('OMITS budget_profile for the "" Default option (server resolves — ADR-F063)', () => {
		const payload = buildRunPayload({
			prompt: 'p',
			budgetProfile: '',
			selectedMatterId: 'proj-1'
		});
		expect('budget_profile' in payload).toBe(false);
		expect(payload.project_id).toBe('proj-1');
	});

	it('uses null project_id when selectedMatterId is absent', () => {
		const payload = buildRunPayload({ prompt: 'p', budgetProfile: 'generous' });
		expect(payload.project_id).toBeNull();
	});

	it('uses null project_id when selectedMatterId is explicitly null', () => {
		const payload = buildRunPayload({
			prompt: 'p',
			budgetProfile: 'balanced',
			selectedMatterId: null
		});
		expect(payload.project_id).toBeNull();
	});

	it('forwards the prompt exactly', () => {
		const payload = buildRunPayload({
			prompt: 'Draft an NDA',
			budgetProfile: 'generous',
			selectedMatterId: 'proj-2'
		});
		expect(payload.prompt).toBe('Draft an NDA');
	});
});

describe('buildRunPayload — null detail coerced to no-detail path', () => {
	it('treats detail=null the same as absent (takes the new-conversation branch)', () => {
		const payload = buildRunPayload({
			prompt: 'p',
			budgetProfile: 'economy',
			detail: null,
			selectedMatterId: 'proj-3'
		});
		expect(payload.project_id).toBe('proj-3');
		expect('thread_id' in payload).toBe(false);
	});
});

describe('formatRunCostUSD — post-run cost estimate label (F2 Slice O-2)', () => {
	it('hides the caption (null) when cost_usd is null or undefined', () => {
		expect(formatRunCostUSD(null)).toBeNull();
		expect(formatRunCostUSD(undefined)).toBeNull();
	});

	it('formats a Decimal string from the wire as USD', () => {
		// cost_usd arrives as a Decimal string (NUMERIC on the server).
		expect(formatRunCostUSD('0.3704')).toBe('$0.37');
		expect(formatRunCostUSD('2.0000')).toBe('$2.00');
	});

	it('formats a numeric value as USD', () => {
		expect(formatRunCostUSD(0.6)).toBe('$0.60');
	});

	it('shows the sub-cent band for tiny estimates (honest, not $0.00)', () => {
		// A cheap local-model run prices below a cent — reuse formatCostUSD's band.
		expect(formatRunCostUSD('0.0006')).toBe('< $0.01');
	});

	it('hides the caption for non-finite or negative values (defensive)', () => {
		expect(formatRunCostUSD('not-a-number')).toBeNull();
		expect(formatRunCostUSD(-1)).toBeNull();
	});
});
