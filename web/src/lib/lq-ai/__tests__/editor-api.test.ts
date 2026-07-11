/**
 * Unit tests for the in-app Word editor's pure client helpers (ADR-F047, Slice 4).
 *
 * These cover the parts that decide what the iframe loads and what state the
 * chrome shows — the discovery parse, the origin-rehoming of the loader URL, the
 * docx/redline filename gates, and the postMessage → save-state mapping. The
 * network functions (createEditorSession / fetchEditorUrlSrc / openEditorSession)
 * are thin wrappers exercised by the Cypress spec + the live check.
 */
import { describe, expect, it } from 'vitest';

import {
	buildEditorSrc,
	extractEditUrlSrc,
	isEditableDocx,
	isRedlineOutput,
	saveStateFromMessage
} from '../api/editor';

const DISCOVERY = `<?xml version="1.0" encoding="UTF-8"?>
<wopi-discovery>
  <net-zone name="external-http">
    <app name="application/vnd.oasis.opendocument.text">
      <action default="true" ext="odt" name="view" urlsrc="https://collab.example/browser/abc123/cool.html?"/>
      <action default="true" ext="odt" name="edit" urlsrc="https://collab.example/browser/abc123/cool.html?"/>
    </app>
    <app name="application/vnd.openxmlformats-officedocument.wordprocessingml.document">
      <action default="true" ext="docx" name="edit" urlsrc="https://collab.example/browser/abc123/cool.html?"/>
    </app>
  </net-zone>
</wopi-discovery>`;

describe('extractEditUrlSrc', () => {
	it('extracts the edit-action loader URL from discovery XML', () => {
		expect(extractEditUrlSrc(DISCOVERY)).toBe('https://collab.example/browser/abc123/cool.html?');
	});

	it('handles urlsrc appearing before name on the action element', () => {
		const xml = '<action urlsrc="https://x/browser/h/cool.html?" name="edit" ext="docx"/>';
		expect(extractEditUrlSrc(xml)).toBe('https://x/browser/h/cool.html?');
	});

	it('falls back to any urlsrc when no edit action is present', () => {
		const xml = '<action name="view" urlsrc="https://x/browser/h/cool.html?"/>';
		expect(extractEditUrlSrc(xml)).toBe('https://x/browser/h/cool.html?');
	});

	it('returns null when discovery carries no urlsrc', () => {
		expect(extractEditUrlSrc('<wopi-discovery></wopi-discovery>')).toBeNull();
	});
});

describe('buildEditorSrc', () => {
	const ORIGIN = 'http://localhost:3000';
	const WOPI = 'http://api:8000/api/v1/wopi/files/2f1c';

	it('re-homes the loader path onto the page origin (drops coolwsd scheme/host)', () => {
		// discovery advertises https://collab.example, but the page is http://localhost:3000
		const src = buildEditorSrc('https://collab.example/browser/abc/cool.html?', WOPI, ORIGIN);
		const u = new URL(src);
		expect(u.origin).toBe(ORIGIN);
		expect(u.pathname).toBe('/browser/abc/cool.html');
	});

	it('sets WOPISrc to the host callback URL (encoded)', () => {
		const src = buildEditorSrc('http://localhost:3000/browser/abc/cool.html?', WOPI, ORIGIN);
		expect(new URL(src).searchParams.get('WOPISrc')).toBe(WOPI);
		// the raw string must be percent-encoded (no bare ':' '/' for the value)
		expect(src).toContain('WOPISrc=http%3A%2F%2Fapi%3A8000');
	});

	it('carries preset loader query params alongside WOPISrc', () => {
		const src = buildEditorSrc(
			'http://localhost:3000/browser/abc/cool.html?lang=en-GB',
			WOPI,
			ORIGIN
		);
		const u = new URL(src);
		expect(u.searchParams.get('lang')).toBe('en-GB');
		expect(u.searchParams.get('WOPISrc')).toBe(WOPI);
	});
});

describe('isEditableDocx', () => {
	it('accepts .docx (any case)', () => {
		expect(isEditableDocx('Cirrus MSA (redlined).docx')).toBe(true);
		expect(isEditableDocx('NOTES.DOCX')).toBe(true);
	});
	it('rejects non-docx', () => {
		expect(isEditableDocx('term-sheet.pdf')).toBe(false);
		expect(isEditableDocx('contract.doc')).toBe(false);
		expect(isEditableDocx('photo.docx.png')).toBe(false);
	});
});

describe('isRedlineOutput', () => {
	it('matches the agent redline filename', () => {
		expect(isRedlineOutput('Cirrus MSA (redlined).docx')).toBe(true);
		expect(isRedlineOutput('x (REDLINED).DOCX')).toBe(true);
	});
	it('matches a versioned redline branch (ADR-F081)', () => {
		expect(isRedlineOutput('Cirrus MSA (redlined v2).docx')).toBe(true);
		expect(isRedlineOutput('Cirrus MSA (redlined v10).docx')).toBe(true);
	});
	it('does not match uploads or other agent outputs', () => {
		expect(isRedlineOutput('Cirrus MSA.docx')).toBe(false);
		expect(isRedlineOutput('NDA (response).docx')).toBe(false);
		expect(isRedlineOutput('x (redlinedv2).docx')).toBe(false); // missing the space
		expect(isRedlineOutput('x (redlined v).docx')).toBe(false); // missing the number
	});
});

describe('saveStateFromMessage', () => {
	it('maps Document_Loaded → clean', () => {
		expect(saveStateFromMessage('App_LoadingStatus', { Status: 'Document_Loaded' })).toBe('clean');
	});
	it('ignores a non-loaded App_LoadingStatus', () => {
		expect(saveStateFromMessage('App_LoadingStatus', { Status: 'Frame_Ready' })).toBeNull();
	});
	it('maps Doc_ModifiedStatus by the Modified flag', () => {
		expect(saveStateFromMessage('Doc_ModifiedStatus', { Modified: true })).toBe('dirty');
		expect(saveStateFromMessage('Doc_ModifiedStatus', { Modified: false })).toBe('saved');
	});
	it('maps save lifecycle messages', () => {
		expect(saveStateFromMessage('Action_Save', undefined)).toBe('saving');
		expect(saveStateFromMessage('Action_Save_Resp', { success: true })).toBe('saved');
		expect(saveStateFromMessage('Document_Saved', undefined)).toBe('saved');
	});
	it('a FAILED save stays unsaved (not "Saved")', () => {
		expect(saveStateFromMessage('Action_Save_Resp', { success: false })).toBe('dirty');
	});
	it('returns null for unrelated messages', () => {
		expect(saveStateFromMessage('UI_Close', undefined)).toBeNull();
	});
});
