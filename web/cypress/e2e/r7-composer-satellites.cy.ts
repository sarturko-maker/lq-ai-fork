/**
 * R7 — Composer satellites: SlashPopover + EnhancePromptExpansion.
 *
 * Drives the legacy chat composer (`/lq-ai/chats`) with DETERMINISTIC,
 * backend-free fixtures so the same render is captured against the pre-R7
 * bundle (PHASE=before) and the R7 bundle (PHASE=after). Two satellite surfaces:
 *
 *   1. SlashPopover — type "/nda" at BOL → the skill typeahead listbox
 *      (`autocompleteSkills` intercepted). Asserts listbox a11y:
 *      role=listbox/option, aria-activedescendant tracks ArrowDown wrap.
 *   2. EnhancePromptExpansion — type a prompt, click ✨ → the inline
 *      Original/Enhanced diff panel (`enhance` intercepted). Asserts the panel
 *      shows both columns + the action buttons.
 *
 * Assertions are bundle-agnostic (role/aria/data-testid exist before AND after),
 * so the full spec runs on both phases; only the screenshot tags differ.
 *
 * Run (live stack, headed for honest dark-theme capture):
 *   cd web && npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/r7-composer-satellites.cy.ts' \
 *     --env LQAI_ADMIN_PASSWORD=LQ-AI-local-Pw1!,PHASE=before
 */
const PHASE = () => (Cypress.env('PHASE') as string) || 'after';

const CHAT_ID = '00000000-0000-4000-8000-0000000000a7';
const NOW = '2026-06-13T10:00:00Z';

const CHAT = {
	id: CHAT_ID,
	title: 'R7 — composer satellites demo',
	owner_id: 'admin',
	project_id: null,
	archived_at: null,
	message_count: 0,
	created_at: NOW,
	updated_at: NOW
};

const AUTOCOMPLETE = {
	results: [
		{
			slug: 'nda-review',
			slash_alias: 'nda',
			title: 'NDA Review',
			description: 'Review a non-disclosure agreement for one-sided terms.',
			scope: 'builtin',
			icon: '📜'
		},
		{
			slug: 'nda-redline',
			slash_alias: 'nda-redline',
			title: 'NDA Redline',
			description: 'Produce a redline against our standard mutual NDA.',
			scope: 'team',
			icon: null
		},
		{
			slug: 'nda-summary',
			slash_alias: 'nda-summary',
			title: 'NDA Summary',
			description: 'One-paragraph plain-English summary of an NDA.',
			scope: 'user',
			icon: '✨'
		}
	]
};

const ENHANCE = {
	interaction_id: '00000000-0000-4000-8000-0000000000e7',
	expansion_applied: true,
	expanded_prompt:
		'Review the attached mutual NDA and flag any clauses that are one-sided ' +
		'against the receiving party — focus on term length, residual-knowledge ' +
		'carve-outs, and the survival period. Cite each flagged clause.',
	reasoning: [
		'Added the controlling party (receiving) so the analysis has a viewpoint.',
		'Named the three highest-risk clause families to scope the review.'
	],
	preview_to_user: 'Sharpened the prompt with a viewpoint and a clause checklist.',
	routed_inference_tier: 4,
	routed_provider: 'minimax',
	routed_model: 'MiniMax-M3'
};

