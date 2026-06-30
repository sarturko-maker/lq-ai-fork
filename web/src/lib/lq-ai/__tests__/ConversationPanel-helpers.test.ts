/**
 * Unit tests for the `buildRunPayload` helper exported from ConversationPanel's
 * `<script module>` block (Svelte 5 idiom — same pattern as DocumentEditorPanel-
 * helpers.test.ts). No DOM or @testing-library/svelte needed: the function is
 * purely computational.
 */
import { describe, expect, it } from 'vitest';
import { buildRunPayload } from '../components/agents/ConversationPanel.svelte';

const ALL_PROFILES = ['economy', 'balanced', 'generous'] as const;

describe('buildRunPayload — follow-up (detail present)', () => {
	const detail = { thread: { id: 'thread-abc' } };

	it('uses thread_id and omits project_id when detail is provided', () => {
		const payload = buildRunPayload({ prompt: 'hello', budgetProfile: 'balanced', detail });
		expect(payload.thread_id).toBe('thread-abc');
		expect('project_id' in payload).toBe(false);
	});

	it('always includes budget_profile for every profile value', () => {
		for (const profile of ALL_PROFILES) {
			const payload = buildRunPayload({ prompt: 'p', budgetProfile: profile, detail });
			expect(payload.budget_profile).toBe(profile);
		}
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

	it('always includes budget_profile for every profile value', () => {
		for (const profile of ALL_PROFILES) {
			const payload = buildRunPayload({
				prompt: 'p',
				budgetProfile: profile,
				selectedMatterId: 'proj-1'
			});
			expect(payload.budget_profile).toBe(profile);
		}
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
