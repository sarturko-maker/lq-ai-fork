/**
 * Unit tests for CaptureSkillModal helpers (Wave D.2, Task 5.2).
 *
 * Convention note: this codebase does not install @testing-library/svelte
 * (see SkillWizard.test.ts / AttachKBModal.test.ts headers). CLAUDE.md
 * forbids adding libraries without justification. So we follow the
 * established pattern: the .svelte file exports its pure logic from
 * <script context="module">, and we exercise those helpers here. The
 * template glue (the modal markup, the navigate-on-save, etc.) is
 * exercised in Cypress e2e once Task 5.3 wires the modal into
 * MessageBubble.
 *
 * Coverage:
 *   - kebab(s)                                — slug auto-derivation
 *   - derive(message)                         — name / slug / description seeds
 *     across heading-led, sentence-led, empty, all-list-items, and
 *     all-symbol message bodies
 *   - canSave(state)                          — submit-button gate
 *   - buildPayload(state, sourceMessage)      — POST /user-skills body shape
 *   - stashForWizard(state)                   — Edit-in-wizard stash shape
 *   - stashStorageKey(captureId)              — localStorage key conventions
 */
import { describe, expect, it } from 'vitest';

import {
	kebab,
	derive,
	canSave,
	buildPayload,
	stashForWizard,
	stashStorageKey,
	type CaptureFormState
} from '../components/CaptureSkillModal.svelte';
import type { Message } from '../types';

function makeMessage(overrides: Partial<Message> = {}): Message {
	return {
		id: 'msg-abc-123',
		chat_id: 'chat-1',
		role: 'assistant',
		content: 'Hello world.',
		created_at: '2026-05-13T00:00:00Z',
		...overrides
	};
}

function makeState(overrides: Partial<CaptureFormState> = {}): CaptureFormState {
	return {
		name: 'NDA Review',
		slug: 'nda-review',
		description: 'Reviews NDA documents',
		body: '# NDA Review\nApply this skill when the user shares an NDA.',
		saving: false,
		...overrides
	};
}

describe('CaptureSkillModal.kebab', () => {
	it('converts spaces to dashes and lowercases', () => {
		expect(kebab('NDA Review')).toBe('nda-review');
	});

	it('collapses runs of non-alphanumeric chars to a single dash', () => {
		expect(kebab('Foo  Bar')).toBe('foo-bar');
		expect(kebab('Hello, World!')).toBe('hello-world');
	});

	it('trims leading and trailing dashes', () => {
		expect(kebab('  hello  ')).toBe('hello');
		expect(kebab('---hello---')).toBe('hello');
	});

	it('returns an empty string for all-non-alphanumeric input', () => {
		expect(kebab('')).toBe('');
		expect(kebab('---')).toBe('');
	});

	it('caps output at 80 characters', () => {
		expect(kebab('a'.repeat(100))).toHaveLength(80);
	});
});

describe('CaptureSkillModal.derive', () => {
	it('uses the first markdown heading as the name when present', () => {
		const m = makeMessage({
			content: '# NDA Review\n\nReviews mutual NDAs and flags rough edges.'
		});
		const d = derive(m);
		expect(d.name).toBe('NDA Review');
		expect(d.slug).toBe('nda-review');
		// description still comes from the first non-heading sentence
		expect(d.description).toBe('Reviews mutual NDAs and flags rough edges.');
	});

	it('strips multiple leading hash characters from the heading', () => {
		const m = makeMessage({ content: '### Deep Heading\nBody sentence.' });
		expect(derive(m).name).toBe('Deep Heading');
	});

	it('falls back to the first sentence when no heading is present', () => {
		const m = makeMessage({
			content: 'This is the first sentence. This is the second one.'
		});
		const d = derive(m);
		expect(d.name).toBe('This is the first sentence.');
		expect(d.description).toBe('This is the first sentence.');
		expect(d.slug).toBe('this-is-the-first-sentence');
	});

	it('truncates an overlong sentence-derived name to 60 chars', () => {
		const m = makeMessage({
			content:
				'A very long sentence that keeps going and going and going past sixty characters easily.'
		});
		const d = derive(m);
		expect(d.name.length).toBeLessThanOrEqual(60);
	});

	it('uses the literal "Captured skill" when content has no usable text', () => {
		// Pure list items + no heading → no first-sentence-line found, name
		// falls back to the literal string.
		const m = makeMessage({ content: '- one\n- two\n- three' });
		const d = derive(m);
		expect(d.name).toBe('Captured skill');
		expect(d.description).toBe('');
		expect(d.slug).toBe('captured-skill');
	});

	it('uses the deterministic captured-skill-<id-prefix> slug fallback when name kebabs to empty', () => {
		// A heading that's entirely non-alphanumeric kebabs to ''. The
		// fallback must still produce a valid slug so the user can save.
		const m = makeMessage({ id: 'msg-zzzzzz-deadbeef', content: '# !!!\nBody.' });
		const d = derive(m);
		// name comes from the heading (literal "!!!"), slug falls back.
		expect(d.name).toBe('!!!');
		expect(d.slug).toBe('captured-skill-msg-zz');
	});

	it('returns a stable slug for empty content', () => {
		const m = makeMessage({ id: 'msg-12345', content: '' });
		const d = derive(m);
		expect(d.name).toBe('Captured skill');
		expect(d.slug).toBe('captured-skill');
	});

	it('skips list-item lines when looking for a sentence', () => {
		// Heading + list items + a real sentence after the list. Heading wins
		// the name; description comes from the first non-heading non-list line.
		const m = makeMessage({
			content: '# Title\n- item one\n- item two\nThe summary sentence here.'
		});
		const d = derive(m);
		expect(d.name).toBe('Title');
		expect(d.description).toBe('The summary sentence here.');
	});
});

