/**
 * Unit tests for the matter-memory panel's pure helpers (C3c-2).
 *
 * No @testing-library/svelte in this codebase (CLAUDE.md: don't add libraries
 * without justification), so — like MatterCard / AttachKBModal — the panel
 * exports its pure decision functions from `<script module>` and we exercise
 * those here; the Svelte template is glue, covered by the Cypress spec.
 */
import { describe, expect, it } from 'vitest';

import {
	canRevert,
	isRevertable,
	logKindLabel,
	logTailNote,
	shortRunId
} from '../components/matter/MemoryPanel.svelte';

describe('logKindLabel', () => {
	it('maps known kinds to friendly labels', () => {
		expect(logKindLabel('wiki_snapshot')).toBe('Summary revision');
		expect(logKindLabel('fact')).toBe('Fact');
		expect(logKindLabel('correction')).toBe('Pinned correction');
		expect(logKindLabel('consolidation')).toBe('Consolidation');
	});

	it('title-cases an unknown kind rather than dropping it', () => {
		expect(logKindLabel('some_new_kind')).toBe('Some New Kind');
	});
});

describe('isRevertable', () => {
	it('is true only for wiki snapshots (the revert target)', () => {
		expect(isRevertable({ kind: 'wiki_snapshot' })).toBe(true);
		expect(isRevertable({ kind: 'fact' })).toBe(false);
		expect(isRevertable({ kind: 'correction' })).toBe(false);
		expect(isRevertable({ kind: 'consolidation' })).toBe(false);
	});
});

describe('shortRunId', () => {
	it('takes the first segment of a run id', () => {
		expect(shortRunId('deadbeef-1234-5678-9abc-def012345678')).toBe('deadbeef');
	});

	it('renders an em-dash for a run-less (human) entry', () => {
		expect(shortRunId(null)).toBe('—');
	});
});

describe('logTailNote', () => {
	it('notes the tail cap when the log is truncated', () => {
		expect(logTailNote(200, 540)).toBe('Showing the 200 most recent of 540 entries.');
	});

	it('is empty when the whole log fits', () => {
		expect(logTailNote(12, 12)).toBe('');
		expect(logTailNote(5, 3)).toBe(''); // never negative — shown >= total
	});
});

describe('canRevert', () => {
	it('blocks revert while a run is active (no racing the agent), allows it otherwise', () => {
		expect(canRevert(true)).toBe(false);
		expect(canRevert(false)).toBe(true);
	});
});
