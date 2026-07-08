/**
 * Deployment-branding store — BRAND-1b (fork, ADR-F068).
 *
 * The web half of white-labeling: a writable store carrying the effective
 * product name, validated accent palette and logo cache-buster, plus the
 * DOM plumbing that keeps three surfaces in sync with it:
 *
 * 1. the `#lq-branding` <style> tag (dual-scope `:root:root{}` + `:root.dark{}`
 *    rules built from the palette — see {@link buildBrandingCss} for why it is
 *    a style tag and NEVER `documentElement.style.setProperty`, and why the
 *    selector specificity is doubled),
 * 2. `document.title` (bare-brand fallback pages only — svelte:head pages
 *    re-render reactively through {@link titleFor}),
 * 3. the favicon `<link rel="icon">` (repointed at the raster logo endpoint
 *    when a logo is set).
 *
 * Boot sequence (mirrors the anti-flash theme pattern in app.html):
 * the inline app.html script paints from the localStorage 'branding' cache
 * BEFORE first paint; this module hydrates the store from the same cache at
 * import time; {@link refreshBranding} (called from the auth-gate layout's
 * onMount, so it runs on every route incl. the pre-auth pages) then fetches
 * the authoritative state from the unauth GET /branding and reconciles.
 * The very FIRST visit has no cache and paints the default brand until the
 * fetch returns — accepted, same class as the theme flash pattern.
 *
 * SECURITY: localStorage is attacker-influenceable state (another-origin
 * XSS cannot reach it, but extensions / other-page XSS can) — every value
 * read from it is RE-validated here (closed token allowlist + `#RRGGBB`
 * shape) before it goes anywhere near a style tag. The product name renders
 * only through Svelte `{}` interpolation and `document.title` assignment —
 * both non-HTML sinks; it must never pass through `{@html}` or
 * renderModelMarkdown (hard line, ADR-F068).
 */

import { derived, get, writable } from 'svelte/store';

import { getBranding, logoUrl, type BrandingResponse } from '../api/branding';

// Direct feature-detection so this module is portable to the vitest node
// runner without SvelteKit alias setup (api/client.ts precedent).
const browser = typeof window !== 'undefined' && typeof window.localStorage !== 'undefined';

/** The default lockup name — rendered when no custom name is configured. */
export const DEFAULT_PRODUCT_NAME = 'LQ.AI Oscar Edition';

/** localStorage key for the pre-paint cache: `{name, palette, logoVersion}`.
 *  Read (and re-validated) by the inline app.html script — keep in sync
 *  (drift-guarded by `__tests__/store.test.ts`). */
export const BRANDING_STORAGE_KEY = 'branding';

/** id of the injected dual-scope style element — also created pre-paint by
 *  the app.html inline script; this module rewrites it in place. */
export const BRANDING_STYLE_TAG_ID = 'lq-branding';

/**
 * The CLOSED brandable-token allowlist (ADR-F068) — wire names → CSS custom
 * properties. Mirrors `ALLOWED_PALETTE_TOKENS` on the API model
 * (`api/app/models/deployment_branding.py`); `--primary` is ink by design
 * and deliberately NOT brandable. The legacy `--lq-*` set is never brandable
 * (hard line: those names never rename and stay untouched).
 */
export const PALETTE_TOKEN_CSS_VARS = {
	brand: '--brand',
	brand_foreground: '--brand-foreground',
	ring: '--ring',
	sidebar_ring: '--sidebar-ring',
	status_running: '--status-running',
	status_running_wash: '--status-running-wash',
	chart_1: '--chart-1'
} as const;

export type PaletteToken = keyof typeof PALETTE_TOKEN_CSS_VARS;

export const ALLOWED_PALETTE_TOKENS = Object.keys(PALETTE_TOKEN_CSS_VARS) as PaletteToken[];

/** Exactly `#RRGGBB` — the only value shape a palette entry may carry. */
export const HEX_COLOR_RE = /^#[0-9a-fA-F]{6}$/;

/** C0/C1 controls, DEL, and the line/paragraph separators — the same
 *  predicate the API's PUT boundary enforces on `product_name`. Exported so
 *  the admin page's client pre-flight validates with the SAME regex. */
// eslint-disable-next-line no-control-regex
export const PRODUCT_NAME_CONTROL_CHARS_RE = /[\u0000-\u001f\u007f-\u009f\u2028\u2029]/;

export const PRODUCT_NAME_MAX = 80;

export interface BrandingPalette {
	light: Partial<Record<PaletteToken, string>>;
	dark: Partial<Record<PaletteToken, string>>;
}

export interface BrandingState {
	/** Effective display name — {@link DEFAULT_PRODUCT_NAME} when unset. */
	productName: string;
	/** True when the deployment configured a custom product name. */
	customName: boolean;
	/** Sanitized palette — only allowlisted tokens with `#RRGGBB` values. */
	palette: BrandingPalette;
	/** Opaque cache-buster for the logo endpoint, or null when no logo. */
	logoVersion: number | null;
}

