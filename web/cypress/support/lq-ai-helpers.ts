/**
 * Shared E2E helper functions for LQ.AI Cypress specs (DE-254).
 *
 * These helpers were duplicated inline across wave-d1-power-features.cy.ts,
 * wave-d2-skill-creator.cy.ts, and wave-m1-final-surfaces.cy.ts. They are
 * plain function exports (not `Cypress.Commands.add`) so they are
 * tree-shaken per spec and can be imported with a standard ES import.
 *
 * Each spec passes `login`, `createSampleMatter`, and `getBearerToken`
 * from this module; any spec-local variant (e.g. different default prefix)
 * just calls the helper with the right args.
 */

/// <reference types="cypress" />

// ---------------------------------------------------------------------------
// login — visit /lq-ai/login, fill credentials, wait for redirect
// ---------------------------------------------------------------------------

/**
 * Navigate to the LQ.AI login page, type credentials, submit, and wait
 * until the URL no longer includes '/login'. A 15s timeout absorbs the
 * post-LLM-test API backlog that can delay the redirect.
 */
export function login(email: string, password: string): void {
	cy.visit('/lq-ai/login');
	cy.get('input[type="email"]').type(email);
	cy.get('input[type="password"]').type(password);
	cy.get('button[type="submit"]').click();
	cy.url({ timeout: 15000 }).should('not.include', '/login');
}

// ---------------------------------------------------------------------------
// createSampleMatter — create a new matter, start a chat, wait for composer
// ---------------------------------------------------------------------------

/**
 * Navigate to /lq-ai/matters, create a fresh non-privileged matter,
 * click "+ New Chat" to seed an active chat, and wait for the composer
 * to render.
 *
 * The composer is gated on `{#if activeChat}` in ChatPanel.svelte; without
 * this step every test that needs the composer times out.
 *
 * Sets the Cypress alias `@matterName` to the generated matter name so
 * calling tests can assert on it later.
 */
export function createSampleMatter(prefix = 'Cypress LQ.AI'): void {
	const matterName = `${prefix} ${Date.now()}`;
	cy.visit('/lq-ai/matters');

	// Intercept the create-matter POST before clicking so we can wait for
	// the 201 before asserting on the URL. NewMatterModal calls onCreated()
	// (parent state refresh) then goto(); under SvelteKit's microtask queue
	// these can race, delaying the URL change past Cypress' default 4s retry.
	cy.intercept('POST', '/api/v1/projects').as('createMatter');

	cy.contains('button', '+ New matter').first().click();
	cy.get('[role="dialog"]').should('exist');
	cy.get('[role="dialog"]').find('input[type="text"]').first().clear().type(matterName);
	cy.contains('button', 'Create matter').click();

	cy.wait('@createMatter').its('response.statusCode').should('eq', 201);
	cy.url({ timeout: 15000 }).should('match', /\/lq-ai\/matters\/[a-f0-9-]+$/);
	cy.get('[data-testid="lq-ai-chat-shell"]', { timeout: 10000 }).should('exist');

	// + New Chat → auto-selects → composer mounts
	cy.get('[data-testid="lq-ai-new-chat-btn"]').click();
	cy.get('[data-testid="lq-ai-composer-input"]', { timeout: 10000 }).should('be.visible');

	cy.wrap(matterName).as('matterName');
}

// ---------------------------------------------------------------------------
// getBearerToken — read the access token from localStorage
// ---------------------------------------------------------------------------

/**
 * Extract the LQ.AI bearer token from localStorage and pass it to a
 * callback. The auth store writes the session under `lq_ai_auth` as a
 * JSON object with an `access_token` field (api/client.ts + auth/store.ts).
 *
 * Usage:
 *
 *   getBearerToken((token) => {
 *     cy.request({ headers: { Authorization: `Bearer ${token}` }, ... });
 *   });
 *
 * The assertion `expect(token).to.be.a('string')` fails the test early if
 * the auth store is not populated (e.g. login was skipped in beforeEach).
 */
export function getBearerToken(cb: (token: string) => void): void {
	cy.window().then((win) => {
		let token: string | null = null;
		try {
			const raw = win.localStorage.getItem('lq_ai_auth');
			if (raw) {
				const parsed = JSON.parse(raw) as { access_token?: string };
				token = parsed.access_token ?? null;
			}
		} catch {
			token = null;
		}
		expect(token, 'auth token must exist after login').to.be.a('string');
		cb(token as string);
	});
}
