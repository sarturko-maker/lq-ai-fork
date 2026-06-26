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
	canWrite,
	CORRECTION_MAX_CHARS,
	factCorrectionPrefill,
	isParticipantSubmittable,
	isPinSubmittable,
	isRevertable,
	logKindLabel,
	logTailNote,
	PARTICIPANT_SIDES,
	parseAliases,
	participantTrustLabel,
	shortRunId,
	sideLabel,
	sideToneClass
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

describe('canWrite', () => {
	it('gates every human write on no run being mid-write', () => {
		expect(canWrite(true)).toBe(false);
		expect(canWrite(false)).toBe(true);
	});

	it('is the same gate canRevert aliases (single-sourced)', () => {
		expect(canRevert).toBe(canWrite);
	});
});

describe('isPinSubmittable', () => {
	it('accepts non-empty text within the body cap', () => {
		expect(isPinSubmittable('We act for the seller.')).toBe(true);
		expect(isPinSubmittable('x'.repeat(CORRECTION_MAX_CHARS))).toBe(true);
	});

	it('rejects blank / whitespace-only text (trims first)', () => {
		expect(isPinSubmittable('')).toBe(false);
		expect(isPinSubmittable('   \n\t ')).toBe(false);
	});

	it('rejects text past the body cap (after trim)', () => {
		expect(isPinSubmittable('x'.repeat(CORRECTION_MAX_CHARS + 1))).toBe(false);
		// surrounding whitespace doesn't count toward the cap
		expect(isPinSubmittable(`  ${'x'.repeat(CORRECTION_MAX_CHARS)}  `)).toBe(true);
	});
});

describe('factCorrectionPrefill', () => {
	it('wraps a short fact as a single-line "Re: …" reply stub', () => {
		expect(factCorrectionPrefill('Liability cap is 12 months of fees.')).toBe(
			'Re: "Liability cap is 12 months of fees." → '
		);
	});

	it('collapses internal whitespace to a single line', () => {
		expect(factCorrectionPrefill('Governing law\n is  England\t& Wales')).toBe(
			'Re: "Governing law is England & Wales" → '
		);
	});

	it('truncates a long fact with an ellipsis (keeps the stub readable)', () => {
		const long = 'A'.repeat(200);
		const out = factCorrectionPrefill(long);
		expect(out.startsWith('Re: "')).toBe(true);
		expect(out.endsWith('… " → ') || out.endsWith('…" → ')).toBe(true);
		// excerpt is bounded well under the full 200 chars
		expect(out.length).toBeLessThan(100);
	});
});

// --- Authorship roster (ADR-F048) ------------------------------------------------

describe('sideLabel', () => {
	it('maps each side to a friendly label', () => {
		expect(sideLabel('ours')).toBe('Ours');
		expect(sideLabel('counterparty')).toBe('Counterparty');
		expect(sideLabel('unknown')).toBe('Unknown');
	});
	it('passes an unrecognised side through unchanged', () => {
		expect(sideLabel('other')).toBe('other');
	});
	it('has a label for every known side', () => {
		for (const s of PARTICIPANT_SIDES) expect(sideLabel(s).length).toBeGreaterThan(0);
	});
});

describe('sideToneClass', () => {
	it('uses the brand accent for our side and amber for the counterparty', () => {
		expect(sideToneClass('ours')).toContain('brand');
		expect(sideToneClass('counterparty')).toContain('amber');
	});
	it('falls back to a muted tone for unknown/other', () => {
		expect(sideToneClass('unknown')).toContain('muted');
		expect(sideToneClass('other')).toContain('muted');
	});
});

describe('participantTrustLabel', () => {
	it('distinguishes a confirmed entry from an inferred one', () => {
		expect(participantTrustLabel('confirmed')).toBe('Confirmed');
		expect(participantTrustLabel('inferred')).toBe('Inferred');
	});
});

describe('parseAliases', () => {
	it('splits on commas and newlines, trims, and drops blanks', () => {
		expect(parseAliases('Jane Smith, jsmith@acme.com\n  J. Smith ')).toEqual([
			'Jane Smith',
			'jsmith@acme.com',
			'J. Smith'
		]);
	});
	it('dedupes case-insensitively (keeps the first form)', () => {
		expect(parseAliases('Jane, JANE, jane')).toEqual(['Jane']);
	});
	it('is empty for a blank string', () => {
		expect(parseAliases('   ,\n , ')).toEqual([]);
	});
});

describe('isParticipantSubmittable', () => {
	it('needs a name and a valid side', () => {
		expect(isParticipantSubmittable('Jane', 'ours')).toBe(true);
		expect(isParticipantSubmittable('Jane', 'counterparty')).toBe(true);
		expect(isParticipantSubmittable('Jane', 'unknown')).toBe(true);
	});
	it('rejects a blank name or an invalid side', () => {
		expect(isParticipantSubmittable('   ', 'ours')).toBe(false);
		expect(isParticipantSubmittable('Jane', 'enemy')).toBe(false);
		expect(isParticipantSubmittable('Jane', '')).toBe(false);
	});
});