describe('CaptureSkillModal.canSave', () => {
	it('is true when name, slug, and body are all populated', () => {
		expect(canSave(makeState())).toBe(true);
	});

	it('is false when name is missing or whitespace', () => {
		expect(canSave(makeState({ name: '' }))).toBe(false);
		expect(canSave(makeState({ name: '   ' }))).toBe(false);
	});

	it('is false when slug is missing or whitespace', () => {
		expect(canSave(makeState({ slug: '' }))).toBe(false);
		expect(canSave(makeState({ slug: '   ' }))).toBe(false);
	});

	it('is false when body is missing or whitespace', () => {
		expect(canSave(makeState({ body: '' }))).toBe(false);
		expect(canSave(makeState({ body: '   ' }))).toBe(false);
	});

	it('is true when description is empty (description is optional in the modal gate)', () => {
		// The modal falls back to name when description is empty, so no
		// requirement to populate it for the gate.
		expect(canSave(makeState({ description: '' }))).toBe(true);
	});

	it('is false while saving is in flight', () => {
		expect(canSave(makeState({ saving: true }))).toBe(false);
	});
});

describe('CaptureSkillModal.buildPayload', () => {
	it('produces a UserSkillCreate-shaped payload (display_name / body, NOT title / body_md)', () => {
		const m = makeMessage({ id: 'msg-source-9' });
		const payload = buildPayload(makeState(), m);
		expect(payload).toEqual({
			scope: 'user',
			slug: 'nda-review',
			display_name: 'NDA Review',
			description: 'Reviews NDA documents',
			body: '# NDA Review\nApply this skill when the user shares an NDA.',
			source_message_id: 'msg-source-9'
		});
		// Should not include the plan-text legacy keys.
		const asRecord = payload as unknown as Record<string, unknown>;
		expect(asRecord.title).toBeUndefined();
		expect(asRecord.body_md).toBeUndefined();
	});

	it('trims display_name, description, and slug before sending', () => {
		const payload = buildPayload(
			makeState({
				name: '  Padded Name  ',
				description: '  Padded desc  ',
				slug: '  nda-review  '
			}),
			makeMessage()
		);
		expect(payload.display_name).toBe('Padded Name');
		expect(payload.description).toBe('Padded desc');
		expect(payload.slug).toBe('nda-review');
	});

	it('falls back to the trimmed name when description is empty (backend requires non-empty)', () => {
		const payload = buildPayload(
			makeState({ name: 'NDA Review', description: '' }),
			makeMessage()
		);
		expect(payload.description).toBe('NDA Review');
	});

	it('falls back to the trimmed name when description is whitespace only', () => {
		const payload = buildPayload(
			makeState({ name: 'NDA Review', description: '   ' }),
			makeMessage()
		);
		expect(payload.description).toBe('NDA Review');
	});

	it('preserves body verbatim (no trimming) so the captured exchange is faithful', () => {
		const body = '\n  preserved leading + trailing whitespace  \n';
		const payload = buildPayload(makeState({ body }), makeMessage());
		expect(payload.body).toBe(body);
	});

	it('forwards source_message_id from the captured message', () => {
		const payload = buildPayload(makeState(), makeMessage({ id: 'msg-xyz' }));
		expect(payload.source_message_id).toBe('msg-xyz');
	});

	it('sets scope=user (the capture flow is user-scope only)', () => {
		expect(buildPayload(makeState(), makeMessage()).scope).toBe('user');
	});
});

