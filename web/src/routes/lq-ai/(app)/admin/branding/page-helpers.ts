/**
 * Pure helpers for the /lq-ai/admin/branding page — BRAND-1b (ADR-F068).
 *
 * Extracted out of `+page.svelte` so vitest can exercise them without a
 * SvelteKit runtime (Users-page precedent — no @testing-library/svelte).
 *
 * The accent fan-out and wash blend MIRROR the first-boot env seeder
 * (`api/app/admin_bootstrap.py` — `_accent_fan_out` / `_blend_hex`), so an
 * admin picking the same accent the wizard seeded produces byte-identical
 * palettes. The WCAG contrast math follows the standard relative-luminance
 * formula (WCAG 2.x §1.4.3/§1.4.11).
 */

import {
	HEX_COLOR_RE,
	PRODUCT_NAME_CONTROL_CHARS_RE,
	PRODUCT_NAME_MAX,
	type BrandingPalette,
	type PaletteToken
} from '$lib/lq-ai/branding/store';

/** Shipped default accents (app.css `--brand` light/dark) — the pickers'
 *  initial values on an unbranded install. */
export const DEFAULT_ACCENT_LIGHT = '#0070f3';
export const DEFAULT_ACCENT_DARK = '#47a3ff';

/** The theme canvases the accent sits on (F013: white / charcoal #111). */
export const LIGHT_CANVAS = '#ffffff';
export const DARK_CANVAS = '#111111';

// ---------------------------------------------------------------------------
// Colour math
// ---------------------------------------------------------------------------

export interface Rgb {
	r: number;
	g: number;
	b: number;
}

/** Parse `#RRGGBB` → channels, or null for anything else (no shorthand). */
export function parseHex(value: string): Rgb | null {
	if (!HEX_COLOR_RE.test(value)) return null;
	return {
		r: parseInt(value.slice(1, 3), 16),
		g: parseInt(value.slice(3, 5), 16),
		b: parseInt(value.slice(5, 7), 16)
	};
}

function toHexChannel(n: number): string {
	return Math.round(n).toString(16).padStart(2, '0');
}

/** Blend `fg` over `bg` at `alpha` opacity — the client mirror of the
 *  seeder's `_blend_hex` (pure integer channel math). */
export function blendHex(fg: string, bg: string, alpha: number): string {
	const f = parseHex(fg);
	const b = parseHex(bg);
	if (!f || !b) return fg;
	const channel = (fc: number, bc: number) => toHexChannel(fc * alpha + bc * (1 - alpha));
	return `#${channel(f.r, b.r)}${channel(f.g, b.g)}${channel(f.b, b.b)}`;
}

/** WCAG 2.x relative luminance of a `#RRGGBB` colour (0 = black, 1 = white). */
export function relativeLuminance(hex: string): number {
	const rgb = parseHex(hex);
	if (!rgb) return 0;
	const linear = (channel: number): number => {
		const c = channel / 255;
		return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
	};
	return 0.2126 * linear(rgb.r) + 0.7152 * linear(rgb.g) + 0.0722 * linear(rgb.b);
}

/** WCAG contrast ratio between two `#RRGGBB` colours (1:1 … 21:1). */
export function contrastRatio(a: string, b: string): number {
	const la = relativeLuminance(a);
	const lb = relativeLuminance(b);
	const lighter = Math.max(la, lb);
	const darker = Math.min(la, lb);
	return (lighter + 0.05) / (darker + 0.05);
}

/**
 * Non-blocking WCAG warnings for an accent against its theme canvas:
 * <3:1 fails for UI elements (focus rings, status dots — WCAG 1.4.11);
 * <4.5:1 is below the text threshold (links render in the accent — 1.4.3).
 * Warnings, not gates — the server accepts any valid hex; the admin decides.
 */
