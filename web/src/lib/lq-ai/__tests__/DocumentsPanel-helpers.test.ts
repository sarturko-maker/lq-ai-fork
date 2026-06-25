/**
 * Unit tests for the matter Documents panel's pure helpers (C7a, ADR-F046).
 *
 * No @testing-library/svelte in this codebase (CLAUDE.md: don't add libraries
 * without justification), so — like MemoryPanel / MatterCard — the panel exports
 * its pure decision functions from `<script module>` and we exercise those here;
 * the Svelte template is glue, covered by the Cypress spec.
 */
import { describe, expect, it } from 'vitest';

import {
	fileOriginBadge,
	formatBytes,
	isUpdatingLive
} from '../components/matter/DocumentsPanel.svelte';

describe('formatBytes', () => {
	it('formats across units (1024-based)', () => {
		expect(formatBytes(0)).toBe('0 B');
		expect(formatBytes(512)).toBe('512 B');
		expect(formatBytes(2048)).toBe('2.0 KB');
		expect(formatBytes(1_500_000)).toBe('1.4 MB');
		expect(formatBytes(3 * 1024 ** 3)).toBe('3.0 GB');
	});

	it('treats non-positive / non-finite as 0 B (never NaN/-)', () => {
		expect(formatBytes(-1)).toBe('0 B');
		expect(formatBytes(Number.NaN)).toBe('0 B');
	});
});

// isRedlineOutput now lives in api/editor.ts (single source) — tested in editor-api.test.ts.

describe('fileOriginBadge', () => {
	it('labels a redline output "Redline"', () => {
		expect(
			fileOriginBadge({ filename: 'Cirrus MSA (redlined).docx', created_by_run_id: 'r1' })
		).toBe('Redline');
	});

	it('labels any other agent-produced file "Agent output"', () => {
		expect(fileOriginBadge({ filename: 'summary.docx', created_by_run_id: 'r1' })).toBe(
			'Agent output'
		);
	});

	it('returns null for a plain human upload (no run provenance)', () => {
		expect(fileOriginBadge({ filename: 'Cirrus MSA.docx', created_by_run_id: null })).toBeNull();
	});
});

describe('isUpdatingLive', () => {
	it('mirrors the run-active flag (drives the live poll + indicator)', () => {
		expect(isUpdatingLive(true)).toBe(true);
		expect(isUpdatingLive(false)).toBe(false);
	});
});
