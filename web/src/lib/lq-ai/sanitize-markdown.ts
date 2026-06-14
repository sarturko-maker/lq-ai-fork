/**
 * Canonical renderer for UNTRUSTED model output (assistant answers + `<think>`
 * reasoning). Markdown → HTML via `marked`, sanitised with DOMPurify under the
 * media-forbid policy the rest of the model-output surface enforces.
 *
 * Model output is untrusted input (CLAUDE.md). DOMPurify's defaults strip
 * active XSS (script / event handlers / `javascript:`) but ALLOW media tags
 * that auto-fetch remote resources on render (`<img src>`, `<svg><image href>`,
 * `srcset`, `<video>`…) — a data-exfil/beacon channel for a poisoned answer or
 * a poisoned KB chunk restated inside reasoning. F0-S5 review forbade them on
 * the agent surface (ConversationPanel) and skill source view; this helper is
 * the shared home so no model-output render path can drift from that control.
 * R-CONV-2 / R14a should converge their local copies onto this.
 */
import DOMPurify from 'dompurify';
import { marked } from 'marked';

export const SANITIZE_OPTS = {
	FORBID_TAGS: ['img', 'picture', 'audio', 'video', 'source', 'track', 'svg', 'image', 'use'],
	FORBID_ATTR: ['srcset', 'ping']
};

/**
 * Render untrusted model markdown to sanitised, media-free HTML.
 *
 * `breaks` maps single newlines to `<br>` (GitHub-flavoured) — off by default
 * to match the agent/chat answer surfaces; the skill source view opts in so
 * authored SKILL.md bodies keep their hard line breaks (R-CONV-2 convergence).
 */
export function renderModelMarkdown(
	raw: string | null | undefined,
	opts: { breaks?: boolean } = {}
): string {
	if (!raw) return '';
	return DOMPurify.sanitize(
		marked.parse(raw, { async: false, breaks: opts.breaks ?? false }) as string,
		SANITIZE_OPTS
	);
}
