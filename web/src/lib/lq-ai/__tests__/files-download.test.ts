/**
 * Unit tests for the file-download filename picker (C7a, ADR-F046). The DOM
 * download trigger (`downloadFile`) is browser-only and covered by Cypress; the
 * pure name selection is exercised here.
 */
import { describe, expect, it } from 'vitest';

import { pickDownloadFilename } from '../api/files';

describe('pickDownloadFilename', () => {
	it('prefers the caller-supplied name (the cockpit already has it)', () => {
		expect(
			pickDownloadFilename('Cirrus MSA (redlined).docx', 'attachment; filename="server.docx"', 'id')
		).toBe('Cirrus MSA (redlined).docx');
	});

	it('falls back to a quoted Content-Disposition filename', () => {
		expect(pickDownloadFilename(undefined, 'attachment; filename="server.docx"', 'id')).toBe(
			'server.docx'
		);
	});

	it('decodes an RFC 5987 filename* (non-ASCII)', () => {
		expect(
			pickDownloadFilename(undefined, "attachment; filename*=UTF-8''Contr%C3%A4t.docx", 'id')
		).toBe('Conträt.docx');
	});

	it('falls back to the bare id when no name is available', () => {
		expect(pickDownloadFilename(undefined, null, 'file-123')).toBe('file-123');
		expect(pickDownloadFilename('   ', null, 'file-123')).toBe('file-123');
	});
});
