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
/** Direct API base — bypasses the SvelteKit web container which has no POST proxy for user-skills routes. */
const API_BASE = () => Cypress.env('LQAI_API_BASE') ?? 'http://localhost:8000';

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

	it('1. Capture happy path: AI reply → modal → save → skill in list', () => {
		// Timestamp suffix makes name/slug unique across repeated runs so we
		// never get a 409 from a prior run's stale row.
		const ts = Date.now();
		const skillName = `Sales Contract Structure ${ts}`;
		const skillSlug = `sales-contract-structure-${ts}`;

		createSampleMatter('Capture Test Matter');

		// createSampleMatter lands on the matter workspace with the composer
		// visible. Type a prompt and send it via the Send button.
		cy.get('[data-testid="lq-ai-composer-input"]').first().type('Summarize the typical structure of a sales contract.');
		cy.get('[data-testid="lq-ai-send-btn"]').click();

		// Wait for an AI reply — the inline capture button mounts immediately on
		// assistant messages but stays disabled while streaming. Poll until it
		// becomes enabled (streaming complete) then click. 90s accommodates
		// slow LLM round-trips. The `:not([disabled])` CSS pseudo-class causes
		// cy.get to retry until a matching (enabled) element exists.
		cy.get('[data-testid="lq-ai-message-capture-inline"]:not([disabled])', { timeout: 90000 })
			.first()
			.click();

		// Capture modal mounts.
		cy.get('[data-testid="lq-ai-capture-skill-modal"]').should('exist');

		// Override the auto-derived name and slug with known values so the
		// list assertion below is deterministic.
		cy.get('[data-testid="lq-ai-capture-name"]').clear().type(skillName);
		cy.get('[data-testid="lq-ai-capture-slug"]').clear().type(skillSlug);

		// Intercept BEFORE the save click — once the button fires the POST
		// the alias must already be registered.
		cy.intercept('POST', '/api/v1/user-skills').as('createSkill');
		cy.get('[data-testid="lq-ai-capture-save"]').click();
		cy.wait('@createSkill').its('response.statusCode').should('eq', 201);

		// Navigate to the skills list and confirm the new skill row is present.
		cy.visit('/lq-ai/skills');
		cy.contains('[data-testid="lq-ai-user-skill-row"]', skillName).should('exist');
	});

	it('2. Wizard from scratch: blank → fill 3 sections → set slash_alias → save', () => {
		// Use a timestamp suffix to avoid 409 collisions on repeated runs.
		const ts = Date.now();
		const displayName = `D.2 Test Skill ${ts}`;
		// kebab('D.2 Test Skill <ts>') → 'd-2-test-skill-<ts>' (dots and spaces
		// → dashes, trimmed). The slug auto-derives reactively from the display name.
		const expectedSlug = `d-2-test-skill-${ts}`;

		cy.visit('/lq-ai/skills');
		cy.get('[data-testid="lq-ai-user-skills-new-link"]').click();
		cy.url().should('include', '/lq-ai/skills/new');

		// Section 1 — display name (slug auto-derives until user touches the slug field).
		cy.get('[data-testid="lq-ai-wizard-display-name"]').type(displayName);
		// Assert the reactive slug matches the kebab-derived value.
		cy.get('[data-testid="lq-ai-wizard-slug"]').should('have.value', expectedSlug);

		// Section 1 continued — description.
		cy.get('[data-testid="lq-ai-wizard-description"]').type('Test skill for Wave D.2 Cypress spec.');

		// Slash alias (Section 2 area in the wizard). Include ts suffix to
		// avoid the slash_alias partial-unique constraint on repeated runs.
		cy.get('[data-testid="lq-ai-wizard-slash-alias"]').type(`/d2-test-${ts}`);

		// Section 3 — body (required for canSave to return true).
		cy.get('[data-testid="lq-ai-wizard-body"]').type('# D.2 test\nThis skill is a Cypress fixture.');

		// Intercept BEFORE the save click.
		cy.intercept('POST', '/api/v1/user-skills').as('createSkill');
		cy.get('[data-testid="lq-ai-wizard-save"]').click();
		cy.wait('@createSkill').its('response.statusCode').should('eq', 201);

		// onSave navigates to /lq-ai/skills/{slug}?just_saved=1.
		cy.url({ timeout: 10000 }).should('include', `/lq-ai/skills/${expectedSlug}`);

		// The skill detail page renders SkillDetailTabs which always has a
		// "Use it" tab label — presence confirms the detail page loaded.
		cy.contains(/use it/i, { timeout: 10000 }).should('exist');
	});

	it('3. Fork flow: detail page → fork → wizard pre-populated → save', () => {
		// Timestamp suffix makes the forked slug unique across reruns so the
		// uniqueSlug dedup in skills/new/+page.svelte doesn't silently append -2.
		const ts = Date.now();
		const forkSlug = `nda-review-fork-${ts}`;

		// Navigate to the nda-review built-in detail page. The detail page
		// renders a "🔱 Fork as my own" anchor with aria-label
		// "Fork nda-review as my own" (per +page.svelte line ~58-62).
		cy.visit('/lq-ai/skills/nda-review');

		// Wait for the skill to load — the header h1 mounts once `skill` is set.
		cy.contains('h1', /nda/i, { timeout: 10000 }).should('exist');

		// Click the fork link. The link href is
		// `/lq-ai/skills/new?fork=nda-review`; no need for cy.url() assertion
		// since clicking an <a> navigates directly.
		cy.contains('a', /fork as my own/i).click();

		// Wait for the wizard to mount (the display-name input must be visible
		// before we assert its value, since the fork data is loaded async in
		// onMount of +page.svelte).
		cy.get('[data-testid="lq-ai-wizard-display-name"]', { timeout: 10000 }).should('be.visible');

		// The wizard's onMount sets displayName = `${source.title ?? source.name} (fork)`
		// and slug = await uniqueSlug(`${source.name}-fork`) → "nda-review-fork"
		// (possibly -2 on reruns but we are not asserting exact slug, we override it).
		cy.get('[data-testid="lq-ai-wizard-display-name"]').should(($el) => {
			const val = ($el.val() as string) ?? '';
			expect(val.toLowerCase()).to.match(/\(fork\)$/);
		});

		// Description must be non-empty (seeded from source.description).
		cy.get('[data-testid="lq-ai-wizard-description"]').should(($el) => {
			const val = ($el.val() as string) ?? '';
			expect(val.trim()).to.not.equal('');
		});

		// Override the auto-derived slug with a timestamped one so this test
		// is idempotent across reruns. cy.clear() resets slugTouched via the
		// on:input handler, then type() arms slugTouched so auto-derive stops.
		cy.get('[data-testid="lq-ai-wizard-slug"]').clear().type(forkSlug);

		// Intercept BEFORE the save click.
		cy.intercept('POST', '/api/v1/user-skills').as('saveFork');
		cy.get('[data-testid="lq-ai-wizard-save"]:not([disabled])').click();
		cy.wait('@saveFork').then((interception) => {
			expect(interception.response?.statusCode).to.eq(201);
			// forked_from field is set in buildPayload → POST body.
			expect(interception.request.body.forked_from).to.eq('nda-review');
		});

		// onSave navigates to /lq-ai/skills/{slug}?just_saved=1.
		cy.url({ timeout: 10000 }).should('include', `/lq-ai/skills/${forkSlug}`);
	});

	it.skip('4. Slash invocation: type "/" in composer → popover → pick → pill → send', () => {
		// populated in Task 8.4
	});

	it.skip('5. Try-it sandbox: detail Try-it tab → ensure sandbox → send → conversation persists', () => {
		// populated in Task 8.4
	});

	it('6. Versions tab + slash_alias collision: edit twice → tab shows 3 rows; collision → inline error', () => {
		// Timestamp suffix makes slug and slash_alias unique across reruns so
		// the pre-seed never collides with a prior run's stale row.
		const ts = Date.now();
		const targetSlug = `d2-versions-${ts}`;
		const targetAlias = `/d2t${ts}`.slice(0, 33); // backend max 32 chars after /

		// ── Pre-seed: create skill + 2 edits via cy.request ─────────────────
		// cy.request fires outside the browser session's fetch, so we must
		// carry the bearer token ourselves. The LQ.AI auth store writes the
		// session under the key `lq_ai_auth` in localStorage as a JSON object
		// with an `access_token` field (api/client.ts + auth/store.ts).

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

			const headers = { Authorization: `Bearer ${token}` };

			// Create the skill
			cy.request({
				method: 'POST',
				url: `${API_BASE()}/api/v1/user-skills`,
				headers,
				body: {
					scope: 'user',
					slug: targetSlug,
					display_name: 'D2 Versions Target',
					description: 'd',
					body: 'b',
					version: '1.0.0',
					slash_alias: targetAlias
				}
			})
				.its('body.id')
				.then((skillId: string) => {
					// Edit 1: update description
					cy.request({
						method: 'PATCH',
						url: `${API_BASE()}/api/v1/user-skills/${skillId}`,
						headers,
						body: { description: 'd2' }
					});
					// Edit 2: update body (column is `body` on PATCH too, per
					// UserSkillUpdate in user_skills.py)
					cy.request({
						method: 'PATCH',
						url: `${API_BASE()}/api/v1/user-skills/${skillId}`,
						headers,
						body: { body: 'b2' }
					});
				});
		});

		// ── Versions tab: expect 3 audit rows ────────────────────────────────
		// The Versions tab renders the audit log with `{v.action}` directly in
		// the Action column (SkillVersionsTab.svelte line ~157). Actions are
		// `user_skill.created` and `user_skill.updated` (api/user_skills.py).
		cy.visit(`/lq-ai/skills/${targetSlug}?tab=versions`);

		// Wait for the versions table to appear.
		cy.get('[data-testid="lq-ai-versions-table"]', { timeout: 10000 }).should('exist');

		// 1 created + 2 updated = 3 rows in the tbody.
		cy.get('[data-testid="lq-ai-versions-table"] tbody tr', { timeout: 10000 }).should('have.length', 3);

		// The table's Action column shows the raw action string from the
		// audit log (`user_skill.created` / `user_skill.updated`).
		cy.contains('[data-testid="lq-ai-versions-table"]', 'user_skill.created').should('exist');
		cy.contains('[data-testid="lq-ai-versions-table"]', 'user_skill.updated').should('exist');

		// ── Collision: try to create a new skill with the same slash_alias ───
		// The backend returns 422 with
		// `"slash_alias '<alias>' is already used by another of your skills."`.
		// SkillWizard catches the 422, checks for "slash_alias" in the error
		// string, and populates `slashAliasError` (rendered inline near the
		// alias input via the `{#if slashAliasError}` block — not via the
		// `lq-ai-wizard-save-error` banner).
		cy.visit('/lq-ai/skills/new');
		cy.get('[data-testid="lq-ai-wizard-display-name"]').type('Collision Test');
		cy.get('[data-testid="lq-ai-wizard-description"]').type('collision description');
		cy.get('[data-testid="lq-ai-wizard-body"]').type('collision body');
		cy.get('[data-testid="lq-ai-wizard-slash-alias"]').type(targetAlias);

		cy.intercept('POST', '/api/v1/user-skills').as('collide');
		cy.get('[data-testid="lq-ai-wizard-save"]:not([disabled])').click();
		cy.wait('@collide').its('response.statusCode').should('eq', 422);

		// SkillWizard renders the slash_alias inline error (not the banner)
		// when the 422 detail contains "slash_alias". The fallback text is
		// "That slash alias is already used by another of your skills (slash_alias /...)".
		// Both the fallback and the raw backend string contain "already used".
		cy.contains(/already used/i, { timeout: 5000 }).should('exist');
	});
});
