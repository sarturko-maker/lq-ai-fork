/**
 * Cockpit helper logic — F1-S2. URL-state codec round-trips, view
 * derivation (the cockpit LANDS on the area list), relative time, and
 * the theme cycle contract shared with app.html's pre-paint script.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { describe, expect, it, vi } from 'vitest';

import type { AgentRunStatus } from '$lib/lq-ai/api/agents';
import {
	areaActivityCounts,
	cockpitUrl,
	mattersForArea,
	MOTION,
	motionMs,
	nextTheme,
	normalizeTheme,
	parseCockpitState,
	runDot,
	timeAgo,
	viewOf,
	type CockpitState
} from '../helpers';

type FakeMatter = {
	practice_area_key: string | null;
	last_run_at: string | null;
	last_run_status: AgentRunStatus | null;
};

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

describe('area grouping (F1-S3 — matters file by practice_area_key)', () => {
	const matters: FakeMatter[] = [
		{
			practice_area_key: 'commercial',
			last_run_at: '2026-06-13T10:00:00Z',
			last_run_status: 'completed'
		},
		{
			practice_area_key: 'commercial',
			last_run_at: '2026-06-12T10:00:00Z',
			last_run_status: 'failed'
		},
		{ practice_area_key: 'privacy', last_run_at: null, last_run_status: null },
		{ practice_area_key: null, last_run_at: '2026-06-11T10:00:00Z', last_run_status: 'completed' } // unfiled
	];

	it('counts per area and takes the first (latest) activity + status, skipping unfiled', () => {
		const byArea = areaActivityCounts(matters);
		// The FIRST matter per area is the latest, so its status is the area's.
		expect(byArea.get('commercial')).toEqual({
			count: 2,
			lastActivity: '2026-06-13T10:00:00Z',
			lastStatus: 'completed'
		});
		expect(byArea.get('privacy')).toEqual({ count: 1, lastActivity: null, lastStatus: null });
		// The unfiled matter (null key) is not grouped under any area.
		expect(byArea.has('')).toBe(false);
		expect([...byArea.keys()].sort()).toEqual(['commercial', 'privacy']);
	});

	it('filters matters to one area, never leaking another area or unfiled', () => {
		expect(mattersForArea(matters, 'commercial')).toHaveLength(2);
		expect(mattersForArea(matters, 'privacy')).toHaveLength(1);
		expect(mattersForArea(matters, 'disputes')).toEqual([]);
	});
});

describe('runDot (F2-VL2 — settled status → calm dot, via statusBadge)', () => {
	const NOW = Date.parse('2026-06-15T12:00:00Z');
	const recent = '2026-06-15T11:59:00Z'; // 1m ago — not stale

	it('maps the settled tones onto the StatusDot tones + the canonical labels', () => {
		expect(runDot('completed', recent, NOW)).toEqual({ dot: 'completed', label: 'Completed' });
		expect(runDot('running', recent, NOW)).toEqual({ dot: 'running', label: 'Working…' });
		expect(runDot('failed', recent, NOW)).toEqual({ dot: 'failed', label: 'Failed' });
		expect(runDot('cancelled', recent, NOW)).toEqual({ dot: 'cancelled', label: 'Cancelled' });
	});

	it('routes cap_exceeded + the stale-running belt to the attention tone', () => {
		// cap_exceeded → warn → attention.
		expect(runDot('cap_exceeded', recent, NOW)).toEqual({
			dot: 'attention',
			label: 'Step cap reached'
		});
		// A run "running" since long before NOW is stale (warn → attention).
		expect(runDot('running', '2026-06-15T11:50:00Z', NOW)).toEqual({
			dot: 'attention',
			label: 'Stale'
		});
	});

	it('treats no runs yet (null status) as faint idle', () => {
		expect(runDot(null, null, NOW)).toEqual({ dot: 'idle', label: 'No runs yet' });
	});
});

describe('motionMs (F1-S2.1 reduced-motion gate)', () => {
	it('passes durations through normally and zeroes them under prefers-reduced-motion', () => {
		const matchMedia = vi.fn().mockReturnValue({ matches: false });
		vi.stubGlobal('matchMedia', matchMedia);
		try {
			expect(motionMs(120)).toBe(120);
			expect(matchMedia).toHaveBeenCalledWith('(prefers-reduced-motion: reduce)');
			matchMedia.mockReturnValue({ matches: true });
			expect(motionMs(120)).toBe(0);
		} finally {
			vi.unstubAllGlobals();
		}
	});
});

describe('MOTION scale (F013 VL0)', () => {
	// The JS mirror exists because Svelte's JS transitions take a number, not a
	// CSS var. This test is the sync lock: it parses the canonical `--motion-*`
	// tokens out of app.css and asserts MOTION matches them, so the two can't
	// drift silently.
	const appCss = readFileSync(
		fileURLToPath(new URL('../../../../app.css', import.meta.url)),
		'utf8'
	);
	const cssMs = (name: string): number => {
		const m = appCss.match(new RegExp(`--motion-${name}:\\s*(\\d+)ms`));
		if (!m) throw new Error(`--motion-${name} not found in app.css`);
		return Number(m[1]);
	};

	it('mirrors the CSS --motion-* duration tokens', () => {
		expect(MOTION.fast).toBe(cssMs('fast'));
		expect(MOTION.base).toBe(cssMs('base'));
		expect(MOTION.slow).toBe(cssMs('slow'));
	});
});
