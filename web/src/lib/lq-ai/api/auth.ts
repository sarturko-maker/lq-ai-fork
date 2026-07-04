/**
 * /api/v1/auth — login, refresh, logout, change-password, /users/me.
 *
 * The login + refresh calls bypass the auth header (no token yet); the rest
 * carry the bearer token via `apiRequest`.
 */
import { apiRequest } from './client';
import { clearSession, setSession, setUser } from '../auth/store';
import type {
	AcceptInviteRequest,
	AcceptInviteResponse,
	ChangePasswordRequest,
	LoginRequest,
	LoginResponse,
	MfaSetupResponse,
	PasswordResetConfirmRequest,
	TokenResponse,
	User
} from '../types';

/** POST /api/v1/auth/login. On success, populates the auth store. */
export async function login(req: LoginRequest): Promise<LoginResponse> {
	const res = await apiRequest<LoginResponse>('/auth/login', {
		method: 'POST',
		body: req,
		skipAuth: true,
		skipRefresh: true
	});
	setSession({
		access_token: res.access_token,
		refresh_token: res.refresh_token ?? null,
		expires_in: res.expires_in,
		user: res.user
	});
	return res;
}

/** POST /api/v1/auth/refresh. Caller normally wants the wrapper in `client.ts`. */
export async function refresh(refresh_token: string): Promise<TokenResponse> {
	const res = await apiRequest<TokenResponse>('/auth/refresh', {
		method: 'POST',
		body: { refresh_token },
		skipAuth: true,
		skipRefresh: true
	});
	setSession({
		access_token: res.access_token,
		refresh_token: res.refresh_token,
		expires_in: res.expires_in
	});
	return res;
}

/** POST /api/v1/auth/logout. Best-effort; clears local session regardless. */
export async function logout(): Promise<void> {
	try {
		await apiRequest<void>('/auth/logout', { method: 'POST' });
	} catch {
		// Even if the server errors, drop the local session.
	}
	clearSession();
}

/** POST /api/v1/auth/change-password. Server revokes all sessions on success. */
export async function changePassword(req: ChangePasswordRequest): Promise<void> {
	await apiRequest<void>('/auth/change-password', {
		method: 'POST',
		body: req
	});
	// Server revoked our sessions; clear locally too. Caller redirects to login.
	clearSession();
}

/** GET /api/v1/users/me. Updates the cached user in the auth store. */
export async function getCurrentUser(): Promise<User> {
	const user = await apiRequest<User>('/users/me');
	setUser(user);
	return user;
}

/** POST /api/v1/auth/mfa/setup — issues a fresh TOTP secret + recovery codes. */
export async function mfaSetup(): Promise<MfaSetupResponse> {
	return apiRequest<MfaSetupResponse>('/auth/mfa/setup', { method: 'POST' });
}

/** POST /api/v1/auth/mfa/enable — verify code, flip mfa_enabled to true. */
export async function mfaEnable(code: string): Promise<void> {
	await apiRequest<void>('/auth/mfa/enable', { method: 'POST', body: { code } });
}

/** POST /api/v1/auth/mfa/disable — password + code; clears MFA state. */
export async function mfaDisable(password: string, code: string): Promise<void> {
	await apiRequest<void>('/auth/mfa/disable', { method: 'POST', body: { password, code } });
}

// ----- User lifecycle (SETUP-3b, ADR-F061) -----
// All three are UNAUTHENTICATED (token pages / login screen): skipAuth so no
// stale bearer rides along, skipRefresh so a 401 can't trigger a refresh loop.
// No response ever carries session tokens — the house pattern is
// redirect-to-login after success (D2/D3).

/** POST /api/v1/auth/accept-invite — redeem an invite token, create the account. */
export async function acceptInvite(req: AcceptInviteRequest): Promise<AcceptInviteResponse> {
	return apiRequest<AcceptInviteResponse>('/auth/accept-invite', {
		method: 'POST',
		body: req,
		skipAuth: true,
		skipRefresh: true
	});
}

/**
 * POST /api/v1/auth/password-reset-request — always 202 regardless of account
 * existence (anti-enumeration); the UI copy must never confirm existence either.
 */
export async function passwordResetRequest(email: string): Promise<void> {
	await apiRequest<void>('/auth/password-reset-request', {
		method: 'POST',
		body: { email },
		skipAuth: true,
		skipRefresh: true
	});
}

/** POST /api/v1/auth/password-reset — redeem a reset token, set the new password (204). */
export async function passwordResetConfirm(req: PasswordResetConfirmRequest): Promise<void> {
	await apiRequest<void>('/auth/password-reset', {
		method: 'POST',
		body: req,
		skipAuth: true,
		skipRefresh: true
	});
}