export function accentWarnings(accent: string, canvas: string): string[] {
	if (!parseHex(accent) || !parseHex(canvas)) return [];
	const ratio = contrastRatio(accent, canvas);
	const shown = `${(Math.round(ratio * 100) / 100).toFixed(2)}:1`;
	const warnings: string[] = [];
	if (ratio < 3) {
		warnings.push(
			`Contrast ${shown} against ${canvas} is below 3:1 — focus rings and status markers may be hard to see (WCAG 1.4.11).`
		);
	}
	if (ratio < 4.5) {
		warnings.push(
			`Contrast ${shown} against ${canvas} is below 4.5:1 — link text in this colour will not meet WCAG AA (1.4.3).`
		);
	}
	return warnings;
}

/**
 * Suggest a dark-theme accent from the light one by lifting it toward white
 * (30%), echoing how the shipped pair relates (#0070f3 → #47a3ff). A
 * suggestion only — the admin can override the dark picker.
 */
export function suggestDarkAccent(lightAccent: string): string {
	if (!parseHex(lightAccent)) return DEFAULT_ACCENT_DARK;
	return blendHex('#ffffff', lightAccent, 0.3);
}

// ---------------------------------------------------------------------------
// Palette fan-out (mirror of the seeder — keep in sync)
// ---------------------------------------------------------------------------

/**
 * Fan one accent out into the 7-token brandable family, exactly like the
 * first-boot seeder (`_accent_fan_out`):
 * `brand = ring = sidebar_ring = status_running = chart_1 = accent`;
 * `brand_foreground` is white on light / ink on dark (the shipped pairing);
 * the wash is the accent blended into the theme canvas (8% over white /
 * 16% over #111111 — like the shipped #eef4ff / #14233a).
 */
export function accentFanOut(
	accent: string,
	theme: 'light' | 'dark'
): Partial<Record<PaletteToken, string>> {
	const foreground = theme === 'light' ? '#ffffff' : '#111111';
	const wash =
		theme === 'light' ? blendHex(accent, LIGHT_CANVAS, 0.08) : blendHex(accent, DARK_CANVAS, 0.16);
	return {
		brand: accent,
		brand_foreground: foreground,
		ring: accent,
		sidebar_ring: accent,
		status_running: accent,
		status_running_wash: wash,
		chart_1: accent
	};
}

/** Build the PUT palette body: both themes fanned out, or `{}` when the
 *  admin turned the custom accent off (restores the shipped blue). */
export function buildPaletteBody(
	accentEnabled: boolean,
	accentLight: string,
	accentDark: string
): Record<string, Record<string, string>> {
	if (!accentEnabled) return {};
	return {
		light: accentFanOut(accentLight, 'light') as Record<string, string>,
		dark: accentFanOut(accentDark, 'dark') as Record<string, string>
	};
}

/** Read the stored accent back out of a saved palette (the fan-out is
 *  lossless for the accent itself — it IS `brand`). */
export function accentFromPalette(
	palette: BrandingPalette,
	theme: 'light' | 'dark',
	fallback: string
): string {
	const value = palette[theme].brand;
	return typeof value === 'string' && HEX_COLOR_RE.test(value) ? value : fallback;
}

// ---------------------------------------------------------------------------
// Field validation (client pre-flight; the server 422 is authoritative)
// ---------------------------------------------------------------------------

/** Mirrors the PUT boundary: ≤80 chars, no control characters (the name
 *  lands in SMTP subject headers; the regex is the store's — one predicate,
 *  no drift against sanitizeName). Empty is VALID — it restores the default
 *  brand. Returns an error message or null. */
export function validateProductName(name: string): string | null {
	if (name.length > PRODUCT_NAME_MAX) {
		return `Product name must be at most ${PRODUCT_NAME_MAX} characters.`;
	}
	if (PRODUCT_NAME_CONTROL_CHARS_RE.test(name)) {
		return 'Product name must not contain control characters.';
	}
	return null;
}

/** `#RRGGBB` or an error message. */
export function validateAccentHex(value: string): string | null {
	return HEX_COLOR_RE.test(value) ? null : 'Enter a 6-digit hex colour like #0070f3.';
}
