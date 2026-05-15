/**
 * Unit tests for SkillVersionsTab helpers (Wave D.2 Task 6.2).
 *
 * Convention note: this codebase does not install ``@testing-library/svelte``
 * (see SkillWizard.test.ts / AttachKBModal.test.ts headers; CLAUDE.md
 * forbids adding libraries without justification). So we follow the
 * established pattern: the .svelte file exports its pure logic from
 * ``<script context="module">``, and we exercise those helpers here. The
 * ``onMount`` data-fetch glue and the table-render branch are covered in
 * Cypress (Wave 8) once the page wires this tab.
 *
 * Coverage:
 *   - isBuiltinReadonly(skill)                 — built-in branch + missing-id branch
 *   - formatActor(v)                           — email present + null fallback
 *   - formatVersion(v)                         — semver present + null fallback
 *   - formatTimestamp(v)                       — non-empty (locale-sensitive; see note)
 *   - shouldShowEmptyState(skill, ...)         — derived state for the "no rows yet" UX
 */
import { describe, expect, it } from 'vitest';

import {
	isBuiltinReadonly,
	formatActor,
	formatVersion,
	formatTimestamp,
	shouldShowEmptyState,
	type SkillForVersionsTab
} from '../components/SkillVersionsTab.svelte';
import type { UserSkillVersion } from '../types';

function makeVersion(overrides: Partial<UserSkillVersion> = {}): UserSkillVersion {
	return {
		timestamp: '2026-05-13T15:30:00Z',
		actor_user_id: 'user-uuid-1',
		actor_email: 'attorney@example.com',
		action: 'user_skill.updated',
		version: '1.0.1',
		details: null,
		...overrides
	};
}

describe('SkillVersionsTab.isBuiltinReadonly', () => {
	it('is true for a built-in skill (no DB id, no audit history)', () => {
		const skill: SkillForVersionsTab = { scope: 'builtin', name: 'nda-review' };
		expect(isBuiltinReadonly(skill)).toBe(true);
	});

	it('is true defensively when a non-builtin row is missing its id', () => {
		// Defensive: parents should never pass an id-less user/team row, but
		// the audit endpoint requires an id and we'd rather render the
		// readonly state than 422.
		const skill: SkillForVersionsTab = { scope: 'user', name: 'my-thing' };
		expect(isBuiltinReadonly(skill)).toBe(true);
	});

	it('is false for a user-scope skill with an id', () => {
		const skill: SkillForVersionsTab = {
			scope: 'user',
			id: 'sk-1',
			name: 'my-thing'
		};
		expect(isBuiltinReadonly(skill)).toBe(false);
	});

	it('is false for a team-scope skill with an id', () => {
		const skill: SkillForVersionsTab = {
			scope: 'team',
			id: 'sk-2',
			name: 'team-playbook'
		};
		expect(isBuiltinReadonly(skill)).toBe(false);
	});
});

describe('SkillVersionsTab.formatActor', () => {
	it('returns the email when present', () => {
		expect(formatActor(makeVersion({ actor_email: 'a@b.com' }))).toBe('a@b.com');
	});

	it('returns the em-dash placeholder when actor_email is null', () => {
		expect(formatActor(makeVersion({ actor_email: null }))).toBe('—');
	});
});

describe('SkillVersionsTab.formatVersion', () => {
	it('returns the version string when present', () => {
		expect(formatVersion(makeVersion({ version: '1.0.0' }))).toBe('1.0.0');
		expect(formatVersion(makeVersion({ version: '2.4.1' }))).toBe('2.4.1');
	});

	it('returns the em-dash placeholder when version is null', () => {
		expect(formatVersion(makeVersion({ version: null }))).toBe('—');
	});
});

describe('SkillVersionsTab.formatTimestamp', () => {
	// Locale + timezone are both runtime-dependent (CI vs dev box vs browser).
	// We assert non-empty and that obvious garbage shows through, rather than
	// pinning a specific locale string. The exact rendering is verified
	// in Cypress against a deterministic browser locale.
	it('returns a non-empty string for a valid ISO-8601 timestamp', () => {
		const out = formatTimestamp(makeVersion({ timestamp: '2026-05-13T15:30:00Z' }));
		expect(out).toBeTruthy();
		expect(out.length).toBeGreaterThan(0);
		expect(out).not.toBe('Invalid Date');
	});

	it('surfaces "Invalid Date" for unparseable input (matches native Date behavior)', () => {
		// We deliberately do NOT mask this — a bogus timestamp upstream is a
		// data bug worth surfacing in the audit table during QA.
		expect(formatTimestamp(makeVersion({ timestamp: 'not-a-date' }))).toBe(
			'Invalid Date'
		);
	});
});

describe('SkillVersionsTab.shouldShowEmptyState', () => {
	const userSkill: SkillForVersionsTab = {
		scope: 'user',
		id: 'sk-1',
		name: 'my-thing'
	};
	const builtin: SkillForVersionsTab = { scope: 'builtin', name: 'nda-review' };

	it('is true for a user-scope skill with no rows after a successful load', () => {
		expect(shouldShowEmptyState(userSkill, [], false, null)).toBe(true);
	});

	it('is false while loading (the loading branch owns the UI)', () => {
		expect(shouldShowEmptyState(userSkill, [], true, null)).toBe(false);
	});

	it('is false when there is an error (the error branch owns the UI)', () => {
		expect(shouldShowEmptyState(userSkill, [], false, 'boom')).toBe(false);
	});

	it('is false when versions exist (the table branch owns the UI)', () => {
		expect(shouldShowEmptyState(userSkill, [makeVersion()], false, null)).toBe(false);
	});

	it('is false for built-in skills (the readonly empty state owns the UI)', () => {
		// The built-in branch renders its own dedicated empty state — we don't
		// want both paths firing.
		expect(shouldShowEmptyState(builtin, [], false, null)).toBe(false);
	});
});