function login() {
	cy.visit('/lq-ai/login');
	cy.get('input[type="email"]').type(Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai');
	cy.get('input[type="password"]').type(Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-local-Pw1!');
	cy.get('button[type="submit"]').click();
	cy.url({ timeout: 15000 }).should('not.include', '/login');
}

function setTheme(mode: 'light' | 'dark') {
	cy.window().then((win) => {
		win.localStorage.setItem('theme', mode);
		win.document.documentElement.classList.remove('light', 'dark');
		win.document.documentElement.classList.add(mode);
	});
}

function stubChat() {
	// Anchor every stub to `/api/v1` (a bare `/chats` regex also catches the
	// `cy.visit` DOCUMENT request → "could not load · 200 application/json").
	cy.intercept('GET', /\/api\/v1\/chats(\?.*)?$/, { items: [CHAT], next_cursor: null }).as('chats');
	cy.intercept('GET', '**/api/v1/chats/*/messages*', { items: [], next_cursor: null }).as(
		'messages'
	);
	cy.intercept('GET', '**/api/v1/skills/autocomplete*', AUTOCOMPLETE).as('autocomplete');
	cy.intercept('POST', '**/api/v1/enhance-prompt', ENHANCE).as('enhance');
	cy.intercept('PATCH', '**/api/v1/enhance-prompt/*', { statusCode: 200, body: {} }).as('outcome');
}

function openComposer() {
	cy.visit(`/lq-ai/chats?id=${CHAT_ID}`);
	cy.get('[data-testid="lq-ai-composer-input"]', { timeout: 15000 }).should('be.visible');
}

function openSlash() {
	openComposer();
	cy.get('[data-testid="lq-ai-composer-input"]').clear().type('/nda');
	cy.wait('@autocomplete');
	cy.get('[data-testid="lq-ai-slash-popover-anchor"]').should('be.visible');
	cy.get('[role="option"]').should('have.length', AUTOCOMPLETE.results.length);
}

function openEnhance() {
	openComposer();
	// Force the first-run JIT strip to show (part of the surface under test).
	cy.window().then((win) => win.localStorage.removeItem('lq_ai_jit_enhance_seen'));
	cy.get('[data-testid="lq-ai-composer-input"]')
		.clear()
		.type('review this nda for one-sided terms');
	cy.get('[data-testid="lq-ai-enhance-btn"]').click();
	cy.wait('@enhance');
	cy.get('[data-testid="lq-ai-enhance-panel"]', { timeout: 10000 }).should('be.visible');
}

describe('R7 — composer satellites: semantic tokens + a11y', () => {
	beforeEach(() => {
		stubChat();
		login();
	});

	// ── SlashPopover: listbox keyboard / aria-activedescendant ──────────────────
	it('exposes a listbox whose aria-activedescendant tracks ArrowDown (with wrap)', () => {
		cy.viewport(1280, 800);
		openSlash();

		const listbox = () => cy.get('[role="listbox"][aria-label="Skill suggestions"]');

		// Initial: active row 0.
		listbox().should('have.attr', 'aria-activedescendant', 'lq-slash-row-0');
		cy.get('#lq-slash-row-0').should('have.attr', 'aria-selected', 'true');

		// ArrowDown advances the active descendant. The composer keeps focus; the
		// popover's <svelte:window on:keydown> owns the arrows.
		cy.get('[data-testid="lq-ai-composer-input"]').type('{downArrow}');
		listbox().should('have.attr', 'aria-activedescendant', 'lq-slash-row-1');
		cy.get('#lq-slash-row-1').should('have.attr', 'aria-selected', 'true');

		// Wrap: from the last row, ArrowDown returns to row 0.
		cy.get('[data-testid="lq-ai-composer-input"]').type('{downArrow}'); // -> row 2
		cy.get('[data-testid="lq-ai-composer-input"]').type('{downArrow}'); // wrap -> row 0
		listbox().should('have.attr', 'aria-activedescendant', 'lq-slash-row-0');

		// Escape dismisses the popover.
		cy.get('[data-testid="lq-ai-composer-input"]').type('{esc}');
		cy.get('[data-testid="lq-ai-slash-popover-anchor"]').should('not.exist');
	});

	// ── EnhancePromptExpansion: the Original/Enhanced diff + actions ─────────────
	it('shows the Original/Enhanced diff panel with action buttons', () => {
		cy.viewport(1280, 900);
		openEnhance();

		cy.get('[data-testid="lq-ai-enhance-original"]').should('contain', 'review this nda');
		cy.get('[data-testid="lq-ai-enhance-enhanced"]').should('contain', 'one-sided');
		// All three primary actions present and clickable.
		cy.get('[data-testid="lq-ai-enhance-use"]').should('be.visible');
		cy.get('[data-testid="lq-ai-enhance-edit"]').should('be.visible');
		cy.get('[data-testid="lq-ai-enhance-keep"]').should('be.visible');
		// Tier pill rendered (routed_inference_tier = 4).
		cy.get('[data-testid="lq-ai-enhance-panel"]').should('contain', 'Tier 4');
	});

	// ── Visual evidence: light/dark × wide/narrow ───────────────────────────────
	// One page load per surface (theme + viewport are toggled live), so the long
	// multi-navigation run can't outlive the access token — repeated `cy.visit`s
	// previously crossed the token TTL and got redirected to /login mid-capture.
	const SHOTS: Array<{ theme: 'light' | 'dark'; w: number; h: number; tag: string }> = [
		{ theme: 'light', w: 1280, h: 900, tag: 'wide' },
		{ theme: 'dark', w: 1280, h: 900, tag: 'wide' },
		{ theme: 'light', w: 760, h: 1100, tag: 'narrow' },
		{ theme: 'dark', w: 760, h: 1100, tag: 'narrow' }
	];

	it('captures the SlashPopover across themes and widths', () => {
		openComposer();
		for (const s of SHOTS) {
			cy.viewport(s.w, s.h);
			setTheme(s.theme);
			// Re-trigger the typeahead each shot so it's open regardless of reflow.
			cy.get('[data-testid="lq-ai-composer-input"]').clear().type('/nda');
			cy.wait('@autocomplete');
			cy.get('[data-testid="lq-ai-slash-popover-anchor"]').should('be.visible');
			cy.wait(150);
			cy.screenshot(`${PHASE()}-r7-slash-${s.theme}-${s.tag}`, { capture: 'viewport' });
		}
	});

	it('captures the EnhancePromptExpansion across themes and widths', () => {
		openComposer();
		// Force the first-run JIT strip to show (part of the surface under test).
		cy.window().then((win) => win.localStorage.removeItem('lq_ai_jit_enhance_seen'));
		cy.get('[data-testid="lq-ai-composer-input"]')
			.clear()
			.type('review this nda for one-sided terms');
		cy.get('[data-testid="lq-ai-enhance-btn"]').click();
		cy.wait('@enhance');
		cy.get('[data-testid="lq-ai-enhance-panel"]').should('be.visible');
		// The panel is state-driven (not focus-driven), so it survives live
		// theme/viewport toggles — no re-trigger needed.
		for (const s of SHOTS) {
			cy.viewport(s.w, s.h);
			setTheme(s.theme);
			cy.get('[data-testid="lq-ai-enhance-panel"]').should('be.visible');
			cy.wait(150);
			cy.screenshot(`${PHASE()}-r7-enhance-${s.theme}-${s.tag}`, { capture: 'viewport' });
		}
	});
});
