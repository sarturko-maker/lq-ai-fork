/**
 * B-4 — org-authored playbooks through the harness (ADR-F067 D2/D3).
 *
 * DETERMINISTIC: auth stays LIVE (a real admin session), but the playbooks
 * list, the propose/proposals endpoints, and the admin review-queue reads +
 * approve are INTERCEPTED — no seeded-DB coupling, no flake. It proves the WEB
 * half of the propose→review→approve state machine (the playbook analogue of
 * b2b-org-skills):
 *   1. the "Propose to Library" row action renders only on an OWNED playbook
 *      (created_by === the caller), never a built-in; clicking it POSTs
 *      /playbooks/{id}/propose and surfaces the success banner + a status chip;
 *   2. the admin Library page renders the org-playbook review queue with the
 *      FROZEN positions read-only (issue / standard language), and Approve
 *      round-trips POST /admin/org-playbooks/{id}/approve then reloads the queue.
 *
 * The live "propose → approve → adopt → bind → agent cites the snapshot" is the
 * maintainer's browser/real-model UAT — this spec pins the deterministic wiring.
 *
 * Run (live stack for auth):
 *   cd web && DISPLAY=:0 npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/b4-org-playbooks.cy.ts' \
 *     --env LQAI_ADMIN_PASSWORD=<dev-admin-pw>
 */
import { login } from '../support/lq-ai-helpers';

const ADMIN_EMAIL = () => Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai';
const ADMIN_PASSWORD = () => Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-local-Pw1!';

const OWNED_PB_ID = '00000000-0000-4000-8000-0000000042a1';
const BUILTIN_PB_ID = '00000000-0000-4000-8000-0000000042b2';
const VERSION_ID = '00000000-0000-4000-8000-0000000042c3';

const ownedPlaybook = (createdBy: string) => ({
	id: OWNED_PB_ID,
	name: 'My NDA Playbook',
	contract_type: 'NDA',
	description: 'Standard NDA positions authored by me.',
	version: '1.0.0',
	created_by: createdBy,
	created_at: '2026-01-01T00:00:00Z',
	updated_at: '2026-01-01T00:00:00Z',
	positions: []
});

const builtinPlaybook = () => ({
	id: BUILTIN_PB_ID,
	name: 'Shipped MSA Playbook',
	contract_type: 'MSA',
	description: 'A built-in playbook — never proposable.',
	version: '2.0.0',
	created_by: null,
	created_at: '2026-01-01T00:00:00Z',
	updated_at: '2026-01-01T00:00:00Z',
	positions: []
});

const proposalResponse = () => ({
	id: VERSION_ID,
	playbook_id: OWNED_PB_ID,
	version_no: 1,
	state: 'proposed',
	content_hash: 'a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2',
	size_bytes: 512,
	position_count: 1,
	proposed_at: '2026-07-09T00:00:00Z',
	reviewed_at: null,
	review_note: null,
	revoked_at: null
});

const adminVersion = (state: 'proposed' | 'approved') => ({
	id: VERSION_ID,
	playbook_id: OWNED_PB_ID,
	version_no: 1,
	state,
	name: 'My NDA Playbook',
	contract_type: 'NDA',
	description: 'Standard NDA positions authored by me.',
	playbook_version: '1.0.0',
	author_user_id: 'author-uuid',
	author_email: 'lawyer@company.example',
	proposed_at: '2026-07-09T00:00:00Z',
	reviewed_by: state === 'approved' ? 'admin-uuid' : null,
	approver_email: state === 'approved' ? ADMIN_EMAIL() : null,
	reviewed_at: state === 'approved' ? '2026-07-09T01:00:00Z' : null,
	review_note: null,
	revoked_at: null,
	content_hash: 'a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2',
	size_bytes: 512,
	position_count: 1,
	positions: [
		{
			issue: 'Definition of Confidential Information',
			description: 'Confidential Information must be defined broadly.',
			standard_language: 'Confidential Information means all non-public information disclosed…',
			fallback_tiers: [
				{
					rank: 1,
					description: 'Narrower carve-out',
					language: 'excluding publicly available data'
				}
			],
			redline_strategy: 'add standard carve-outs',
			severity_if_missing: 'high',
			detection_keywords: ['confidential', 'proprietary'],
			detection_examples: ['"Confidential Information" shall mean…'],
			position_order: 0
		}
	]
});

