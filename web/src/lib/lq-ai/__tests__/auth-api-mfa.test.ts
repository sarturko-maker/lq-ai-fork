/**
 * Unit tests for the MFA helpers added to the auth API client.
 *
 * Mocks `fetch` to keep tests hermetic. Follows the saved-prompts-api.test.ts
 * pattern: set a session token, replace global.fetch, assert on URL / method /
 * body / response shape.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { mfaDisable, mfaEnable, mfaSetup } from '../api/auth';
import type { MfaSetupResponse } from '../types';
import { clearSession, setSession } from '../auth/store';
import { LQAIApiError } from '../api/client';

const realFetch = global.fetch;

function jsonResponse(status: number, body: unknown): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json' }
	});
}

function emptyResponse(status: number): Response {
	return new Response(null, { status });
}

const SETUP_RESPONSE: MfaSetupResponse = {
	secret: 'JBSWY3DPEHPK3PXP',
	provisioning_uri: 'otpauth://totp/LQ.AI%3Auser%40example.com?secret=JBSWY3DPEHPK3PXP&issuer=LQ.AI',
	recovery_codes: [
		'aaaa-bbbb', 'cccc-dddd', 'eeee-ffff', 'gggg-hhhh', 'iiii-jjjj',
		'kkkk-llll', 'mmmm-nnnn', 'oooo-pppp', 'qqqq-rrrr', 'ssss-tttt'
	]
};

describe('auth API — MFA helpers', () => {
	beforeEach(() => {
		clearSession();
		setSession({ access_token: 'tok', expires_in: 900 });
		vi.restoreAllMocks();
	});

	afterEach(() => {
		global.fetch = realFetch;
	});

	it('mfaSetup returns the setup response shape', async () => {
		global.fetch = vi.fn(async () => jsonResponse(200, SETUP_RESPONSE)) as unknown as typeof fetch;
		const out = await mfaSetup();
		expect(out.secret).toBe('JBSWY3DPEHPK3PXP');
		expect(out.provisioning_uri).toContain('otpauth://');
		expect(out.recovery_codes).toHaveLength(10);
	});

	it('mfaEnable POSTs the 6-digit code in the body', async () => {
		const fetchSpy = vi.fn(async () => emptyResponse(204));
		global.fetch = fetchSpy as unknown as typeof fetch;
		await mfaEnable('123456');
		const init = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[1];
		expect(init.method).toBe('POST');
		const parsed = JSON.parse(init.body as string);
		expect(parsed.code).toBe('123456');
	});

	it('mfaDisable POSTs both password and code', async () => {
		const fetchSpy = vi.fn(async () => emptyResponse(204));
		global.fetch = fetchSpy as unknown as typeof fetch;
		await mfaDisable('s3cr3t', '654321');
		const init = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[1];
		expect(init.method).toBe('POST');
		const parsed = JSON.parse(init.body as string);
		expect(parsed.password).toBe('s3cr3t');
		expect(parsed.code).toBe('654321');
	});

	it('mfaSetup surfaces 409 as LQAIApiError', async () => {
		global.fetch = vi.fn(async () =>
			jsonResponse(409, { detail: { code: 'mfa_already_enabled', message: 'MFA already enabled' } })
		) as unknown as typeof fetch;
		await expect(mfaSetup()).rejects.toBeInstanceOf(LQAIApiError);
	});
});
