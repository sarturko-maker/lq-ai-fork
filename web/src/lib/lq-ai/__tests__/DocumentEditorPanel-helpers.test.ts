/**
 * Unit tests for the in-app Word editor chrome's pure presenters (ADR-F047,
 * Slice 4). No @testing-library/svelte in this codebase, so the panel exports
 * its decision functions from `<script module>` and we exercise those here; the
 * iframe/launch glue is covered by the Cypress spec + the live check.
 */
import { describe, expect, it } from 'vitest';

import {
	saveStateLabel,
	saveStatePulses,
	saveStateTone
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
