/**
 * Cockpit helper logic — F1-S2. URL-state codec round-trips, view
 * derivation (the cockpit LANDS on the area list), relative time, and
 * the theme cycle contract shared with app.html's pre-paint script.
 */
import { describe, expect, it } from 'vitest';

import {
	cockpitUrl,
	nextTheme,
	normalizeTheme,
	parseCockpitState,
	timeAgo,
	viewOf,
	type CockpitState
} from '../helpers';

function stateOf(url: string): CockpitState {
	return parseCockpitState(new URL(`http://x${url}`).searchParams);
}

describe('cockpit URL state', () => {
	it('lands on the area list with no params', () => {
		const sel = stateOf('/lq-ai');
		expect(sel).toEqual({ area: null, matter: null, thread: null, unfiled: false });
		expect(viewOf(sel)).toBe('areas');
	});

	it('round-trips area → matters view', () => {
		const sel = stateOf(cockpitUrl({ area: 'commercial' }));
		expect(sel.area).toBe('commercial');
		expect(viewOf(sel)).toBe('matters');
	});

	it('round-trips matter + thread → matter view', () => {
		const url = cockpitUrl({ area: 'commercial', matter: 'p-1', thread: 't-1' });
		const sel = stateOf(url);
		expect(sel).toEqual({ area: 'commercial', matter: 'p-1', thread: 't-1', unfiled: false });
		expect(viewOf(sel)).toBe('matter');
	});

	it('unfiled view drops area/matter and keeps the thread', () => {
		const url = cockpitUrl({ unfiled: true, area: 'commercial', matter: 'p-1', thread: 't-9' });
		const sel = stateOf(url);
		expect(sel.area).toBeNull();
		expect(sel.matter).toBeNull();
		expect(sel.thread).toBe('t-9');
		expect(viewOf(sel)).toBe('unfiled');
	});

	it('omits empty params entirely', () => {
		expect(cockpitUrl({})).toBe('/lq-ai');
		expect(cockpitUrl({ area: 'commercial', thread: null })).toBe('/lq-ai?area=commercial');
	});
});

describe('timeAgo', () => {
	const now = Date.parse('2026-06-12T12:00:00Z');

	it.each([
		['2026-06-12T11:59:40Z', 'just now'],
		['2026-06-12T11:48:00Z', '12m ago'],
		['2026-06-12T09:00:00Z', '3h ago'],
		['2026-06-11T08:00:00Z', 'yesterday'],
		['2026-06-05T12:00:00Z', '7d ago']
	])('%s → %s', (iso, expected) => {
		expect(timeAgo(iso, now)).toBe(expected);
	});

	it('falls back to a date beyond 30 days and an em dash for null/garbage', () => {
		expect(timeAgo('2026-01-01T00:00:00Z', now)).toBe(
			new Date('2026-01-01T00:00:00Z').toLocaleDateString()
		);
		expect(timeAgo(null, now)).toBe('—');
		expect(timeAgo('not-a-date', now)).toBe('—');
	});
});

describe('theme cycle (app.html contract)', () => {
	it('cycles system → light → dark → system', () => {
		expect(nextTheme('system')).toBe('light');
		expect(nextTheme('light')).toBe('dark');
		expect(nextTheme('dark')).toBe('system');
	});

	it('normalizes storage values like the pre-paint script', () => {
		expect(normalizeTheme(null)).toBe('system');
		expect(normalizeTheme('system')).toBe('system');
		expect(normalizeTheme('light')).toBe('light');
		expect(normalizeTheme('dark')).toBe('dark');
		// Legacy values render dark — same rule as app.html.
		expect(normalizeTheme('oled-dark')).toBe('dark');
	});
});
