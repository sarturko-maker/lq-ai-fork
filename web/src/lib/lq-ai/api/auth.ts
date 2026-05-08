/**
 * /api/v1/auth — login, refresh, logout, change-password, /users/me.
 *
 * The login + refresh calls bypass the auth header (no token yet); the rest
 * carry the bearer token via `apiRequest`.
 */
import { apiRequest } from './client';
import { clearSession, setSession, setUser } from '../auth/store';
import type {
	ChangePasswordRequest,
	LoginRequest,
	LoginResponse,
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
