/**
 * Wave D.2 — Skill Creator (Wave 8 E2E suite).
 *
 * Covers the Skill Creator surface that shipped through Wave D.2:
 *
 *   1. Capture happy path (Task 8.2)    — AI reply → modal → save → skill in list
 *   2. Wizard from scratch (Task 8.2)   — blank → fill 3 sections → set slash_alias → save
 *   3. Fork flow (Task 8.3)             — detail page → fork → wizard pre-populated → save
 *   4. Slash invocation (Task 8.4)      — type "/" in composer → popover → pick → pill → send
 *   5. Try-it sandbox (Task 8.4)        — detail Try-it tab → ensure sandbox → send → conversation persists
 *   6. Versions + slash_alias collision (Task 8.3) — edit twice → tab shows 3 rows; collision → inline error
 *
 * Run requires a live stack:
 *   docker compose up -d
 *   docker compose exec api python -m app.cli reset-admin-password \
 *     --email admin@lq.ai --password 'LQ-AI-smoke-test-Pw1!' --no-force-change
 *   cd web && npx cypress run --spec 'cypress/e2e/wave-d2-skill-creator.cy.ts'
 */

/// <reference types="cypress" />

const ADMIN_EMAIL = () => Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai';
const ADMIN_PASSWORD = () => Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-smoke-test-Pw1!';

/**
 * Inline login — mirrors wave-d1-power-features.cy.ts beforeEach pattern.
 * Wave D.1 did not extract a custom command for this; we follow the same shape
 * so anyone reading the suite sees a single consistent login flow.
 */
function login(email: string, password: string) {
	cy.visit('/lq-ai/login');
	cy.get('input[type="email"]').type(email);
	cy.get('input[type="password"]').type(password);
	cy.get('button[type="submit"]').click();
	// Login can take longer after real LLM round-trips (~30-60s) —
	// the api briefly backlogs incoming requests. Default cy.url retry is
	// 4s; 15s absorbs the post-LLM-test recovery window.
	cy.url({ timeout: 15000 }).should('not.include', '/login');
}

/**
 * Create a fresh non-privileged matter, click + New Chat to seed an active
 * chat, and wait for the composer to render. The composer is gated on
 * `{#if activeChat}` in ChatPanel.svelte, so without this step every test
 * times out looking for `lq-ai-composer-input`.
 *
 * Returns the matter name via Cypress alias `@matterName` so tests can assert
 * on it later. Mirrors wave-d1-power-features.cy.ts createSampleMatter.
 */
function createSampleMatter(prefix = 'Cypress Wave D.2') {
	const matterName = `${prefix} ${Date.now()}`;
	cy.visit('/lq-ai/matters');

	// Intercept the create-matter POST so we can wait for the response
	// BEFORE asserting on the URL change. NewMatterModal calls onCreated()
	// (parent state refresh) then goto(); under SvelteKit's microtask
	// queue these sometimes race — refresh re-paints before goto resolves,
	// and the URL change is delayed past Cypress' default 4s retry.
	cy.intercept('POST', '/api/v1/projects').as('createMatter');

	cy.contains('button', '+ New matter').first().click();
	cy.get('[role="dialog"]').should('exist');
	cy.get('[role="dialog"]').find('input[type="text"]').first().clear().type(matterName);
	cy.contains('button', 'Create matter').click();

	// Wait for the create POST to land, then for the goto-driven URL change.
	// 15s URL timeout absorbs the SvelteKit micro-task drift after refresh().
	cy.wait('@createMatter').its('response.statusCode').should('eq', 201);
	cy.url({ timeout: 15000 }).should('match', /\/lq-ai\/matters\/[a-f0-9-]+$/);
	cy.get('[data-testid="lq-ai-chat-shell"]', { timeout: 10000 }).should('exist');

	// + New Chat → auto-selects → composer mounts. createNewChat passes the
	// matter id through as project_id so composerProjectId is set and the
	// skill-creator affordances render.
	cy.get('[data-testid="lq-ai-new-chat-btn"]').click();
	cy.get('[data-testid="lq-ai-composer-input"]', { timeout: 10000 }).should('be.visible');

	cy.wrap(matterName).as('matterName');
}

describe('Wave D.2 — Skill Creator', () => {
	beforeEach(() => {
		login(ADMIN_EMAIL(), ADMIN_PASSWORD());
	});

	it.skip('1. Capture happy path: AI reply → modal → save → skill in list', () => {
		// populated in Task 8.2
	});

	it.skip('2. Wizard from scratch: blank → fill 3 sections → set slash_alias → save', () => {
		// populated in Task 8.2
	});

	it.skip('3. Fork flow: detail page → fork → wizard pre-populated → save', () => {
		// populated in Task 8.3
	});

	it.skip('4. Slash invocation: type "/" in composer → popover → pick → pill → send', () => {
		// populated in Task 8.4
	});

	it.skip('5. Try-it sandbox: detail Try-it tab → ensure sandbox → send → conversation persists', () => {
		// populated in Task 8.4
	});

	it.skip('6. Versions tab + slash_alias collision: edit twice → tab shows 3 rows; collision → inline error', () => {
		// populated in Task 8.3
	});
});
