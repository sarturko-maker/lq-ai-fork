/**
 * Pure helpers for the /lq-ai/admin/intake-mailboxes page (INTAKE-5a, ADR-F086).
 *
 * Extracted out of `+page.svelte` so vitest can exercise them without a
 * SvelteKit runtime (Users/Areas-page precedent — no @testing-library/svelte).
 * Client-side validation here is a pre-flight only; the server's Pydantic
 * schema (`api/app/schemas/intake_mailboxes.py`) is authoritative.
 */

import type { AdminUserRow } from '$lib/lq-ai/types';
import type { IntakeMailbox, IntakeMailboxBudgetProfile } from '$lib/lq-ai/api/intakeMailboxes';
import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';

export interface StatusView {
	label: string;
	tone: 'secondary' | 'outline';
}

/** Active/Inactive badge — `active` is the only status field this row has. */
export function mailboxStatusView(mailbox: Pick<IntakeMailbox, 'active'>): StatusView {
	return mailbox.active
		? { label: 'Active', tone: 'secondary' }
		: { label: 'Inactive', tone: 'outline' };
}

/** Human label for the run-default budget profile — `null`/unset reads as
 *  "Inherit" (SETUP-5a precedent: the area's own default, or the deployment
 *  default beyond that). */
export function budgetProfileLabel(profile: IntakeMailboxBudgetProfile | null): string {
	switch (profile) {
		case 'economy':
			return 'Economy';
		case 'balanced':
			return 'Balanced';
		case 'generous':
			return 'Generous';
		default:
			return 'Inherit';
	}
}

/** `id -> name` lookup built once per practice-area list load, so table rows
 *  and pickers don't each re-scan the array. */
export function buildAreaNameMap(areas: PracticeArea[]): Map<string, string> {
	return new Map(areas.map((a) => [a.id, a.name]));
}

/** `id -> email` lookup built once per user list load. */
export function buildUserEmailMap(users: AdminUserRow[]): Map<string, string> {
	return new Map(users.map((u) => [u.id, u.email]));
}

/** A row's practice-area name, or a fallback that still shows the raw id
 *  (never blank — an area can be deleted out from under a mailbox binding). */
export function areaNameFor(areaMap: Map<string, string>, practiceAreaId: string): string {
	return areaMap.get(practiceAreaId) ?? `Unknown area (${practiceAreaId})`;
}

/** A row's owner email, or a fallback that still shows the raw id (a user
 *  can be soft-deleted out from under an existing binding). */
export function ownerEmailFor(userMap: Map<string, string>, ownerUserId: string): string {
	return userMap.get(ownerUserId) ?? `Unknown user (${ownerUserId})`;
}

/** Non-empty, trimmed — the inbox id is opaque provider-side (AgentMail
 *  inbox id today), so beyond "required" the server's own max-length check
 *  is authoritative. */
export function validateInboxId(inboxId: string): string | null {
	if (!inboxId.trim()) return 'Inbox id is required.';
	return null;
}

/** The mailbox address the provider delivers to — required, and worth a
 *  light shape check since a typo here silently misroutes real mail. */
export function validateAddress(address: string): string | null {
	const trimmed = address.trim();
	if (!trimmed) return 'Address is required.';
	if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed)) {
		return 'Enter a valid email address.';
	}
	return null;
}

export function validatePracticeArea(practiceAreaId: string): string | null {
	if (!practiceAreaId) return 'Choose a practice area.';
	return null;
}

export function validateOwner(ownerUserId: string): string | null {
	if (!ownerUserId) return 'Choose an owner.';
	return null;
}

/** `max_steps` is `1..600` server-side (`ge=1, le=600`); the field is
 *  optional — an empty string means "leave unset". */
export function validateMaxSteps(raw: string): string | null {
	const trimmed = raw.trim();
	if (!trimmed) return null;
	const n = Number(trimmed);
	if (!Number.isInteger(n) || n < 1 || n > 600) {
		return 'Max steps must be a whole number between 1 and 600.';
	}
	return null;
}

/** `''` (the select's "unset" option) -> `null`; a chosen value passes through. */
export function parseBudgetProfile(raw: string): IntakeMailboxBudgetProfile | null {
	return raw === '' ? null : (raw as IntakeMailboxBudgetProfile);
}

/** `''` -> `null` (leave unset / clear); a digit string -> its number. */
export function parseMaxSteps(raw: string): number | null {
	const trimmed = raw.trim();
	return trimmed === '' ? null : Number(trimmed);
}

/** Locale datetime for admin timestamps ("Bound {date}") — the shared admin
 *  helper, re-exported so this module stays the page's single import surface. */
export { formatDateTime, describeMutationError } from '$lib/lq-ai/admin/page-helpers';
