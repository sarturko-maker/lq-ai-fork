/**
 * AE4 (ADR-F011) — Shiki highlighter for fenced code blocks in model output.
 *
 * `shiki` is the one new runtime dependency ADR-F011 sanctioned. It is a
 * tokenizer: it turns a source STRING into styled `<span>`s. It does not eval,
 * it makes no network call, and it never interprets its input as HTML — the
 * caller feeds it `.textContent` already pulled out of DOMPurify-sanitized
 * output, and DOMPurify re-sanitizes Shiki's output before it re-enters the DOM
 * (see `enhance.ts`). So the highlight runs entirely on already-sanitized text.
 *
 * We use the *fine-grained* setup (the bundled `createHighlighter` with the
 * pure-JS regex engine, no WASM, plus an explicit short language list) so the
 * bundle only carries grammars we actually expect in a legal-tech chat. A
 * language we don't load degrades to `text` (plain, no grammar) rather than
 * throwing — `codeToHtml` rejects an unknown `lang`.
 *
 * Dual theme: GitHub light/dark (clean, professional, AA — matches the design
 * rule). Shiki emits both palettes inline (`color` for light, a `--shiki-dark`
 * CSS var for dark); `enhance.ts`'s scoped CSS swaps to the dark var under
 * `html.dark`. This is Shiki's recommended class-based dark mode.
 */
import { createHighlighter, type Highlighter } from 'shiki';
import { createJavaScriptRegexEngine } from 'shiki/engine/javascript';

export const LIGHT_THEME = 'github-light-default';
export const DARK_THEME = 'github-dark-default';

/**
 * Grammars loaded into the highlighter. Anything outside this set normalizes to
 * `text`. Keep the list modest — every entry is eagerly loaded at init, and
 * code blocks are rare on this surface. Add languages here as real need shows.
 */
export const SUPPORTED_LANGS = [
	'bash',
	'css',
	'diff',
	'go',
	'html',
	'java',
	'javascript',
	'json',
	'jsx',
	'markdown',
	'python',
	'rust',
	'sql',
	'svelte',
	'tsx',
	'typescript',
	'xml',
	'yaml'
] as const;

export type SupportedLang = (typeof SUPPORTED_LANGS)[number];

const SUPPORTED = new Set<string>(SUPPORTED_LANGS);

/**
 * Common fence aliases the model emits → a grammar we load. Anything not here
 * and not in `SUPPORTED_LANGS` falls back to `text`.
 */
const ALIASES: Record<string, SupportedLang> = {
	sh: 'bash',
	shell: 'bash',
	zsh: 'bash',
	console: 'bash',
	js: 'javascript',
	mjs: 'javascript',
	cjs: 'javascript',
	ts: 'typescript',
	py: 'python',
	py3: 'python',
	python3: 'python',
	yml: 'yaml',
	golang: 'go',
	rs: 'rust',
	md: 'markdown',
	htm: 'html',
	postgres: 'sql',
	postgresql: 'sql',
	mysql: 'sql',
	plpgsql: 'sql'
};

/**
 * Map a raw fence language token (from `class="language-…"`) to a grammar we
 * load, or `'text'` (plain, no grammar) when we don't recognise it. Case- and
 * whitespace-insensitive; never throws.
 */
export function normalizeLang(raw: string | null | undefined): SupportedLang | 'text' {
	if (!raw) return 'text';
	const key = raw.trim().toLowerCase();
	if (!key) return 'text';
	if (SUPPORTED.has(key)) return key as SupportedLang;
	if (key in ALIASES) return ALIASES[key];
	return 'text';
}

let instance: Promise<Highlighter> | null = null;

/**
 * Lazily build (once) and return the shared highlighter. The first code block
 * to render triggers init; later blocks reuse the instance.
 */
export function getHighlighter(): Promise<Highlighter> {
	if (!instance) {
		instance = createHighlighter({
			themes: [LIGHT_THEME, DARK_THEME],
			langs: [...SUPPORTED_LANGS],
			engine: createJavaScriptRegexEngine()
		});
	}
	return instance;
}
