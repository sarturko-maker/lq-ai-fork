/**
 * /lq-ai/admin/house-brief helper tests — B-1 (ADR-F049).
 */
import { describe, expect, it } from 'vitest';

import {
	HOUSE_BRIEF_MAX_CHARS,
	formatDateTime,
	formatLastUpdated,
	isContentEmpty,
	validateContentLength
} from '../page-helpers';

describe('validateContentLength', () => {
	it('accepts empty content and content within the cap', () => {
		expect(validateContentLength('')).toBeNull();
		expect(validateContentLength('Acme Corp is a widget manufacturer.')).toBeNull();
		expect(validateContentLength('x'.repeat(HOUSE_BRIEF_MAX_CHARS))).toBeNull();
	});

	it('rejects content over the server cap with a clear message', () => {
		const error = validateContentLength('x'.repeat(HOUSE_BRIEF_MAX_CHARS + 1));
		expect(error).not.toBeNull();
		expect(error).toContain(String(HOUSE_BRIEF_MAX_CHARS));
		expect(error).toContain(String(HOUSE_BRIEF_MAX_CHARS + 1));
	});
});

describe('isContentEmpty', () => {
	it('is true for empty and whitespace-only content', () => {
		expect(isContentEmpty('')).toBe(true);
		expect(isContentEmpty('   \n\t  ')).toBe(true);
	});

	it('is false once there is real content', () => {
		expect(isContentEmpty('Acme Corp')).toBe(false);
		expect(isContentEmpty('  Acme Corp  ')).toBe(false);
	});
});

describe('formatDateTime', () => {
	it('returns the raw string on parse failure', () => {
		expect(formatDateTime('not-a-date')).toBe('not-a-date');
	});

	it('formats a valid ISO timestamp (not the raw string)', () => {
		expect(formatDateTime('2026-07-01T12:00:00Z')).not.toBe('2026-07-01T12:00:00Z');
	});
});

describe('formatLastUpdated', () => {
	it('is null when the House Brief was never saved', () => {
		expect(formatLastUpdated(null, null)).toBeNull();
	});

	it('includes the admin id when present', () => {
		const result = formatLastUpdated('2026-07-01T12:00:00Z', 'user-123');
		expect(result).toContain('Last updated');
		expect(result).toContain('user-123');
	});

	it('omits the "by" clause when updated_by is absent', () => {
		const result = formatLastUpdated('2026-07-01T12:00:00Z', null);
		expect(result).toContain('Last updated');
		expect(result).not.toContain(' by ');
	});
});
