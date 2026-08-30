/**
 * Admin intake-mailboxes API client — INTAKE-5a (ADR-F086).
 *
 * Surface (mirrors `api/app/api/admin_intake_mailboxes.py` exactly):
 *
 *   - POST   /api/v1/admin/intake-mailboxes           — bind a mailbox
 *   - GET    /api/v1/admin/intake-mailboxes            — list live (non-soft-deleted) mailboxes
 *   - PATCH  /api/v1/admin/intake-mailboxes/{id}       — partial update
 *   - DELETE /api/v1/admin/intake-mailboxes/{id}       — soft-delete
 *
 * All four endpoints are admin-gated server-side; a non-admin caller gets a
 * 403 `forbidden` which `apiRequest` surfaces as a typed `LQAIApiError` the
 * admin page catches and renders inline (intake-bridges precedent).
 *
 * There are no secrets anywhere in this API — a mailbox binding is just
 * `(provider, inbox_id) → address, practice_area, owner_user` plus the run
 * defaults. Never add a token/key/credential field here.
 */
import { apiRequest } from './client';

/** Matches `app.schemas.agent_runs.BudgetProfile` — the same three values
 *  used inline by `practiceAreas.ts`'s `default_budget_profile`. */
export type IntakeMailboxBudgetProfile = 'economy' | 'balanced' | 'generous';

/** Wire shape returned by all four admin endpoints (`IntakeMailboxResponse`). */
export interface IntakeMailbox {
	id: string;
	provider: string;
	inbox_id: string;
	address: string;
	practice_area_id: string;
	owner_user_id: string;
	default_budget_profile: IntakeMailboxBudgetProfile | null;
	max_steps: number | null;
	active: boolean;
	created_at: string;
	updated_at: string;
}

/** Body for `POST /admin/intake-mailboxes` (`IntakeMailboxCreate`).
 *  `provider`/`inbox_id`/`address` are create-only — rebind by deleting and
 *  recreating (the server never lets a PATCH touch them). */
export interface IntakeMailboxCreateBody {
	/** Defaults to 'agentmail' server-side when omitted. */
	provider?: string;
	inbox_id: string;
	address: string;
	practice_area_id: string;
	owner_user_id: string;
	default_budget_profile?: IntakeMailboxBudgetProfile | null;
	max_steps?: number | null;
}

/** Body for `PATCH /admin/intake-mailboxes/{id}` (`IntakeMailboxUpdate`).
 *  Every field is optional; only fields actually set are applied
 *  (`exclude_unset` server-side) — omit a field to leave it unchanged. */
export interface IntakeMailboxUpdateBody {
	active?: boolean;
	owner_user_id?: string;
	default_budget_profile?: IntakeMailboxBudgetProfile | null;
	max_steps?: number | null;
}

/** GET /api/v1/admin/intake-mailboxes — live mailboxes, newest first. */
export async function listIntakeMailboxes(): Promise<IntakeMailbox[]> {
	return apiRequest<IntakeMailbox[]>('/admin/intake-mailboxes', { method: 'GET' });
}

/** POST /api/v1/admin/intake-mailboxes — bind a mailbox to a practice area +
 *  owner user. 404 on an unknown `practice_area_id`/`owner_user_id`; 409 on a
 *  collision with an already-live `(provider, inbox_id)`. */
export async function createIntakeMailbox(
	body: IntakeMailboxCreateBody
): Promise<IntakeMailbox> {
	return apiRequest<IntakeMailbox>('/admin/intake-mailboxes', { method: 'POST', body });
}

/** PATCH /api/v1/admin/intake-mailboxes/{id} — 404 on an unknown mailbox id or
 *  an unknown `owner_user_id`. */
export async function updateIntakeMailbox(
	mailboxId: string,
	body: IntakeMailboxUpdateBody
): Promise<IntakeMailbox> {
	return apiRequest<IntakeMailbox>(
		`/admin/intake-mailboxes/${encodeURIComponent(mailboxId)}`,
		{ method: 'PATCH', body }
	);
}

/** DELETE /api/v1/admin/intake-mailboxes/{id} — soft-delete; idempotent (an
 *  already-deleted/missing id 404s rather than 204-no-op). */
export async function deleteIntakeMailbox(mailboxId: string): Promise<void> {
	await apiRequest<void>(`/admin/intake-mailboxes/${encodeURIComponent(mailboxId)}`, {
		method: 'DELETE'
	});
}