/** Fresh default-brand state (factory — callers may mutate their copy). */
export function defaultBranding(): BrandingState {
	return {
		productName: DEFAULT_PRODUCT_NAME,
		customName: false,
		palette: { light: {}, dark: {} },
		logoVersion: null
	};
}

// ---------------------------------------------------------------------------
// Validation (pure — unit-tested against hostile payloads)
// ---------------------------------------------------------------------------

function sanitizeThemeTokens(raw: unknown): Partial<Record<PaletteToken, string>> {
	const out: Partial<Record<PaletteToken, string>> = {};
	if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) return out;
	const record = raw as Record<string, unknown>;
	for (const token of ALLOWED_PALETTE_TOKENS) {
		const value = record[token];
		if (typeof value === 'string' && HEX_COLOR_RE.test(value)) {
			out[token] = value;
		}
	}
	return out;
}

/**
 * Reduce an untrusted palette-shaped value to the closed allowlist: unknown
 * themes/tokens dropped, every kept value matches `#RRGGBB`, nested garbage
 * (arrays, numbers, objects-in-place-of-strings) discarded silently.
 */
export function sanitizePalette(raw: unknown): BrandingPalette {
	if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) {
		return { light: {}, dark: {} };
	}
	const record = raw as Record<string, unknown>;
	return {
		light: sanitizeThemeTokens(record['light']),
		dark: sanitizeThemeTokens(record['dark'])
	};
}

/** Reject-don't-sanitize (CLAUDE.md boundary rule): a tampered/overlong name
 *  falls back to the default brand rather than rendering a truncation. */
function sanitizeName(raw: unknown): string {
	if (typeof raw !== 'string') return '';
	if (raw.length === 0 || raw.length > PRODUCT_NAME_MAX) return '';
	if (PRODUCT_NAME_CONTROL_CHARS_RE.test(raw)) return '';
	return raw;
}

function sanitizeLogoVersion(raw: unknown): number | null {
	return typeof raw === 'number' && Number.isInteger(raw) && raw > 0 ? raw : null;
}

/**
 * Build a {@link BrandingState} from an UNTRUSTED cache payload
 * (`{name, palette, logoVersion}` as written by {@link writeCache}).
 * Anything malformed degrades to the default brand, never throws.
 */
export function sanitizeBranding(raw: unknown): BrandingState {
	if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) {
		return defaultBranding();
	}
	const record = raw as Record<string, unknown>;
	const name = sanitizeName(record['name']);
	return {
		productName: name || DEFAULT_PRODUCT_NAME,
		customName: name !== '',
		palette: sanitizePalette(record['palette']),
		logoVersion: sanitizeLogoVersion(record['logoVersion'])
	};
}

/** Same reduction for the API response (defense in depth — the server
 *  already enforces the identical rules at the PUT boundary). */
export function brandingStateFromResponse(resp: BrandingResponse): BrandingState {
	const name = sanitizeName(resp.product_name);
	return {
		productName: name || DEFAULT_PRODUCT_NAME,
		customName: name !== '',
		palette: sanitizePalette(resp.palette),
		logoVersion: sanitizeLogoVersion(resp.logo_version)
	};
}

// ---------------------------------------------------------------------------
// CSS generation
// ---------------------------------------------------------------------------

function cssDeclarations(tokens: Partial<Record<PaletteToken, string>>): string {
	// Re-validate at the injection site (defense in depth): only allowlisted
	// tokens with `#RRGGBB` values can reach the style tag, regardless of
	// what the caller passed.
	return ALLOWED_PALETTE_TOKENS.filter(
		(token) => typeof tokens[token] === 'string' && HEX_COLOR_RE.test(tokens[token] as string)
	)
		.map((token) => `${PALETTE_TOKEN_CSS_VARS[token]}:${tokens[token]};`)
		.join('');
}

/**
 * Dual-scope stylesheet for the `#lq-branding` tag: a light block and a dark
 * block, matching the app.css token architecture so the theme class toggle
 * keeps working.
 *
 * The selector specificity is deliberately DOUBLED — `:root:root` and
 * `:root.dark`, both (0,2,0). The app.css token blocks (`:root` / `.dark`,
 * both (0,1,0)) are UNLAYERED, so at equal specificity the cascade falls
 * back to order-of-appearance — and the pre-paint tag created by the
 * app.html inline script always PRECEDES the app stylesheet link, which
 * would silently revert a cached custom palette to the shipped defaults on
 * every warm load. (0,2,0) beats app.css in both scopes regardless of sheet
 * order (same trick as practice.css's `:root.dark`, its lines 71–75).
 * Within the tag the dark block comes SECOND, so under `html.dark` it wins
 * over the light block at equal specificity; in light mode `:root.dark`
 * simply doesn't match. Caveat: both scopes always emit, and a light-only
 * palette (possible via a direct API PUT — the admin fan-out always writes
 * both themes) also overrides app.css's `.dark` defaults.
 *
 * NEVER replace this with `documentElement.style.setProperty(...)`: an
 * inline custom property on `<html>` outranks BOTH scope blocks, so the
 * dark variants would silently never apply (ADR-F068 §risks). A unit test
 * pins the presence of both scopes and the doubled specificity.
 */
