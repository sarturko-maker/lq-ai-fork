/**
 * Unit tests for the helpers exported from
 * `routes/lq-ai/knowledge/[id]/+page.svelte` <script context="module">.
 *
 * Pattern matches knowledge-page-helpers.test.ts: pure helpers exported
 * from the module-level script + tested without @testing-library/svelte.
 */
import { describe, expect, it } from 'vitest';
import {
	docStatusLabel,
	formatBytes,
	sortFiles,
	type DocStatus
} from '../../../routes/lq-ai/knowledge/[id]/+page.svelte';
import type { KnowledgeBaseFile, IngestionStatus } from '../types';

function makeFile(
	overrides: Partial<KnowledgeBaseFile> = {}
): KnowledgeBaseFile {
	return {
		id: 'f-default',
		owner_id: 'u1',
		filename: 'doc.pdf',
		mime_type: 'application/pdf',
		size_bytes: 100,
		hash_sha256: 'abc',
		ingestion_status: 'ready' as IngestionStatus,
		created_at: '2026-05-01T00:00:00Z',
		attached_at: '2026-05-01T00:00:00Z',
		...overrides
	};
}

describe('docStatusLabel', () => {
	it('renders the spec-mandated indicators', () => {
		const cases: Array<[DocStatus, string]> = [
			['ready', '✓ ready'],
			['processing', '⏳ processing'],
			['pending', '⏳ pending'],
			['failed', '⚠ failed']
		];
		for (const [s, expected] of cases) {
			expect(docStatusLabel(s)).toBe(expected);
		}
	});
});

describe('formatBytes', () => {
	it('renders bytes', () => {
		expect(formatBytes(0)).toBe('0 B');
		expect(formatBytes(512)).toBe('512 B');
	});
	it('renders KB / MB with binary divisor', () => {
		expect(formatBytes(1024)).toBe('1.0 KB');
		expect(formatBytes(1024 * 100)).toBe('100 KB');
		expect(formatBytes(1024 * 1024)).toBe('1.0 MB');
		expect(formatBytes(1024 * 1024 * 1024 * 5)).toBe('5.0 GB');
	});
	it('handles invalid input', () => {
		expect(formatBytes(NaN)).toBe('—');
		expect(formatBytes(-1)).toBe('—');
	});
});

describe('sortFiles', () => {
	it('orders ready first, processing/pending next, failed last', () => {
		const files = [
			makeFile({ id: 'a', filename: 'a.pdf', ingestion_status: 'failed' }),
			makeFile({ id: 'b', filename: 'b.pdf', ingestion_status: 'ready' }),
			makeFile({ id: 'c', filename: 'c.pdf', ingestion_status: 'processing' }),
			makeFile({ id: 'd', filename: 'd.pdf', ingestion_status: 'ready' }),
			makeFile({ id: 'e', filename: 'e.pdf', ingestion_status: 'pending' })
		];
		const sorted = sortFiles(files).map((f) => f.id);
		expect(sorted).toEqual(['b', 'd', 'c', 'e', 'a']);
	});

	it('does not mutate the input array', () => {
		const files = [
			makeFile({ id: 'z', filename: 'z.pdf', ingestion_status: 'failed' }),
			makeFile({ id: 'a', filename: 'a.pdf', ingestion_status: 'ready' })
		];
		const before = files.map((f) => f.id);
		sortFiles(files);
		expect(files.map((f) => f.id)).toEqual(before);
	});
});