describe('B-4 org-authored playbooks', () => {
	it('proposes an owned playbook to the Library from the list page', () => {
		cy.viewport(1280, 900);
		login(ADMIN_EMAIL(), ADMIN_PASSWORD());

		// The propose button gates on created_by === the logged-in user's id, so
		// stamp the owned row with the real session user id.
		cy.window().then((win) => {
			const raw = win.localStorage.getItem('lq_ai_auth');
			const uid = raw ? JSON.parse(raw).user.id : 'unknown';

			cy.intercept('GET', '**/api/v1/playbooks', {
				body: [ownedPlaybook(uid), builtinPlaybook()]
			});
			cy.intercept('GET', '**/api/v1/playbooks/*/proposals', { body: [] });
			cy.intercept('POST', '**/api/v1/playbooks/*/propose', (req) => {
				req.reply({ statusCode: 201, body: proposalResponse() });
			}).as('propose');

			cy.visit('/lq-ai/playbooks');
			cy.get('[data-testid="lq-playbooks-table"]', { timeout: 30000 }).should('exist');

			// Owned row shows the propose button; the built-in row does NOT.
			cy.get(`[data-playbook-id="${OWNED_PB_ID}"]`)
				.find('[data-testid="lq-playbook-propose"]')
				.should('exist')
				.and('contain.text', 'Propose to Library');
			cy.get(`[data-playbook-id="${BUILTIN_PB_ID}"]`)
				.find('[data-testid="lq-playbook-propose"]')
				.should('not.exist');

			cy.get(`[data-playbook-id="${OWNED_PB_ID}"]`)
				.find('[data-testid="lq-playbook-propose"]')
				.click();

			cy.wait('@propose').then((i) => {
				expect(i.request.url).to.contain(`/playbooks/${OWNED_PB_ID}/propose`);
			});

			// Success banner + inline status chip reflect the new proposal.
			cy.get('[data-testid="lq-playbook-propose-success"]')
				.should('be.visible')
				.and('contain.text', 'My NDA Playbook');
			cy.get(`[data-playbook-id="${OWNED_PB_ID}"]`)
				.find('[data-testid="lq-playbook-proposal-status"]')
				.should('contain.text', 'Proposed');

			cy.screenshot('b4-propose-owned-playbook', { capture: 'viewport' });
		});
	});

	it('reviews the frozen positions and approves in the admin Library queue', () => {
		let approved = false;

		cy.viewport(1280, 900);
		login(ADMIN_EMAIL(), ADMIN_PASSWORD());

		// Page chrome (adopted sections + the skill queue) — kept empty so the
		// playbook queue is the surface under test.
		cy.intercept('GET', '**/api/v1/library', { body: { entries: [] } });
		cy.intercept('GET', '**/api/v1/practice-areas', { body: { practice_areas: [] } });
		cy.intercept('GET', '**/api/v1/admin/org-skills*', { body: { versions: [] } });

		cy.intercept('GET', '**/api/v1/admin/org-playbooks*', (req) => {
			// After approval the 'proposed' filter is empty (round-trip reload).
			req.reply({ body: { versions: approved ? [] : [adminVersion('proposed')] } });
		}).as('pbQueue');
		cy.intercept('POST', '**/api/v1/admin/org-playbooks/*/approve', (req) => {
			approved = true;
			req.reply({ body: adminVersion('approved') });
		}).as('pbApprove');

		cy.visit('/lq-ai/admin/library');
		cy.get('[data-testid="lq-admin-library-page"]', { timeout: 30000 }).should('exist');
		cy.get('[data-testid="lq-admin-pb-review-queue"]').should('be.visible');

		// Expand the proposal → the FROZEN positions render read-only.
		cy.get(`[data-testid="lq-admin-org-playbook-${VERSION_ID}-toggle"]`).click();
		cy.get(`[data-testid="lq-admin-org-playbook-${VERSION_ID}-positions"]`).should('be.visible');
		cy.get('[data-testid="lq-playbook-ro-issue"]').should(
			'contain.text',
			'Definition of Confidential Information'
		);
		cy.get('[data-testid="lq-playbook-ro-standard"]').should(
			'contain.text',
			'Confidential Information means'
		);
		cy.get(`[data-testid="lq-admin-org-playbook-${VERSION_ID}-hash"]`).should(
			'contain.text',
			'a1b2c3d4'
		);

		// Approve → POST round-trip + queue reload (now empty on the proposed filter).
		cy.get(`[data-testid="lq-admin-org-playbook-${VERSION_ID}-approve"]`).click();
		cy.wait('@pbApprove').then((i) => {
			expect(i.request.url).to.contain(`/admin/org-playbooks/${VERSION_ID}/approve`);
		});
		cy.get('[data-testid="lq-admin-pb-review-queue-empty"]').should('be.visible');

		cy.screenshot('b4-approve-org-playbook', { capture: 'viewport' });
	});
});
