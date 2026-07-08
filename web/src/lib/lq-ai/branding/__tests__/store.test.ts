/**
 * Branding-store unit tests — BRAND-1b (ADR-F068).
 *
 * Pure-function coverage only (no component mounting — the repo has no
 * @testing-library/svelte): hostile localStorage payload validation,
 * dual-scope CSS generation (the setProperty-vs-style-tag trap), and the
 * title helper. Runs in the node environment; the store module feature-
 * detects the browser and no-ops its DOM paths here.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { beforeEach, describe, expect, it } from 'vitest';
import { get } from 'svelte/store';

import {
	ALLOWED_PALETTE_TOKENS,
	BRANDING_STORAGE_KEY,
	BRANDING_STYLE_TAG_ID,
	DEFAULT_PRODUCT_NAME,
	HEX_COLOR_RE,
	PALETTE_TOKEN_CSS_VARS,
	PRODUCT_NAME_CONTROL_CHARS_RE,
	PRODUCT_NAME_MAX,
	branding,
	buildBrandingCss,
	defaultBranding,
	formatPageTitle,
	sanitizeBranding,
	sanitizePalette,
	titleFor
} from '../store';

beforeEach(() => {
	branding.set(defaultBranding());
});

describe('sanitizePalette', () => {
	it('keeps the full 7-token allowlist when every value is valid hex', () => {
		const input = {
			light: {
				brand: '#0070f3',
				brand_foreground: '#ffffff',
				ring: '#0070f3',
				sidebar_ring: '#0070f3',
				status_running: '#0070f3',
				status_running_wash: '#eef4ff',
				chart_1: '#0070f3'
			},
			dark: { brand: '#47a3ff' }
		};
		const out = sanitizePalette(input);
		expect(Object.keys(out.light).sort()).toEqual([...ALLOWED_PALETTE_TOKENS].sort());
		expect(out.dark).toEqual({ brand: '#47a3ff' });
	});

	it('drops unknown tokens (closed allowlist)', () => {
		const out = sanitizePalette({
			light: { brand: '#112233', primary: '#000000', background: '#ff0000', evil: '#aabbcc' }
		});
		expect(out.light).toEqual({ brand: '#112233' });
	});

	it('drops values that are not exactly #RRGGBB', () => {
		const out = sanitizePalette({
			light: {
				brand: '#12345', // too short
				ring: '#1234567', // too long
				sidebar_ring: 'red', // keyword
				status_running: '#gg0000', // bad hex digits
				status_running_wash: '#0070f3;} body{display:none', // CSS injection attempt
				chart_1: 'url(https://evil.example/x)',
				brand_foreground: '#AABBCC' // valid — uppercase hex allowed
			}
		});
		expect(out.light).toEqual({ brand_foreground: '#AABBCC' });
	});

	it('drops nested garbage (arrays / numbers / objects in place of strings)', () => {
		const out = sanitizePalette({
			light: { brand: ['#0070f3'], ring: 42, chart_1: { hex: '#0070f3' }, sidebar_ring: null }
		});
		expect(out.light).toEqual({});
	});

	it('drops unknown themes and non-object themes', () => {
		const out = sanitizePalette({
			light: { brand: '#0070f3' },
			hcm: { brand: '#ff0000' },
			dark: ['#47a3ff']
		});
		expect(Object.keys(out).sort()).toEqual(['dark', 'light']);
		expect(out.dark).toEqual({});
	});

	it('returns empty themes for a non-object palette', () => {
		for (const raw of [null, undefined, 'brand', 12, ['light']]) {
			expect(sanitizePalette(raw)).toEqual({ light: {}, dark: {} });
		}
	});
});

describe('sanitizeBranding (hostile localStorage payloads)', () => {
	it('degrades non-object payloads to the default brand', () => {
		for (const raw of [null, undefined, 'Acme', 7, ['Acme']]) {
			expect(sanitizeBranding(raw)).toEqual(defaultBranding());
		}
	});

	it('accepts a valid cached payload', () => {
		const state = sanitizeBranding({
			name: 'Acme Legal',
			palette: { light: { brand: '#336699' } },
			logoVersion: 1751900000000
		});
		expect(state.productName).toBe('Acme Legal');
		expect(state.customName).toBe(true);
		expect(state.palette.light).toEqual({ brand: '#336699' });
		expect(state.logoVersion).toBe(1751900000000);
	});

	it('rejects (not truncates) an overlong or control-char name', () => {
		expect(sanitizeBranding({ name: 'x'.repeat(81) }).productName).toBe(DEFAULT_PRODUCT_NAME);
		expect(sanitizeBranding({ name: 'Acme\r\nBcc: evil' }).productName).toBe(
			DEFAULT_PRODUCT_NAME
		);
		expect(sanitizeBranding({ name: 'Acme\u2028line' }).customName).toBe(false);
		expect(sanitizeBranding({ name: 42 }).customName).toBe(false);
	});

	it('rejects non-integer logo versions (it lands in a URL)', () => {
		expect(sanitizeBranding({ name: 'A', logoVersion: '123' }).logoVersion).toBeNull();
		expect(sanitizeBranding({ name: 'A', logoVersion: 1.5 }).logoVersion).toBeNull();
		expect(sanitizeBranding({ name: 'A', logoVersion: -3 }).logoVersion).toBeNull();
		expect(sanitizeBranding({ name: 'A', logoVersion: Infinity }).logoVersion).toBeNull();
	});
});

describe('buildBrandingCss (dual-scope style tag)', () => {
	it('emits BOTH scopes at DOUBLED specificity — :root:root/:root.dark (0,2,0) beat app.css\'s unlayered :root/.dark (0,1,0) regardless of sheet order (the pre-paint tag precedes the app stylesheet), and inline setProperty on <html> would outrank .dark and break theme switching', () => {
		// Even a light-only palette must produce both blocks, so a later dark
		// entry lands in the right scope and stale dark values get cleared.
		const css = buildBrandingCss({ light: { brand: '#336699' }, dark: {} });
		expect(css.startsWith(':root:root{')).toBe(true);
		expect(css).toContain('\n:root.dark{');
		// Plain single-specificity scopes would lose the cascade to app.css.
		expect(css).not.toMatch(/(^|\n):root\{/);
		expect(css).not.toMatch(/(^|\n)\.dark\{/);
	});

	it('maps wire token names to the CSS custom properties', () => {
		const css = buildBrandingCss({
			light: {
				brand: '#111213',
				brand_foreground: '#ffffff',
				ring: '#111213',
				sidebar_ring: '#111213',
				status_running: '#111213',
				status_running_wash: '#eef4ff',
				chart_1: '#111213'
			},
			dark: { brand: '#a1b2c3' }
		});
		expect(css).toContain('--brand:#111213;');
		expect(css).toContain('--brand-foreground:#ffffff;');
		expect(css).toContain('--ring:#111213;');
		expect(css).toContain('--sidebar-ring:#111213;');
		expect(css).toContain('--status-running:#111213;');
		expect(css).toContain('--status-running-wash:#eef4ff;');
		expect(css).toContain('--chart-1:#111213;');
		expect(css).toContain(':root.dark{--brand:#a1b2c3;}');
	});

	it('re-validates at the injection site: bad values never reach the CSS', () => {
		const css = buildBrandingCss({
			// Cast: simulate a tampered object handed straight to the builder.
			light: {
				brand: '#0070f3;} * {display:none',
				ring: 'javascript:alert(1)'
			} as Record<string, string>,
			dark: {}
		} as never);
		expect(css).toBe(':root:root{}\n:root.dark{}');
	});

	it('produces empty scopes for an empty palette (clears stale values on rewrite)', () => {
		expect(buildBrandingCss({ light: {}, dark: {} })).toBe(':root:root{}\n:root.dark{}');
	});
});

describe('app.html pre-paint script sync lock (MOTION-test precedent)', () => {
	// The inline app.html script re-declares the branding validation constants
	// (it is vanilla JS — it cannot import this module). These tests parse the
	// real app.html and assert the duplicates match the store's exports, so
	// the two sides can't drift silently (e.g. an 8th allowlisted token added
	// here but not there would silently drop pre-paint).
	const appHtml = readFileSync(
		fileURLToPath(new URL('../../../../app.html', import.meta.url)),
		'utf8'
	);

	it('mirrors PALETTE_TOKEN_CSS_VARS in the inline TOKENS literal (exactly — no missing, no extra keys)', () => {
		const literal = appHtml.match(/const TOKENS = \{([\s\S]*?)\};/);
		if (!literal) throw new Error('const TOKENS literal not found in app.html');
		const pairs = [...literal[1].matchAll(/(\w+):\s*'([^']+)'/g)].map((m) => [m[1], m[2]]);
		expect(Object.fromEntries(pairs)).toEqual(PALETTE_TOKEN_CSS_VARS);
	});

	it('mirrors the value/name validators (hex shape, name cap, control chars)', () => {
		expect(appHtml).toContain(`const HEX = /${HEX_COLOR_RE.source}/;`);
		expect(appHtml).toContain(`cached.name.length <= ${PRODUCT_NAME_MAX}`);
		expect(appHtml).toContain(PRODUCT_NAME_CONTROL_CHARS_RE.source);
	});

	it('mirrors the storage key, style-tag id and positive-integer logoVersion gate', () => {
		expect(appHtml).toContain(`localStorage.getItem('${BRANDING_STORAGE_KEY}')`);
		expect(appHtml).toContain(`style.id = '${BRANDING_STYLE_TAG_ID}';`);
		expect(appHtml).toContain('cached.logoVersion > 0');
	});

	it('emits the same doubled-specificity dual scopes as buildBrandingCss', () => {
		expect(appHtml).toContain(`':root:root{' + light + '}\\n:root.dark{' + dark + '}'`);
	});
});

describe('formatPageTitle / titleFor', () => {
	it('keeps the shipped default titles byte-identical', () => {
		expect(formatPageTitle('Playbooks', DEFAULT_PRODUCT_NAME, 'dot')).toBe(
			'Playbooks · LQ.AI Oscar Edition'
		);
		expect(formatPageTitle('Reset password', DEFAULT_PRODUCT_NAME)).toBe(
			'Reset password — LQ.AI Oscar Edition'
		);
		expect(formatPageTitle('Users', DEFAULT_PRODUCT_NAME, 'admin')).toBe(
			'Users — LQ.AI Oscar Edition admin'
		);
	});

	it('titleFor tracks the store', () => {
		expect(get(titleFor)('Playbooks', 'dot')).toBe('Playbooks · LQ.AI Oscar Edition');
		branding.set({
			...defaultBranding(),
			productName: 'Acme Legal',
			customName: true
		});
		expect(get(titleFor)('Playbooks', 'dot')).toBe('Playbooks · Acme Legal');
		expect(get(titleFor)('Branding', 'admin')).toBe('Branding — Acme Legal admin');
	});
});
