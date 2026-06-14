/**
 * `enhanceCodeBlocks` — Svelte action that upgrades the fenced code blocks in
 * rendered model output into the AI Elements code-block identity: a bordered
 * card with a language header, a copy button, and Shiki syntax highlighting
 * (AE4, ADR-F011).
 *
 * Mirrors `decorateCitationsInline` — it post-processes the *already-sanitized*
 * `{@html}` output rather than re-rendering markdown through a component tree
 * (we keep the single `renderModelMarkdown` → `{@html}` sink; we do NOT adopt a
 * streamdown-style Response). Security posture:
 *
 *   1. `renderModelMarkdown` (marked + DOMPurify, media-forbidden) has already
 *      run, so each `<pre><code>` holds HTML-escaped, sanitized text.
 *   2. We read `code.textContent` — a plain string (entities decoded back to
 *      characters); it is never interpreted as HTML.
 *   3. Shiki tokenizes that string into styled spans (no eval, no network).
 *   4. We DOMPurify-sanitize Shiki's output again before it re-enters the DOM.
 *
 * So highlighting runs entirely on already-sanitized text and the highlighted
 * HTML is re-sanitized — no new injection sink is introduced.
 *
 * Like the citation decorator the action is a no-op while `enabled === false`
 * (the message is still streaming): partial fences shouldn't be highlighted and
 * re-highlighted on every token. Highlighting is async (the Shiki grammar/theme
 * load is lazy); a generation counter discards results from a superseded pass,
 * and `pre.isConnected` guards against a block detached by an `{@html}`
 * re-render mid-flight.
 */
import DOMPurify from 'dompurify';
import { SANITIZE_OPTS } from '../sanitize-markdown';
import { getHighlighter, normalizeLang, LIGHT_THEME, DARK_THEME } from './shiki';

export interface EnhanceCodeParams {
	/**
	 * Streaming hint: when `false`, the action is a no-op (raw `<pre>` stays).
	 * Callers pass `false` while the assistant message streams and switch to
	 * `true` once it completes.
	 */
	enabled?: boolean;
}

/** Marker set on a `<pre>` once we've started/finished enhancing it. */
const STATE_ATTR = 'data-lq-code';

/** Pull the fenced language token out of `class="language-…"` (marked output). */
function langFromClass(className: string): string | null {
	for (const cls of className.split(/\s+/)) {
		if (cls.startsWith('language-')) return cls.slice('language-'.length);
		if (cls.startsWith('lang-')) return cls.slice('lang-'.length);
	}
	return null;
}

/** Build the AE code-block card around already-sanitized Shiki HTML. */
function buildCard(safeShikiHtml: string, label: string, source: string): HTMLElement {
	const figure = document.createElement('figure');
	figure.className =
		'lq-code not-prose my-4 overflow-hidden rounded-lg border border-border bg-card';
	figure.setAttribute('data-testid', 'lq-ai-code-block');
	figure.dataset.lang = label;

	const caption = document.createElement('figcaption');
	caption.className =
		'flex items-center justify-between gap-2 border-b border-border bg-muted/40 px-3 py-1.5';

	const langSpan = document.createElement('span');
	langSpan.className = 'font-mono text-xs font-medium text-muted-foreground select-none';
	langSpan.textContent = label;
	caption.appendChild(langSpan);

	caption.appendChild(buildCopyButton(source));

	const body = document.createElement('div');
	body.className = 'lq-code-body';
	// Already DOMPurify-sanitized by the caller (Shiki span markup only).
	body.innerHTML = safeShikiHtml;

	figure.appendChild(caption);
	figure.appendChild(body);
	return figure;
}

/** Copy-to-clipboard button with a transient confirmation + accessible label. */
function buildCopyButton(source: string): HTMLButtonElement {
	const btn = document.createElement('button');
	btn.type = 'button';
	btn.className =
		'inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium text-muted-foreground ' +
		'hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring ' +
		'transition-colors';
	btn.setAttribute('data-testid', 'lq-ai-code-copy');
	btn.setAttribute('aria-label', 'Copy code to clipboard');
	const IDLE = 'Copy';
	btn.textContent = IDLE;

	let revert: ReturnType<typeof setTimeout> | undefined;
	btn.addEventListener('click', async () => {
		try {
			await navigator.clipboard.writeText(source);
			btn.textContent = 'Copied';
			btn.setAttribute('aria-label', 'Code copied to clipboard');
		} catch {
			btn.textContent = 'Copy failed';
			btn.setAttribute('aria-label', 'Copy failed');
		}
		if (revert) clearTimeout(revert);
		revert = setTimeout(() => {
			btn.textContent = IDLE;
			btn.setAttribute('aria-label', 'Copy code to clipboard');
		}, 1500);
	});
	return btn;
}

export function enhanceCodeBlocks(
	node: HTMLElement,
	params: EnhanceCodeParams
): {
	update(next: EnhanceCodeParams): void;
	destroy(): void;
} {
	let current = params;
	// Bumped on every apply(); async highlight closures capture their value and
	// bail if a newer pass has started (or the node unmounted).
	let generation = 0;

	async function highlightAndSwap(pre: HTMLElement, gen: number): Promise<void> {
		const code = pre.querySelector('code');
		const source = code?.textContent ?? '';
		const rawLang = code ? langFromClass(code.className) : null;
		const lang = normalizeLang(rawLang);

		let html: string;
		try {
			const highlighter = await getHighlighter();
			if (gen !== generation || !pre.isConnected) return;
			html = highlighter.codeToHtml(source, {
				lang,
				themes: { light: LIGHT_THEME, dark: DARK_THEME }
			});
		} catch {
			// Highlight failed (e.g. grammar load error) — leave the raw <pre>
			// in place rather than dropping the code. Clear the marker so a
			// later pass can retry.
			pre.removeAttribute(STATE_ATTR);
			return;
		}

		// Shiki emits only <pre>/<code>/<span style> — no media — but re-sanitize
		// under the SAME media-forbid policy as the rest of the model-output
		// surface (defense in depth; one policy, no drift).
		const safe = DOMPurify.sanitize(html, SANITIZE_OPTS);
		if (gen !== generation || !pre.isConnected) return;

		pre.replaceWith(buildCard(safe, lang, source));
	}

	function apply(): void {
		const gen = ++generation;
		if (current.enabled === false) return;

		const codes = node.querySelectorAll('pre > code');
		codes.forEach((code) => {
			const pre = code.parentElement;
			if (!pre || pre.hasAttribute(STATE_ATTR)) return;
			pre.setAttribute(STATE_ATTR, '');
			void highlightAndSwap(pre, gen);
		});
	}

	apply();

	return {
		update(next: EnhanceCodeParams) {
			current = next;
			apply();
		},
		destroy() {
			// Bump the generation so any in-flight highlight is discarded; the
			// node is being torn down by Svelte, so there's nothing to restore.
			generation++;
		}
	};
}
