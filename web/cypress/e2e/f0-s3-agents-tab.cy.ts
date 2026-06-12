/**
 * F0-S3 — Agents tab v0: the first visible deep agent.
 * F0-S8 update: blank workspace is GONE (ADR-F002) — this spec now
 * CREATES a matter through the in-place "+ New matter" modal and runs
 * bound to it, doubling as the S8 create-in-place live evidence. It
 * stays self-sufficient: no pre-seeded matter needed.
 *
 * Drives a REAL agent run end-to-end against the live dev stack: logs in
 * through the UI, opens the Agents tab, creates a matter without leaving
 * the page, submits a prompt, and asserts the final answer renders with
 * reasoning collapsed. Screenshots double as the ADR-F005
 * live-verification evidence.
 *
 * Run requires a live stack (and a gateway model that answers):
 *   docker compose up -d
 *   cd web && npx cypress run --spec 'cypress/e2e/f0-s3-agents-tab.cy.ts'
 *
 * The run costs one short MiniMax-M3 loop (~4 steps). Credentials are the
 * local dev defaults; this spec never runs in CI (CI has no stack).
 */

/// <reference types="cypress" />

const EMAIL = Cypress.env('LQ_AI_EMAIL') ?? 'admin@lq.ai';
const PASSWORD = Cypress.env('LQ_AI_PASSWORD') ?? 'LQ-AI-local-Pw1!';

// A full loop is model turn -> tool call -> tool result -> model turn at
// MiniMax latitude; 90s absorbs slow first-token without masking hangs.
const RUN_TIMEOUT_MS = 90_000;

describe('F0-S3 — Agents tab v0 (live deep agent)', () => {
	it('logs in, creates a matter in place, runs the Commercial preview agent, and watches it work', () => {
		const matterName = `S3 Spec ${Date.now()}`;

		cy.visit('/lq-ai/login');
		// First element gets a warm-up window — a freshly rebuilt web
		// container hydrates slowly on this box.
		cy.get('[data-testid="lq-ai-login-email"]', { timeout: 30_000 }).type(EMAIL);
		cy.get('[data-testid="lq-ai-login-password"]').type(PASSWORD, { log: false });
		cy.get('[data-testid="lq-ai-login-submit"]').click();

		// Tab is registered and reachable from the shell.
		// F1-S2: post-login lands in the cockpit (no tab bar) — the legacy
		// agents tab keeps working at its URL. Wait out the redirect first:
		// visiting mid-login CANCELS the in-flight POST (the old tab-click
		// waited implicitly).
		cy.url({ timeout: 15_000 }).should('not.include', '/login');
		cy.visit('/lq-ai/agents');
		cy.location('pathname').should('eq', '/lq-ai/agents');
		cy.get('[data-testid="lq-ai-agents-area-card"]').should('contain.text', 'Commercial');

		// Capability rail renders the honest tool universe, all dim. With no
		// matter selected this is the 9 deepagents builtins — the matter
		// document tools only appear once a matter is bound (F0-S4), and the
		// demo tool is gone for good.
		cy.get('[data-testid="lq-ai-agents-rail"] li').should('have.length', 9);
		cy.get('[data-testid="lq-ai-agents-rail"] li.ag-rail__tool--lit').should('have.length', 0);
		cy.screenshot('f0-s3-1-agents-tab-idle', { capture: 'viewport' });

		// ADR-F002 (F0-S8): no blank workspace — without a matter the Run
		// button stays disabled even with a prompt typed.
		cy.get('[data-testid="lq-ai-agents-composer"] textarea').type(
			'What is the liability cap under this contract? Use your tools.'
		);
		cy.get('[data-testid="lq-ai-agents-composer"] button[type="submit"]').should('be.disabled');

		// Create a matter WITHOUT leaving the agent (F0-S8): same modal +
		// POST /projects plumbing as the Matters tab, full form.
		cy.get('[data-testid="lq-ai-agents-new-matter"]').click();
		cy.get('#nmm-name').type(matterName);
		cy.contains('button', 'Create matter').click();

		// The new matter binds in place: select shows it, the rail flips to
		// the matter-bound universe (9 builtins + 2 document tools), and we
		// never navigated away.
		cy.location('pathname').should('eq', '/lq-ai/agents');
		cy.get('[data-testid="lq-ai-agents-matter-select"]')
			.find('option:selected')
			.should('have.text', matterName);
		cy.get('[data-testid="lq-ai-agents-rail"] li').should('have.length', 11);
		cy.screenshot('f0-s3-1b-matter-created-bound', { capture: 'viewport' });

		// Count detail polls so we can prove polling stops after the run settles.
		// Since F0-S5 the page polls the CONVERSATION, not the run (ADR-F008).
		cy.intercept('GET', '**/api/v1/agents/threads/*').as('pollRun');

		// Kick off a real run (the prompt typed above survived the modal).
		cy.get('[data-testid="lq-ai-agents-composer"] button[type="submit"]').should('be.enabled');
		cy.get('[data-testid="lq-ai-agents-composer"] button[type="submit"]').click();

		// The run surface appears and activity settles in via polling. A
		// single-turn direct answer dedups its only model turn out of the
		// timeline (visibleSteps), so accept EITHER a step OR the answer —
		// the comma selector is a union.
		cy.get('[data-testid="lq-ai-agents-run"]').should('exist');
		cy.get('[data-testid="lq-ai-agents-run"] .ag-steps li, [data-testid="lq-ai-agents-answer"]', {
			timeout: RUN_TIMEOUT_MS
		}).should('have.length.at.least', 1);
		cy.screenshot('f0-s3-2-agent-working', { capture: 'viewport' });

		// No tool lighting is asserted: the matter is freshly created and
		// EMPTY, so an honest agent may search-and-find-nothing or answer
		// directly. The f0-s4 spec pins tool dispatch deterministically on
		// a matter with ingested documents.

		// Completion: badge flips and a non-empty final answer renders.
		// (No assertion on model-chosen prose — that flakes; on an empty
		// matter there is nothing deterministic to pin. Grounded-content
		// assertions live in the f0-s4 matter-bound spec.)
		cy.get('[data-testid="lq-ai-agents-run"]')
			.contains('.ag-badge', 'Completed', { timeout: RUN_TIMEOUT_MS })
			.should('exist');
		cy.get('[data-testid="lq-ai-agents-answer"] .prose')
			.invoke('text')
			.should('have.length.greaterThan', 20);
		// Reasoning is collapsed behind the <details> affordance, not inlined.
		// MiniMax-M3 reliably opens with a <think> block; if a future dev model
		// stops emitting them, relax this to a conditional on the API record.
		cy.get('[data-testid="lq-ai-agents-answer"] details.ag-thinking').should('exist');
		cy.get('[data-testid="lq-ai-agents-answer"] .prose').should(($el) => {
			expect($el.text()).not.to.contain('<think>');
		});
		cy.screenshot('f0-s3-3-agent-completed', { capture: 'viewport' });

		// Polling actually stops once the run settles (no zombie 2s loop).
		cy.get('@pollRun.all').then((calls) => {
			const settled = (calls as unknown as unknown[]).length;
			cy.wait(5000);
			cy.get('@pollRun.all').then((later) => {
				expect((later as unknown as unknown[]).length).to.eq(settled);
			});
		});

		// The settled conversation shows up in the conversations list (F0-S5).
		cy.get('[data-testid="lq-ai-agents-runs-list"] li').should('have.length.at.least', 1);
	});
});
