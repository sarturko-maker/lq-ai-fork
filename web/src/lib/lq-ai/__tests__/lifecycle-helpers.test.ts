/**
 * Tests for the unauth token-page helpers (SETUP-3b, ADR-F061).
 */
import { describe, expect, it } from 'vitest';

import {
	PASSWORD_MIN_LENGTH,
	readToken,
	validateNewPassword
} from '../auth/lifecycle-helpers';

describe('readToken', () => {
	it('returns the token when present', () => {
		expect(readToken(new URLSearchParams('token=abc123'))).toBe('abc123');
	});

	it('trims surrounding whitespace', () => {
		expect(readToken(new URLSearchParams('token=%20abc%20'))).toBe('abc');
	});

	it('returns null when missing, empty, or blank (no request fired)', () => {
		expect(readToken(new URLSearchParams(''))).toBeNull();
		expect(readToken(new URLSearchParams('token='))).toBeNull();
		expect(readToken(new URLSearchParams('token=%20%20'))).toBeNull();
	});
});

describe('validateNewPassword', () => {
	it('enforces the 12-character floor (password_min_length parity)', () => {
		expect(PASSWORD_MIN_LENGTH).toBe(12);
		expect(validateNewPassword('short', 'short')).toBe(
			'Password must be at least 12 characters.'
		);
		expect(validateNewPassword('a'.repeat(11), 'a'.repeat(11))).toBe(
			'Password must be at least 12 characters.'
		);
	});

	it('requires the confirmation to match', () => {
		expect(validateNewPassword('a-long-enough-pw', 'a-different-pw-here')).toBe(
			'Password and confirmation do not match.'
		);
	});

	it('accepts a matching pair at or above the floor', () => {
		expect(validateNewPassword('a'.repeat(12), 'a'.repeat(12))).toBeNull();
		expect(validateNewPassword('correct horse battery', 'correct horse battery')).toBeNull();
	});
});