export function buildBrandingCss(palette: BrandingPalette): string {
	return `:root:root{${cssDeclarations(palette.light)}}\n:root.dark{${cssDeclarations(palette.dark)}}`;
}

// ---------------------------------------------------------------------------
// Titles
// ---------------------------------------------------------------------------

/** Separator styles used by the shipped titles: app pages use `·`, pre-auth
 *  and top-level pages use `—`, admin pages add an ` admin` suffix. Keeping
 *  the historical separators means a default install's titles stay
 *  byte-identical (the Cypress rebrand pins still hold). */
export type TitleStyle = 'dot' | 'dash' | 'admin';

export function formatPageTitle(
	page: string,
	productName: string,
	style: TitleStyle = 'dash'
): string {
	if (style === 'dot') return `${page} · ${productName}`;
	if (style === 'admin') return `${page} — ${productName} admin`;
	return `${page} — ${productName}`;
}

// ---------------------------------------------------------------------------
// Store + DOM application
// ---------------------------------------------------------------------------

function initialState(): BrandingState {
	if (!browser) return defaultBranding();
	try {
		const raw = window.localStorage.getItem(BRANDING_STORAGE_KEY);
		if (!raw) return defaultBranding();
		return sanitizeBranding(JSON.parse(raw));
	} catch {
		// Corrupt cache — default brand until refreshBranding() reconciles.
		return defaultBranding();
	}
}

/**
 * The deployment's effective branding. Hydrated from the localStorage cache
 * at import time (no flash-of-default after the first visit) and reconciled
 * with the server by {@link refreshBranding} on every boot.
 */
export const branding = writable<BrandingState>(initialState());

/**
 * `"Page — NAME"` one-liner helper for per-page `<svelte:head>` titles:
 * `<title>{$titleFor('Playbooks', 'dot')}</title>`. Reactive — titles follow
 * the store when the fetched branding lands.
 */
export const titleFor = derived(
	branding,
	($branding) =>
		(page: string, style: TitleStyle = 'dash') =>
			formatPageTitle(page, $branding.productName, style)
);

function writeCache(state: BrandingState): void {
	try {
		window.localStorage.setItem(
			BRANDING_STORAGE_KEY,
			JSON.stringify({
				name: state.customName ? state.productName : '',
				palette: state.palette,
				logoVersion: state.logoVersion
			})
		);
	} catch {
		// Quota/private-mode failure — the pre-paint cache just won't help
		// next boot; the fetched state still applied to this session.
	}
}

function applyBrandingToDom(state: BrandingState, previousName: string): void {
	// Style tag: rewrite in place (the app.html pre-paint script may have
	// created it already). Its position in <head> doesn't matter — the
	// doubled selector specificity in buildBrandingCss wins over app.css
	// regardless of sheet order. Rewriting also CLEARS stale values when a
	// palette was removed server-side.
	let tag = document.getElementById(BRANDING_STYLE_TAG_ID);
	if (!tag) {
		tag = document.createElement('style');
		tag.id = BRANDING_STYLE_TAG_ID;
		document.head.appendChild(tag);
	}
	tag.textContent = buildBrandingCss(state.palette);

	// document.title: only when the current title is the BARE brand (the
	// app.html fallback used by pages without a <svelte:head> title, e.g.
	// login). Pages that set their own titles re-render reactively through
	// $titleFor — stomping them here would race the per-page value.
	if (document.title === previousName || document.title === DEFAULT_PRODUCT_NAME) {
		document.title = state.productName;
	}

	// Favicon: raster logo endpoint when a logo exists (the server only ever
	// stores sniffed PNG/JPEG/WEBP — SVG is impossible by construction);
	// otherwise restore the shipped default. Idempotent either way.
	const link = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
	if (link) {
		if (state.logoVersion !== null) {
			link.href = logoUrl(state.logoVersion);
			link.removeAttribute('type');
		} else {
			link.href = '/favicon.svg';
			link.type = 'image/svg+xml';
		}
	}
}

/**
 * Fetch the authoritative branding (unauth GET — works on the pre-auth
 * pages), validate it, and propagate: store → style tag → title → favicon →
 * localStorage cache. Called from the auth-gate layout's onMount on every
 * route; safe to call again after an admin edit. Failures are best-effort
 * (the cached/default brand stays).
 */
export async function refreshBranding(): Promise<void> {
	if (!browser) return;
	let resp: BrandingResponse;
	try {
		resp = await getBranding();
	} catch {
		// Offline / rate-limited — keep whatever painted; next boot retries.
		return;
	}
	const next = brandingStateFromResponse(resp);
	const previousName = get(branding).productName;
	branding.set(next);
	applyBrandingToDom(next, previousName);
	writeCache(next);
}
