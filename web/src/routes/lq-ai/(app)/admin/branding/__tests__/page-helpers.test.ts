/**
 * /lq-ai/admin/branding helper tests — BRAND-1b (ADR-F068).
 *
 * WCAG contrast math, the dark-accent suggestion, and the seeder-mirroring
 * accent fan-out (parity with `_accent_fan_out`/`_blend_hex` in
 * `api/app/admin_bootstrap.py` — same channel math, same alphas).
 */
import { describe, expect, it } from 'vitest';

import {
	DARK_CANVAS,
	DEFAULT_ACCENT_DARK,
	LIGHT_CANVAS,
	accentFanOut,
	accentFromPalette,
	accentWarnings,
	blendHex,
	buildPaletteBody,
	contrastRatio,
	parseHex,
	relativeLuminance,
	suggestDarkAccent,
	validateAccentHex,
	validateProductName
} from '../page-helpers';

const HEX6 = /^#[0-9a-f]{6}$/i;

describe('parseHex', () => {
	it('parses #RRGGBB channels', () => {
		expect(parseHex('#0070f3')).toEqual({ r: 0, g: 112, b: 243 });
		expect(parseHex('#FFFFFF')).toEqual({ r: 255, g: 255, b: 255 });
	});

	it('rejects anything else', () => {
		for (const bad of ['#fff', '#12345', '#1234567', 'red', '0070f3', '#gg0000', '']) {
			expect(parseHex(bad)).toBeNull();
		}
	});
});

describe('WCAG contrast math', () => {
	it('relative luminance: black 0, white 1', () => {
		expect(relativeLuminance('#000000')).toBe(0);
		expect(relativeLuminance('#ffffff')).toBeCloseTo(1, 5);
	});

	it('black vs white is 21:1; identical colours are 1:1', () => {
		expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 1);
		expect(contrastRatio('#0070f3', '#0070f3')).toBeCloseTo(1, 5);
	});

	it('is symmetric', () => {
		expect(contrastRatio('#0070f3', '#ffffff')).toBeCloseTo(
			contrastRatio('#ffffff', '#0070f3'),
			10
		);
	});

	it('matches the known value for the shipped accent on white (~4.55:1)', () => {
		const ratio = contrastRatio('#0070f3', LIGHT_CANVAS);
		expect(ratio).toBeGreaterThan(4.4);
		expect(ratio).toBeLessThan(4.7);
	});
});

describe('accentWarnings', () => {
	it('a near-canvas accent fails both thresholds (<3:1)', () => {
		const warnings = accentWarnings('#ffff00', LIGHT_CANVAS); // yellow on white ≈1.07:1
		expect(warnings).toHaveLength(2);
		expect(warnings[0]).toContain('3:1');
		expect(warnings[1]).toContain('4.5:1');
	});

	it('a mid-range accent warns for text only (3:1 ≤ ratio < 4.5:1)', () => {
		// #0070f3 on charcoal #111111 ≈ 4.15:1 — fine for UI, short for text.
		const warnings = accentWarnings('#0070f3', DARK_CANVAS);
		expect(warnings).toHaveLength(1);
		expect(warnings[0]).toContain('4.5:1');
	});

	it('a high-contrast accent produces no warnings', () => {
		expect(accentWarnings('#000000', LIGHT_CANVAS)).toEqual([]);
		expect(accentWarnings('#ffffff', DARK_CANVAS)).toEqual([]);
	});

	it('returns nothing for invalid input (the hex error handles that)', () => {
		expect(accentWarnings('nope', LIGHT_CANVAS)).toEqual([]);
	});
});

describe('suggestDarkAccent', () => {
	it('returns a valid hex, lighter than the input', () => {
		const suggested = suggestDarkAccent('#0070f3');
		expect(suggested).toMatch(HEX6);
		expect(relativeLuminance(suggested)).toBeGreaterThan(relativeLuminance('#0070f3'));
	});

	it('falls back to the shipped dark accent for invalid input', () => {
		expect(suggestDarkAccent('garbage')).toBe(DEFAULT_ACCENT_DARK);
	});
});

describe('accentFanOut (seeder parity)', () => {
	it('fans the light accent out exactly like the seeder (8% wash over white)', () => {
		const out = accentFanOut('#0070f3', 'light');
		expect(out).toEqual({
			brand: '#0070f3',
			brand_foreground: '#ffffff',
			ring: '#0070f3',
			sidebar_ring: '#0070f3',
			status_running: '#0070f3',
			// _blend_hex('#0070f3', '#ffffff', 0.08) in the seeder.
			status_running_wash: '#ebf4fe',
			chart_1: '#0070f3'
		});
	});

	it('dark theme pairs ink foreground + 16% wash over the charcoal canvas', () => {
		const out = accentFanOut('#47a3ff', 'dark');
		expect(out.brand_foreground).toBe('#111111');
		expect(out.status_running_wash).toBe(blendHex('#47a3ff', DARK_CANVAS, 0.16));
		expect(out.status_running_wash).toMatch(HEX6);
	});

	it('buildPaletteBody: both themes when enabled, {} when disabled', () => {
		const body = buildPaletteBody(true, '#0070f3', '#47a3ff');
		expect(Object.keys(body).sort()).toEqual(['dark', 'light']);
		expect(Object.keys(body.light)).toHaveLength(7);
		expect(Object.keys(body.dark)).toHaveLength(7);
		expect(buildPaletteBody(false, '#0070f3', '#47a3ff')).toEqual({});
	});

	it('accentFromPalette reads the accent back (round-trip) or falls back', () => {
		const body = buildPaletteBody(true, '#336699', '#6699cc');
		const palette = { light: body.light, dark: body.dark };
		expect(accentFromPalette(palette, 'light', '#000000')).toBe('#336699');
		expect(accentFromPalette(palette, 'dark', '#000000')).toBe('#6699cc');
		expect(accentFromPalette({ light: {}, dark: {} }, 'light', '#0070f3')).toBe('#0070f3');
	});
});

describe('field validation', () => {
	it('validateProductName: empty ok (restores default), >80 and control chars rejected', () => {
		expect(validateProductName('')).toBeNull();
		expect(validateProductName('Acme Legal')).toBeNull();
		expect(validateProductName('x'.repeat(80))).toBeNull();
		expect(validateProductName('x'.repeat(81))).not.toBeNull();
		expect(validateProductName('Acme\r\nBcc: evil')).not.toBeNull();
		expect(validateProductName('Acme\u2028line')).not.toBeNull();
	});

	it('validateAccentHex: #RRGGBB only', () => {
		expect(validateAccentHex('#0070f3')).toBeNull();
		expect(validateAccentHex('#AABBCC')).toBeNull();
		for (const bad of ['#fff', 'blue', '#0070f', '#0070f3f', '0070f3']) {
			expect(validateAccentHex(bad)).not.toBeNull();
		}
	});
});
