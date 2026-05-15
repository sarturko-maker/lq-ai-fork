/**
 * Unit tests for ChatPanel slash-detection helper (Wave D.2, Task 7.1).
 *
 * Convention note: matches the SlashPopover test pattern — pure helpers
 * are exported from <script context="module"> in the .svelte file and
 * exercised here without mounting the (953-LOC) component. The
 * @testing-library/svelte path is unavailable per
 * AttachedSkillPill.test.ts / AttachKBModal.test.ts headers; full
 * composer-popover wiring is exercised by Cypress e2e.
 *
 * Coverage:
 *   - isAtLineStart()
 *   - detectSlashAt() across the boundary cases the composer relies on:
 *       · slash at start of textarea → opens
 *       · slash after a newline → opens
 *       · slash mid-line ("and/or", "TCP/IP") → does NOT open
 *       · empty query (just "/") → opens with query=""
 *       · query containing legal slash-alias chars (a-z, 0-9, -) → opens
 *       · query interrupted by uppercase/space/underscore → does NOT open
 *       · caret at position 0 → does NOT open
 */
import { describe, expect, it } from 'vitest';

import { isAtLineStart, detectSlashAt } from '../components/ChatPanel.svelte';

describe('isAtLineStart', () => {
	it('returns true at position 0', () => {
		expect(isAtLineStart('foo', 0)).toBe(true);
	});

	it('returns true immediately after a newline', () => {
		expect(isAtLineStart('foo\nbar', 4)).toBe(true);
	});

	it('returns false in the middle of a line', () => {
		expect(isAtLineStart('foobar', 3)).toBe(false);
	});

	it('returns false immediately after a space', () => {
		expect(isAtLineStart('foo bar', 4)).toBe(false);
	});
});

describe('detectSlashAt', () => {
	it('does not open when caret is at position 0', () => {
		expect(detectSlashAt('', 0)).toEqual({ open: false });
		expect(detectSlashAt('/foo', 0)).toEqual({ open: false });
	});

	it('opens with empty query when text is just "/"', () => {
		expect(detectSlashAt('/', 1)).toEqual({
			open: true,
			query: '',
			slashIndex: 0
		});
	});

	it('opens at start of textarea with query', () => {
		expect(detectSlashAt('/nda', 4)).toEqual({
			open: true,
			query: 'nda',
			slashIndex: 0
		});
	});

	it('opens immediately after a newline', () => {
		expect(detectSlashAt('hello\n/nda', 10)).toEqual({
			open: true,
			query: 'nda',
			slashIndex: 6
		});
	});

	it('does NOT open mid-line (after a non-newline character)', () => {
		// "and/or" — slash after "and " (or after "and") should not open.
		expect(detectSlashAt('and/or', 6)).toEqual({ open: false });
		expect(detectSlashAt('TCP/IP'.toLowerCase(), 6)).toEqual({ open: false });
	});

	it('does NOT open when slash follows a space', () => {
		// Composer line: "go and /nda" — slash isn't at line start.
		expect(detectSlashAt('go and /nda', 11)).toEqual({ open: false });
	});

	it('opens with hyphenated query', () => {
		expect(detectSlashAt('/msa-review-saas', 16)).toEqual({
			open: true,
			query: 'msa-review-saas',
			slashIndex: 0
		});
	});

	it('opens with digits in query', () => {
		expect(detectSlashAt('/skill123', 9)).toEqual({
			open: true,
			query: 'skill123',
			slashIndex: 0
		});
	});

	it('does NOT open when query contains uppercase (illegal slash-alias char)', () => {
		// The walker stops at the uppercase 'A', leaving no '/' immediately
		// before the scan position → closed.
		expect(detectSlashAt('/NDA', 4)).toEqual({ open: false });
	});

	it('does NOT open when query contains a space', () => {
		expect(detectSlashAt('/nda review', 11)).toEqual({ open: false });
	});

	it('does NOT open when query contains an underscore', () => {
		// `_` is excluded from the slash-alias character class; the walker
		// stops at '_', and the char before is 'a' (not '/'), so closed.
		expect(detectSlashAt('/nda_review', 11)).toEqual({ open: false });
	});

	it('handles partial query (caret in the middle of typing)', () => {
		// User has typed "/nd" and caret is at position 3.
		expect(detectSlashAt('/nd', 3)).toEqual({
			open: true,
			query: 'nd',
			slashIndex: 0
		});
	});

	it('handles caret in the middle of an existing slash query', () => {
		// "/nda-review" with caret after "nda" (position 4).
		expect(detectSlashAt('/nda-review', 4)).toEqual({
			open: true,
			query: 'nda',
			slashIndex: 0
		});
	});
});
