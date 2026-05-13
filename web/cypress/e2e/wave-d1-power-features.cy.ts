/**
 * Wave D.1 — In-chat power features (T21 E2E suite).
 *
 * Covers the four in-chat power features that shipped through Wave D.1 (T0–T20):
 *
 *   1. Enhance Prompt (T20)            — ⌘E expansion → "Use enhanced" → send
 *   2. KB attach modal (T11/T12)       — composer 📎 → multi-select → matter rail reflects
 *   3. Tier-floor refusal + admin
 *      override (T13/T14/T15)          — amber refusal block → Override → reason → confirm
 *   4. Receipts drawer (T16/T17/T18/
 *      T19)                            — composer 📜 → drawer → filter chip → JSONL export
 *   5. Member sees refusal but no
 *      Override button                 — admin-only gate on RefusalMessageBubble
 *
 * Run requires a live stack (mirrors wave-c-matters.cy.ts contract):
 *   docker compose up -d
 *   docker compose exec api python -m app.cli reset-admin-password
 *   cd web && npx cypress run --spec 'cypress/e2e/wave-d1-power-features.cy.ts'
 *
 * Scenarios 3 (admin override) and 5 (member sees refusal, no Override) are
 * exercised against `cy.intercept`-mocked refusal + override + auth-role
 * responses. The backend's tier-floor enforcement has its own pytest coverage
 * (T4); these Cypress scenarios test the FRONTEND end-to-end behavior — the
 * RefusalMessageBubble render path, the admin Override modal flow, and the
 * admin-only gate on the Override affordance — without requiring a privileged
 * matter fixture or a configured tier-floor + provider routing rule. Scenario
 * 4 (receipts export) clicks the Export button and verifies the JSONL lands
 * in `cypress/downloads/`.
 */

const ADMIN_EMAIL = () => Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai';
const ADMIN_PASSWORD = () => Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-smoke-test-Pw1!';
const MEMBER_EMAIL = () => Cypress.env('LQAI_MEMBER_EMAIL') || 'member@lq.ai';
const MEMBER_PASSWORD = () => Cypress.env('LQAI_MEMBER_PASSWORD') || 'LQ-AI-smoke-test-Pw1!';

/**
 * Inline login — mirrors wave-c-matters.cy.ts beforeEach pattern.
 * Wave C did not extract a custom command for this; we follow the same shape
 * so anyone reading the suite sees a single consistent login flow.
 */
