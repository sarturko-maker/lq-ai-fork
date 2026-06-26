/**
 * Unit tests for the in-app Word editor chrome's pure presenters (ADR-F047,
 * Slice 4). No @testing-library/svelte in this codebase, so the panel exports
 * its decision functions from `<script module>` and we exercise those here; the
 * iframe/launch glue is covered by the Cypress spec + the live check.
 */
import { describe, expect, it } from 'vitest';

import {
	canHandBack,
	handBackInstruction,
	nextFitAction,
	saveStateLabel,
	saveStatePulses,
	saveStateTone,
	saveTickOutcome
} from '../components/matter/DocumentEditorPanel.svelte';
import type { EditorSaveState } from '../api/editor';

const ALL: EditorSaveState[] = ['loading', 'clean', 'dirty', 'saving', 'saved'];

describe('saveStateLabel', () => {
	it('labels each state', () => {
		expect(saveStateLabel('loading')).toBe('Opening…');
		expect(saveStateLabel('saving')).toBe('Saving…');
		expect(saveStateLabel('dirty')).toBe('Unsaved changes');
		expect(saveStateLabel('saved')).toBe('Saved');
		expect(saveStateLabel('clean')).toBe('Saved');
	});
	it('never returns empty', () => {
		for (const s of ALL) expect(saveStateLabel(s).length).toBeGreaterThan(0);
	});
});

describe('saveStateTone', () => {
	it('warns only on unsaved edits', () => {
		expect(saveStateTone('dirty')).toBe('warning');
	});
	it('is positive when saved/clean', () => {
		expect(saveStateTone('saved')).toBe('positive');
		expect(saveStateTone('clean')).toBe('positive');
	});
	it('is neutral while in flight', () => {
		expect(saveStateTone('loading')).toBe('neutral');
		expect(saveStateTone('saving')).toBe('neutral');
	});
});

describe('saveStatePulses', () => {
	it('animates only the in-flight states', () => {
		expect(saveStatePulses('loading')).toBe(true);
		expect(saveStatePulses('saving')).toBe(true);
		expect(saveStatePulses('dirty')).toBe(false);
		expect(saveStatePulses('saved')).toBe(false);
		expect(saveStatePulses('clean')).toBe(false);
	});
});

describe('canHandBack', () => {
	it('is clickable once the editor is ready and nothing is in flight', () => {
		expect(canHandBack('ready', 'clean', false)).toBe(true);
		expect(canHandBack('ready', 'dirty', false)).toBe(true);
		expect(canHandBack('ready', 'saved', false)).toBe(true);
		// 'loading' (no Document_Loaded postMessage yet) is still clickable — the click
		// guarantees the save, so a flaky postMessage never traps the lawyer.
		expect(canHandBack('ready', 'loading', false)).toBe(true);
	});
	it('is disabled before the editor is ready, mid-save, or while handing back', () => {
		expect(canHandBack('loading', 'loading', false)).toBe(false);
		expect(canHandBack('error', 'clean', false)).toBe(false);
		expect(canHandBack('ready', 'saving', false)).toBe(false);
		expect(canHandBack('ready', 'clean', true)).toBe(false);
	});
});

describe('saveTickOutcome', () => {
	it('lands the hand-back only once the save is confirmed', () => {
		expect(saveTickOutcome(false, 'saved')).toBe('saved');
		expect(saveTickOutcome(false, 'clean')).toBe('saved');
	});
	it('fails (never hands back unsaved) when a save comes back to dirty', () => {
		expect(saveTickOutcome(true, 'dirty')).toBe('failed');
	});
	it('stays pending before a save is seen, or mid-save', () => {
		expect(saveTickOutcome(false, 'dirty')).toBe('pending'); // not yet saved — keep waiting
		expect(saveTickOutcome(true, 'saving')).toBe('pending');
		expect(saveTickOutcome(false, 'loading')).toBe('pending');
	});
});

describe('handBackInstruction', () => {
	it('names the document and asks the agent to re-read + incorporate', () => {
		const msg = handBackInstruction('Acme MSA (redlined).docx');
		expect(msg).toContain('Acme MSA (redlined).docx');
		expect(msg.toLowerCase()).toContain('re-read');
		expect(msg.toLowerCase()).toContain('incorporate');
	});
	it('is non-empty for any filename', () => {
		expect(handBackInstruction('x.docx').length).toBeGreaterThan(0);
	});
});

