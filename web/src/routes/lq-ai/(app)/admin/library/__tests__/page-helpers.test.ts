/**
 * Pure-helper tests for the /lq-ai/admin/library review-queue section
 * (B-2b, ADR-F067 D2/D3, contract decision 2).
 */
import { describe, expect, it } from 'vitest';

import {
	DEFAULT_QUEUE_STATE,
	STATE_FILTER_PILLS,
	formatSizeBytes,
	queueEmptyMessage,
	truncateHash
} from '../page-helpers';

describe('STATE_FILTER_PILLS', () => {
	it('lists exactly the five org-skill-version states, proposed first', () => {
		expect(STATE_FILTER_PILLS.map((p) => p.value)).toEqual([
			'proposed',
			'approved',
			'rejected',
			'superseded',
			'revoked'
		]);
	});

	it('defaults the queue to the proposed filter', () => {
		expect(DEFAULT_QUEUE_STATE).toBe('proposed');
	});
});

describe('queueEmptyMessage', () => {
	it('names the active filter in the honest-negative copy', () => {
		expect(queueEmptyMessage('proposed')).toBe('Nothing proposed right now.');
		expect(queueEmptyMessage('revoked')).toBe('Nothing revoked right now.');
	});
});

describe('truncateHash', () => {
	it('leaves a short hash untouched', () => {
		expect(truncateHash('abc123')).toBe('abc123');
	});

	it('truncates a long hash to the default visible length with an ellipsis', () => {
		const hash = 'a1b2c3d4e5f6a7b8c9d0';
		expect(truncateHash(hash)).toBe('a1b2c3d4e5f6…');
	});

	it('respects a custom visible-length', () => {
		expect(truncateHash('abcdefghij', 4)).toBe('abcd…');
	});

	it('does not truncate a hash exactly at the boundary', () => {
		expect(truncateHash('123456789012', 12)).toBe('123456789012');
	});
});

describe('formatSizeBytes', () => {
	it('renders 0 or negative as "0 B"', () => {
		expect(formatSizeBytes(0)).toBe('0 B');
		expect(formatSizeBytes(-5)).toBe('0 B');
	});

	it('renders sub-1024 byte counts as whole bytes', () => {
		expect(formatSizeBytes(512)).toBe('512 B');
	});

	it('renders KB with one decimal place', () => {
		expect(formatSizeBytes(2048)).toBe('2.0 KB');
	});

	it('renders MB with one decimal place', () => {
		expect(formatSizeBytes(2 * 1024 * 1024)).toBe('2.0 MB');
	});

	it('handles non-finite input defensively', () => {
		expect(formatSizeBytes(Number.NaN)).toBe('0 B');
	});
});