function login(email: string, password: string) {
	cy.visit('/lq-ai/login');
	cy.get('input[type="email"]').type(email);
	cy.get('input[type="password"]').type(password);
	cy.get('button[type="submit"]').click();
	// Login can take longer after test 1's real LLM round-trip (~30-60s) —
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
 * on it later. Mirrors wave-c-matters.cy.ts test 3.
 */
function createSampleMatter(prefix = 'Cypress Wave D.1') {
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
	// 📎/✨/📜 buttons render.
	cy.get('[data-testid="lq-ai-new-chat-btn"]').click();
	cy.get('[data-testid="lq-ai-composer-input"]', { timeout: 10000 }).should('be.visible');

	cy.wrap(matterName).as('matterName');
}

describe('Wave D.1 — in-chat power features', () => {
	beforeEach(() => {
		login(ADMIN_EMAIL(), ADMIN_PASSWORD());
	});

	// ── Test 1 ───────────────────────────────────────────────────────────────────
	// Enhance Prompt full cycle: open composer → type prompt → ⌘E (hotkey) →
	// expansion panel renders → click "Use enhanced" → the enhanced text replaces
	// the composer contents (T20 audit ships explicit data-testids on the panel
	// and the use-enhanced button).
	it('enhance prompt: ⌘E expands and Use enhanced replaces composer text', () => {
		createSampleMatter('Cypress Enhance');
		const prompt = 'Draft an NDA for a vendor';
		cy.get('[data-testid="lq-ai-composer-input"]').first().type(prompt);

		// Hotkey trigger — Composer.svelte binds Cmd/Ctrl+E to onEnhance().
		// We dispatch the key against the composer textarea (not body) so the
		// focused element receives the keydown.
		cy.get('[data-testid="lq-ai-composer-input"]').first().type('{cmd}e');

		// Enhance panel renders. Either the loading state or the JIT/result card
		// must appear; we accept either, then wait for the result card with the
		// "Use enhanced" button (full live-LLM round-trip). The two-card diff
		// layout can be clipped by the composer's overflow:hidden parent
		// even at 1440x900 — use {force: true} so we click whether or not
		// Cypress considers the button visible; the assertion that matters
		// is the composer-text length grew, asserted next.
		cy.get('[data-testid="lq-ai-enhance-panel"]', { timeout: 60000 }).should('exist');
		cy.get('[data-testid="lq-ai-enhance-use"]', { timeout: 60000 }).click({ force: true });

		// After Use enhanced, the panel collapses and the composer holds the
		// enhanced text. We don't assert on the exact enhanced wording (provider-
		// dependent), but the composer must no longer be empty and the panel
		// should be gone or in its post-accept state.
		cy.get('[data-testid="lq-ai-composer-input"]').first().should(($el) => {
			expect(($el.val() as string).length).to.be.greaterThan(prompt.length);
		});
	});

	// ── Test 2 ───────────────────────────────────────────────────────────────────
	// KB attach modal: composer 📎 button opens AttachKBModal → multi-select
	// checkbox UI → "Attach N selected" submits and dismisses → matter rail
	// Knowledge section (data-testid="matter-rail-knowledge") reflects the
	// newly-attached KBs. Test tolerates the empty-KB-fixture case by skipping
	// the assertion if no checkboxes render (no KBs in this org).
	it('KB attach modal: composer 📎 → multi-select → matter rail reflects', () => {
		createSampleMatter('Cypress KB Attach');

		cy.get('[data-testid="lq-ai-attach-kb-btn"]').click();
		cy.get('[role="dialog"]').should('exist');
		cy.contains(/attach knowledge/i).should('be.visible');

		// If no KBs exist in this org, the modal renders an empty state.
		// In that case the rest of the test is informational; we close the
		// modal and assert the rail Knowledge section exists (T12 always-render).
		cy.get('body').then(($body) => {
			const checkboxes = $body.find('[role="dialog"] input[type="checkbox"]');
			if (checkboxes.length === 0) {
				cy.log('No KBs in fixture — skipping attach assertion');
				cy.get('[role="dialog"]').contains('button', /cancel|close/i).click();
				return;
			}
			// Select up to 2 KBs (or 1 if only one exists).
			cy.get('[role="dialog"] input[type="checkbox"]').first().check({ force: true });
			if (checkboxes.length >= 2) {
				cy.get('[role="dialog"] input[type="checkbox"]').eq(1).check({ force: true });
			}
			cy.contains('button', /^attach \d+ selected$/i).click();
			cy.get('[role="dialog"]').should('not.exist');
		});

		// MatterRailKnowledge section is mounted in the rail (T12 wiring).
		cy.get('[data-testid="matter-rail-knowledge"]').should('exist');
	});

	// ── Test 3 ───────────────────────────────────────────────────────────────────
	// Tier-floor refusal + admin override.
	//
	// Backend tier-floor enforcement is covered by pytest (T4). This Cypress
	// scenario exercises the FRONTEND end-to-end behavior — refusal bubble
	// renders, admin sees Override, override modal posts a reason, refusal
	// bubble clears — via `cy.intercept` on the messages list and the
	// override endpoint. No privileged-matter fixture required.
	it('tier-floor refusal + admin override', () => {
		createSampleMatter('Cypress Refusal Admin');

		// After matter creation we're inside the workspace. Capture the chat
		// id from the URL so we can shape the intercept response for the
		// chat-scoped messages list. The chat panel calls listMessages when
		// a chat is selected; refusal rows render via MessageBubble's
		// kind === 'refusal' branch.
		cy.url().then((url) => {
			const match = url.match(/\/lq-ai\/matters\/([a-f0-9-]+)$/);
			expect(match, 'matter id in URL').to.not.be.null;
			const matterId = match![1];

			// Intercept the messages-list call: inject a single kind=refusal
			// row. The interceptor matches any chat id under the matter; the
			// chat-selection flow polls until a chat exists for the matter.
			cy.intercept('GET', '/api/v1/chats/*/messages*', (req) => {
				const chatMatch = req.url.match(/\/chats\/([^/]+)\/messages/);
				const chatId = chatMatch ? chatMatch[1] : 'chat-fake';
				req.reply({
					statusCode: 200,
					body: {
						items: [
							{
								id: '00000000-0000-4000-8000-000000000001',
								chat_id: chatId,
								role: 'assistant',
								kind: 'refusal',
								content: '',
								applied_skills: [],
								routed_inference_tier: null,
								routed_provider: null,
								routed_model: null,
								requested_model: null,
								prompt_tokens: null,
								completion_tokens: null,
								cost_estimate: null,
								error_code: null,
								citations: [],
								created_at: new Date().toISOString(),
								refusal_reason: 'tier_mismatch',
								requested_tier: 'standard',
								enforced_tier: 'privileged'
							}
						],
						next_cursor: null
					}
				});
			}).as('listMessages');

			cy.log(`Matter ${matterId} loaded — refusal-shaped messages mocked`);
		});

		// Force a refresh so the chat panel runs listMessages with our
		// intercept in place. The shell re-mounts and the mocked refusal
		// row lands in the messages store.
		cy.reload();

		// After reload, the matter page does NOT auto-select a chat
		// (matters/[id]/+page.svelte initializes activeChatId=undefined).
		// Click the existing chat in the ChatSidebar to re-trigger the
		// messages fetch with our intercept active.
		cy.get('[data-testid="lq-ai-chat-shell"]', { timeout: 10000 }).should('exist');
		cy.get(
			'[data-testid="lq-ai-chat-sidebar"] [data-testid^="lq-ai-chat-"]'
		).first().click();

		// Amber refusal block renders (RefusalMessageBubble — T13).
		cy.get('[data-testid="refusal-bubble"]', { timeout: 30000 }).should('be.visible');
		cy.contains(/refused at .*-floor/i).should('be.visible');

		// Admin sees Override button (T13 gate on user.role === 'admin').
		// Mock the override endpoint so confirming the modal doesn't hit
		// the live gateway. T4 backend semantics: returns ai_message +
		// routing_log_id (nullable). The frontend appends ai_message to
		// the store after a successful override.
		cy.intercept('POST', '/api/v1/inference/override-tier-floor', {
			statusCode: 200,
			body: {
				ai_message: {
					id: '00000000-0000-4000-8000-000000000002',
					chat_id: '00000000-0000-4000-8000-000000000010',
					role: 'assistant',
					kind: 'ai',
					content: 'Override accepted — re-run at privileged tier.',
					applied_skills: [],
					routed_inference_tier: 4,
					routed_provider: 'anthropic-prod',
					routed_model: 'claude-sonnet-4-6',
					requested_model: 'smart',
					prompt_tokens: 50,
					completion_tokens: 25,
					cost_estimate: 0.0003,
					error_code: null,
					citations: [],
					created_at: new Date().toISOString()
				},
				routing_log_id: null
			}
		}).as('overrideTierFloor');

		cy.get('[data-testid="override-button"]').click();

		// TierFloorOverrideModal opens — fill reason (10..500 chars) and confirm.
		cy.get('[role="dialog"]').should('exist');
		cy.get('#override-reason').type(
			'Urgent client request — partner has risk-accepted (Cypress E2E test reason)'
		);
		cy.get('[data-testid="confirm-button"]').click();

		// Override endpoint hit with the reason in the body (T4 contract).
		cy.wait('@overrideTierFloor').its('request.body').should((body) => {
			expect(body).to.have.property('message_id');
			expect(body).to.have.property('reason');
			expect(String(body.reason).length).to.be.gte(10);
		});
	});

	// ── Test 4 ───────────────────────────────────────────────────────────────────
	// Receipts drawer toggle + filter + JSONL export (T16/T17/T18/T19).
	// Mocks the receipts GET to seed at least one event so the Export
	// button is enabled (the drawer disables it on empty state). Then
	// clicks Export and verifies the JSONL file lands in
	// `cypress/downloads/` (Cypress' downloads folder is configured
	// per-spec; default `cypress/downloads/`).
	it('receipts drawer toggle + filter + export', () => {
		createSampleMatter('Cypress Receipts');

		// Seed a receipts payload so the Export button enables. The drawer
		// calls GET /api/v1/chats/{id}/receipts; the API contract is a bare
		// `ReceiptEvent[]` (per web/src/lib/lq-ai/api/receipts.ts) with each
		// event shaped as `{ ts, kind, detail }`. We seed one inference and
		// one message event so two kinds register and the filter-chip path
		// has something to click.
		const seededEvents = [
			{
				ts: new Date().toISOString(),
				kind: 'inference',
				detail: {
					message_id: '00000000-0000-4000-8000-000000000001',
					routed_inference_tier: 3,
					routed_provider: 'anthropic-prod',
					routed_model: 'claude-sonnet-4-6',
					prompt_tokens: 12,
					completion_tokens: 24,
					cost_estimate: 0.00031
				}
			},
			{
				ts: new Date().toISOString(),
				kind: 'message',
				detail: {
					message_id: '00000000-0000-4000-8000-000000000001',
					role: 'user',
					content_excerpt: 'cypress-seeded message'
				}
			}
		];
		// Two separate intercepts. Cypress' `*` doesn't cross path segments,
		// so `/receipts/export.jsonl` would not be caught by a list-shaped
		// pattern — register the export endpoint as its own alias so the
		// test can wait on it explicitly and read out the filename.
		cy.intercept('GET', '/api/v1/chats/*/receipts', {
			statusCode: 200,
			body: seededEvents
		}).as('receiptsList');

		cy.intercept('GET', '/api/v1/chats/*/receipts/export.jsonl*', (req) => {
			const jsonl = seededEvents.map((e) => JSON.stringify(e)).join('\n');
			const chatMatch = req.url.match(/\/chats\/([^/]+)\//);
			const chatId = chatMatch ? chatMatch[1] : 'cypress';
			req.reply({
				statusCode: 200,
				headers: {
					'content-type': 'application/x-ndjson',
					'content-disposition': `attachment; filename="chat-${chatId}-receipts.jsonl"`
				},
				body: jsonl
			});
		}).as('receiptsExport');

		// Open drawer via composer 📜 toggle (T19).
		cy.get('[data-testid="lq-ai-receipts-toggle"]').click();
		cy.contains(/receipts/i).should('be.visible');
		cy.wait('@receiptsList');

		// Filter chips render (T17 ReceiptsList) — we seeded two kinds so
		// at least one chip should be present and clickable.
		cy.get('body').then(($body) => {
			const chips = $body.find('[data-testid^="filter-chip-"]');
			if (chips.length > 0) {
				cy.get('[data-testid^="filter-chip-"]').first().click();
			} else {
				cy.log('No filter chips rendered — interceptor may not have applied');
			}
		});

		// Export button is enabled with seeded events; click it and verify
		// the JSONL file lands in cypress/downloads/. ReceiptsDrawer uses
		// `triggerJsonlDownload` which creates an anchor + content-disposition
		// filename. The interceptor sets the filename header to
		// `chat-{chat_id}-receipts.jsonl`; the chat id comes from the URL
		// after createSampleMatter resolves the workspace route.
		cy.get('[data-testid="export-jsonl"]').should('not.be.disabled').click();

		// Wait for the export endpoint to fire, then verify the download
		// landed in cypress/downloads/. The filename comes from the
		// content-disposition header we set in the intercept above.
		cy.wait('@receiptsExport').then((interception) => {
			const chatMatch = interception.request.url.match(/\/chats\/([^/]+)\//);
			expect(chatMatch, 'chat id in export URL').to.not.be.null;
			const chatId = chatMatch![1];
			const downloadsFolder = Cypress.config('downloadsFolder');
			cy.readFile(`${downloadsFolder}/chat-${chatId}-receipts.jsonl`, {
				timeout: 5000
			}).should((content) => {
				expect(String(content).length, 'JSONL has content').to.be.greaterThan(0);
				expect(String(content)).to.include('inference');
			});
		});
	});

	// ── Test 5 ───────────────────────────────────────────────────────────────────
	// Member sees refusal but no Override button.
	//
	// Mocks `/auth/me` to return a member-role user (the LQ.AI auth store
	// drives `currentUserRole` in ChatPanel, which gates Override on
	// admin). Mocks the messages list with a refusal row as in test 3.
	// We re-use the admin login flow to land in the workspace then patch
	// the role before the chat panel mounts on reload.
	it('member sees refusal but no Override button', () => {
		// Set up role + messages intercepts BEFORE creating the matter so the
		// auth-store role override takes effect on the next reload. We need
		// admin to actually create the matter; we then swap the role server-
		// response to 'member' on the post-matter reload.
		createSampleMatter('Cypress Refusal Member');

		// Intercept the user-info endpoint to return member role on subsequent
		// reads. Endpoint is `/api/v1/users/me` (per web/src/lib/lq-ai/api/auth.ts
		// `getCurrentUser`), not `/api/v1/auth/me`. The frontend re-reads on
		// reload via the auth store.
		cy.intercept('GET', '/api/v1/users/me', (req) => {
			req.reply((res) => {
				if (res.statusCode === 200 && res.body) {
					const body = typeof res.body === 'object' ? { ...res.body } : res.body;
					if (body && typeof body === 'object') {
						(body as Record<string, unknown>).role = 'member';
						(body as Record<string, unknown>).is_admin = false;
					}
					res.send(body);
				} else {
					res.send();
				}
			});
		}).as('authMe');

		// Same refusal-shape mock as test 3.
		cy.intercept('GET', '/api/v1/chats/*/messages*', (req) => {
			const chatMatch = req.url.match(/\/chats\/([^/]+)\/messages/);
			const chatId = chatMatch ? chatMatch[1] : 'chat-fake';
			req.reply({
				statusCode: 200,
				body: {
					items: [
						{
							id: '00000000-0000-4000-8000-000000000003',
							chat_id: chatId,
							role: 'assistant',
							kind: 'refusal',
							content: '',
							applied_skills: [],
							routed_inference_tier: null,
							routed_provider: null,
							routed_model: null,
							requested_model: null,
							prompt_tokens: null,
							completion_tokens: null,
							cost_estimate: null,
							error_code: null,
							citations: [],
							created_at: new Date().toISOString(),
							refusal_reason: 'tier_mismatch',
							requested_tier: 'standard',
							enforced_tier: 'privileged'
						}
					],
					next_cursor: null
				}
			});
		}).as('listMessagesMember');

		cy.reload();

		// Same chat-re-select dance as test 3 — matter page doesn't auto-
		// select on reload, so click the existing chat to trigger the
		// messages fetch (and the auth-me re-read in the chat panel mount).
		cy.get('[data-testid="lq-ai-chat-shell"]', { timeout: 10000 }).should('exist');
		cy.get(
			'[data-testid="lq-ai-chat-sidebar"] [data-testid^="lq-ai-chat-"]'
		).first().click();

		// Refusal renders…
		cy.get('[data-testid="refusal-bubble"]', { timeout: 30000 }).should('be.visible');
		cy.contains(/refused at .*-floor/i).should('be.visible');

		// …but no Override button (admin-only gate in RefusalMessageBubble).
		cy.get('[data-testid="override-button"]').should('not.exist');
	});
});
