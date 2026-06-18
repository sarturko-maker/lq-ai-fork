import { describe, expect, it } from 'vitest';

import { filenameFromDisposition } from './ropa';

describe('filenameFromDisposition (PRIV-4a)', () => {
	it('reads the server-set filename from Content-Disposition', () => {
		const header = 'attachment; filename="article-30-ropa-2026-06-18.xlsx"';
		expect(filenameFromDisposition(header, 'xlsx')).toBe('article-30-ropa-2026-06-18.xlsx');
	});

	it('falls back to a format-suffixed default when the header is absent', () => {
		expect(filenameFromDisposition(null, 'csv')).toBe('article-30-ropa.csv');
		expect(filenameFromDisposition(null, 'json')).toBe('article-30-ropa.json');
	});

	it('falls back when the header carries no filename token', () => {
		expect(filenameFromDisposition('attachment', 'xlsx')).toBe('article-30-ropa.xlsx');
	});
});