describe('nextFitAction', () => {
	const base = { zoom: 10, min: 1, max: 18 };

	it('grows one level when the doc underfills the pane (< 92%)', () => {
		// 853 / 1252 = 0.68 → grow (this is the real-world undershoot case)
		expect(nextFitAction({ ...base, docPx: 853, containerW: 1252 })).toEqual({
			kind: 'grow',
			zoom: 11
		});
		// just under the band
		expect(nextFitAction({ ...base, docPx: 919, containerW: 1000 })).toEqual({
			kind: 'grow',
			zoom: 11
		});
	});

	it('shrinks one level (and accepts) when the doc overflows the pane (> 99%)', () => {
		// 1475 / 1252 = 1.18 → overflow → back off to the highest no-overflow level
		expect(nextFitAction({ ...base, docPx: 1475, containerW: 1252 })).toEqual({
			kind: 'shrink',
			zoom: 9
		});
	});

	it('is done within the target band [92%, 99%]', () => {
		// 1229 / 1252 = 0.98 → the fit
		expect(nextFitAction({ ...base, docPx: 1229, containerW: 1252 })).toEqual({ kind: 'done' });
		expect(nextFitAction({ ...base, docPx: 950, containerW: 1000 })).toEqual({ kind: 'done' });
		// exact boundaries are in-band (not > / not <)
		expect(nextFitAction({ ...base, docPx: 990, containerW: 1000 })).toEqual({ kind: 'done' }); // 0.99
		expect(nextFitAction({ ...base, docPx: 920, containerW: 1000 })).toEqual({ kind: 'done' }); // 0.92
	});

	it('is done (no further step) when clamped at min/max', () => {
		// overflow but already at min zoom → accept
		expect(nextFitAction({ docPx: 2000, containerW: 1000, zoom: 1, min: 1, max: 18 })).toEqual({
			kind: 'done'
		});
		// underfill but already at max zoom → accept
		expect(nextFitAction({ docPx: 100, containerW: 1000, zoom: 18, min: 1, max: 18 })).toEqual({
			kind: 'done'
		});
	});

	it('is done when the map is not ready (missing/zero/negative inputs)', () => {
		expect(nextFitAction({ ...base, docPx: null, containerW: 1000 })).toEqual({ kind: 'done' });
		expect(nextFitAction({ ...base, docPx: 0, containerW: 1000 })).toEqual({ kind: 'done' });
		expect(nextFitAction({ ...base, docPx: -5, containerW: 1000 })).toEqual({ kind: 'done' });
		expect(nextFitAction({ ...base, docPx: 500, containerW: null })).toEqual({ kind: 'done' });
		expect(nextFitAction({ docPx: 500, containerW: 1000, zoom: NaN, min: 1, max: 18 })).toEqual({
			kind: 'done'
		});
	});

	it('converges by iteration without oscillating (grow → overflow → shrink → done)', () => {
		// Simulate the 1.2×/level scaling the real editor exhibits, at a pane width
		// where NO level lands inside [0.92, 0.99] — so the fit must overshoot and
		// back off, actually exercising the terminal-shrink path:
		//   L9 712/1000=0.712 → grow; L10 854=0.854 → grow; L11 1025=1.025 → shrink → L10.
		let zoom = 9;
		const docPxAt = (z: number) => 712 * Math.pow(1.2, z - 9); // 712 px at level 9
		const containerW = 1000;
		let steps = 0;
		let hitShrink = false;
		for (; steps < 20; steps++) {
			const a = nextFitAction({ docPx: docPxAt(zoom), containerW, zoom, min: 1, max: 18 });
			if (a.kind === 'done') break;
			zoom = a.zoom as number;
			if (a.kind === 'shrink') {
				// shrink is terminal in the caller (applyFitStep returns true) → stop here
				hitShrink = true;
				break;
			}
		}
		expect(hitShrink, 'fixture exercises the overflow back-off').toBe(true);
		expect(docPxAt(zoom) / containerW).toBeLessThanOrEqual(0.99); // no overflow
		expect(docPxAt(zoom) / containerW).toBeGreaterThan(0.8); // filled, not tiny
		expect(steps).toBeLessThan(8); // converges fast
	});
});