describe('CaptureSkillModal.stashForWizard', () => {
	/**
	 * The stash shape MUST match `WizardInitial` in
	 * `/lq-ai/skills/new/+page.svelte`. That route casts the parsed JSON
	 * directly to WizardInitial — there's no runtime validation, so a
	 * field-name mismatch would silently break the Edit-in-wizard handoff.
	 * These assertions pin the camelCase field names and the defaults.
	 */
	it('returns the camelCase WizardInitial-shaped snapshot the wizard route expects', () => {
		const stash = stashForWizard(makeState(), makeMessage());
		expect(stash).toEqual({
			slug: 'nda-review',
			displayName: 'NDA Review',
			description: 'Reviews NDA documents',
			body: '# NDA Review\nApply this skill when the user shares an NDA.',
			scope: 'user',
			version: '1.0.0',
			forkedFrom: null
		});
	});

	it('uses camelCase field names (NOT snake_case API names)', () => {
		const stash = stashForWizard(makeState(), makeMessage());
		const asRecord = stash as unknown as Record<string, unknown>;
		expect(asRecord.display_name).toBeUndefined();
		expect(asRecord.owner_team_id).toBeUndefined();
		expect(asRecord.forked_from).toBeUndefined();
		expect(asRecord.slash_alias).toBeUndefined();
	});

	it('trims slug, displayName, and description', () => {
		const stash = stashForWizard(
			makeState({
				name: '  Padded  ',
				slug: '  nda-review  ',
				description: '  desc  '
			}),
			makeMessage()
		);
		expect(stash.displayName).toBe('Padded');
		expect(stash.slug).toBe('nda-review');
		expect(stash.description).toBe('desc');
	});

	it('preserves body verbatim (no trimming) so the wizard sees the captured exchange unchanged', () => {
		const body = '\n  preserved + trailing\nwhitespace\n  ';
		expect(stashForWizard(makeState({ body }), makeMessage()).body).toBe(body);
	});

	it('falls back to sourceMessage.content when body is empty (preserves user intent on accidental delete)', () => {
		// User opened the modal, blanked the body field, then clicked
		// "Edit in wizard". Their intent ("refine this exchange") is
		// preserved by stashing the original captured message content
		// rather than an empty string.
		const source = makeMessage({ content: '# Original\nThe captured exchange body.' });
		const stash = stashForWizard(makeState({ body: '' }), source);
		expect(stash.body).toBe('# Original\nThe captured exchange body.');
	});

	it('falls back to sourceMessage.content when body is whitespace only', () => {
		// trim()-empty body counts as blanked too — same fallback.
		const source = makeMessage({ content: 'Captured content here.' });
		const stash = stashForWizard(makeState({ body: '   \n  \t  ' }), source);
		expect(stash.body).toBe('Captured content here.');
	});

	it('does NOT fall back when body has any non-whitespace content (preserves user edits)', () => {
		// If the user has typed anything meaningful, that's what they want
		// in the wizard — even if surrounded by whitespace.
		const source = makeMessage({ content: 'Original content.' });
		const stash = stashForWizard(makeState({ body: '\n  edited body  \n' }), source);
		expect(stash.body).toBe('\n  edited body  \n');
	});

	it('round-trips through JSON without losing fields', () => {
		const stash = stashForWizard(makeState(), makeMessage());
		const restored = JSON.parse(JSON.stringify(stash));
		expect(restored).toEqual(stash);
	});

	it('defaults forkedFrom=null, scope=user, version="1.0.0"', () => {
		const stash = stashForWizard(makeState(), makeMessage());
		expect(stash.scope).toBe('user');
		expect(stash.version).toBe('1.0.0');
		expect(stash.forkedFrom).toBe(null);
	});
});

describe('CaptureSkillModal.stashStorageKey', () => {
	/**
	 * The storage-key prefix MUST match what `/lq-ai/skills/new` reads:
	 * `lq-ai:capture-stash:<key>` (see +page.svelte:139). Renaming the
	 * prefix on either side breaks the Edit-in-wizard handoff silently.
	 */
	it('uses the lq-ai:capture-stash: prefix the wizard route expects', () => {
		expect(stashStorageKey('abc-123')).toBe('lq-ai:capture-stash:abc-123');
	});

	it('passes the capture id through verbatim (no kebab / encode)', () => {
		expect(stashStorageKey('UUID-Mixed-Case')).toBe(
			'lq-ai:capture-stash:UUID-Mixed-Case'
		);
	});
});
