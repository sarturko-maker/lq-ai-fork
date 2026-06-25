/**
 * In-app Word editor (ADR-F047, libreoffice-editor Slice 4) — the browser side
 * of the WOPI launch. Two network calls, then a form-POST into the iframe:
 *
 *   1. `POST /files/{id}/editor-session` mints a file-scoped WOPI access token
 *      (`createEditorSession`).
 *   2. `GET /hosting/discovery` (same-origin, served by the nginx Collabora
 *      proxy) advertises the `cool.html` loader URL (`fetchEditorUrlSrc`).
 *
 * The iframe `src` re-homes the discovery `urlsrc` PATH onto the page origin —
 * coolwsd advertises its own `server_name`/scheme (e.g. http://localhost:3000),
 * which need not match how the page is actually served — and carries only the
 * `WOPISrc` callback in the query. The `access_token` is POSTed into the iframe
 * (never in a URL/history), so Collabora never sees the user's session JWT.
 */
import { apiRequest } from './client';
import type { EditorSession } from '../types';

/** POST /api/v1/files/{id}/editor-session — mint a file-scoped WOPI session. */
export async function createEditorSession(fileId: string): Promise<EditorSession> {
	return apiRequest<EditorSession>(`/files/${encodeURIComponent(fileId)}/editor-session`, {
		method: 'POST'
	});
}

/**
 * Pull the editor loader URL (`urlsrc`) from Collabora's WOPI discovery. The
 * discovery doc advertises the SAME `cool.html` loader for every action, so we
 * prefer an `edit` action and fall back to any `urlsrc`. Discovery is XML and is
 * NOT under `/api/v1`, so this is a plain same-origin fetch (no auth header).
 */
export async function fetchEditorUrlSrc(): Promise<string> {
	const res = await fetch('/hosting/discovery', { headers: { Accept: 'application/xml' } });
	if (!res.ok) throw new Error(`Editor discovery failed (${res.status}).`);
	const urlsrc = extractEditUrlSrc(await res.text());
	if (!urlsrc) throw new Error('Editor discovery returned no loader URL.');
	return urlsrc;
}

/**
 * Mint the session and resolve the iframe `src` in parallel. Returns both the
 * computed `src` (origin-rehomed, WOPISrc-carrying) and the `session` whose
 * `access_token` the caller form-POSTs into the iframe.
 */
export async function openEditorSession(
	fileId: string,
	origin: string
): Promise<{ src: string; session: EditorSession }> {
	const [session, urlsrc] = await Promise.all([createEditorSession(fileId), fetchEditorUrlSrc()]);
	return { src: buildEditorSrc(urlsrc, session.wopi_src, origin), session };
}

// --- Pure helpers (unit-tested; no DOM/network) ----------------------------

/**
 * Extract the editor loader `urlsrc` from a WOPI discovery XML string. Prefers
 * an `edit` action (handles either attribute order) and falls back to the first
 * `urlsrc` present. Returns null if discovery carries none.
 */
export function extractEditUrlSrc(xml: string): string | null {
	const m =
		xml.match(/<action\b[^>]*\bname="edit"[^>]*\burlsrc="([^"]+)"/i) ??
		xml.match(/<action\b[^>]*\burlsrc="([^"]+)"[^>]*\bname="edit"/i) ??
		xml.match(/\burlsrc="([^"]+)"/i);
	return m?.[1] ?? null;
}

/**
 * Build the editor iframe `src`: take the discovery `urlsrc` PATH, re-home it on
 * the page `origin` (drop coolwsd's advertised scheme/host so the iframe loads
 * same-origin over whatever scheme the page actually uses), carry any preset
 * query params, then set `WOPISrc` to the host callback URL. The `access_token`
 * is NOT placed here — it is POSTed into the iframe by the caller.
 */
export function buildEditorSrc(urlsrc: string, wopiSrc: string, origin: string): string {
	const advertised = new URL(urlsrc, origin);
	const editor = new URL(advertised.pathname, origin);
	advertised.searchParams.forEach((v, k) => {
		if (v) editor.searchParams.set(k, v);
	});
	editor.searchParams.set('WOPISrc', wopiSrc);
	return editor.toString();
}

/** A filename the in-app editor can open: a Word `.docx` (WOPI/Collabora). */
export function isEditableDocx(filename: string): boolean {
	return /\.docx$/i.test(filename);
}

/** A redline work product — the agent's tracked-changes output, `… (redlined).docx`. */
export function isRedlineOutput(filename: string): boolean {
	return /\(redlined\)\.docx$/i.test(filename);
}

/**
 * Map a Collabora postMessage `MessageId` (+ its payload) to the editor's
 * save-state, or null if the message doesn't bear on it. Drives the chrome's
 * "Saving…/Saved/Unsaved" indicator. Collabora posts `App_LoadingStatus`
 * (Document_Loaded) once ready, `Doc_ModifiedStatus` ({Modified:bool}) on every
 * edit/save, and `Action_Save_Resp`/`Document_Saved` on a completed save.
 */
export type EditorSaveState = 'loading' | 'clean' | 'dirty' | 'saving' | 'saved';

export function saveStateFromMessage(
	messageId: string,
	values: { Status?: string; Modified?: boolean; success?: boolean } | undefined
): EditorSaveState | null {
	switch (messageId) {
		case 'App_LoadingStatus':
			return values?.Status === 'Document_Loaded' ? 'clean' : null;
		case 'Doc_ModifiedStatus':
			return values?.Modified ? 'dirty' : 'saved';
		case 'Action_Save':
			return 'saving';
		case 'Action_Save_Resp':
			// A failed save must NOT read as "Saved" — leave the edits flagged unsaved.
			return values?.success === false ? 'dirty' : 'saved';
		case 'Document_Saved':
			return 'saved';
		default:
			return null;
	}
}
