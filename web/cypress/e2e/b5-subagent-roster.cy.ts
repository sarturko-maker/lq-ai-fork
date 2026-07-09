/**
 * B-5 — sub-agent roster admin form (surfaces ADR-F034's roster; validated by
 * `build_area_subagents`, ADR-F010/F017).
 *
 * DETERMINISTIC: auth stays LIVE (a real admin session), but the practice-areas
 * list, the deployment-capabilities catalog, and the PATCH are INTERCEPTED — no
 * seeded-DB coupling, no flake. It proves the WEB half of the JSON→form swap:
 *   1. a seeded 3-sub-agent roster renders as EDITABLE rows (name/instructions),
 *      never a JSON textarea;
 *   2. editing one sub-agent's instructions + Save PATCHes the WHOLE `agent_config`
 *      — the edited `system_prompt`, all three sub-agents, the by-reference
 *      `playbooks` passthrough PRESERVED, and NO `model`/`tools` key (ADR-F010);
 *   3. adding a blank sub-agent disables Save and surfaces the required-field gate.
 *
 * The live "edit clause-drafter → run a fan-out matter → the sub-agent's output
 * reflects the edit" behavioural check is the maintainer's browser/real-model UAT
 * (the edited system_prompt is server-side config, never on the wire) — this spec
 * pins the deterministic form wiring the same way hitl3-confirm-card pins the card.
 *
 * Run (live stack for auth):
 *   cd web && DISPLAY=:0 npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/b5-subagent-roster.cy.ts' \
 *     --env LQAI_ADMIN_PASSWORD=<dev-admin-pw>
 */
import { login } from '../support/lq-ai-helpers';

const ADMIN_EMAIL = () => Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai';
const ADMIN_PASSWORD = () => Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-local-Pw1!';

const AREA_ID = '00000000-0000-4000-8000-0000000041a1';
const PLAYBOOK_ID = '00000000-0000-4000-8000-0000000041b2';

// A seeded-style Commercial roster (shape mirrors migration 0073) plus a
// by-reference `playbooks` key the form must preserve untouched.
const seededAgentConfig = () => ({
	subagents: [
		{
			name: 'document-researcher',
			description: 'Investigate a question across the matter documents.',
			system_prompt: 'You are a document researcher.',
			skills: ['contract-qa', 'nda-review']
		},
		{
			name: 'clause-drafter',
			description: 'Draft a client-protective position for one clause.',
			system_prompt: 'You are a commercial contracts drafter.',
			skills: ['surgical-redline', 'nda-review']
		},
		{
			name: 'clause-reviewer',
			description: 'Adversarially reconcile the drafted positions.',
			system_prompt: 'You are a senior reviewer.',
			skills: ['deal-review', 'contract-qa']
		}
	],
	playbooks: [PLAYBOOK_ID]
});

const commercial = (agent_config: Record<string, unknown>) => ({
	id: AREA_ID,
	key: 'commercial',
	name: 'Commercial',
	unit_label: 'Matter',
	configured: true,
	position: 0,
	profile_md: '# Commercial',
	default_tier_floor: null,
	default_budget_profile: null,
	agent_config,
	hitl_policy: {},
	hitl_eligible_tools: [],
	bound_skills: ['contract-qa', 'nda-review', 'surgical-redline', 'deal-review'],
	bound_tool_groups: [],
	bound_playbooks: [],
	bound_knowledge_bases: [],
	created_at: '2026-01-01T00:00:00Z',
	updated_at: '2026-01-01T00:00:00Z'
});

const skillEntry = (key: string) => ({
	capability_kind: 'skill',
	capability_key: key,
	label: key,
	description: null,
	in_library: true,
	enabled: true,
	source: 'built-in'
});

const capabilities = () => ({
	sections: [
		{ kind: 'tool', label: 'Tools', entries: [] },
		{
			kind: 'skill',
			label: 'Skills',
			entries: ['contract-qa', 'nda-review', 'surgical-redline', 'deal-review'].map(skillEntry)
		},
		{ kind: 'playbook', label: 'Playbooks', entries: [] },
		{ kind: 'knowledge', label: 'Knowledge', entries: [] }
	]
});

describe('B-5 sub-agent roster form', () => {
	it('renders the seeded roster as editable rows and round-trips a PATCH', () => {
		let current = seededAgentConfig();

		cy.viewport(1280, 900);
		login(ADMIN_EMAIL(), ADMIN_PASSWORD());

		cy.intercept('GET', '**/api/v1/practice-areas', (req) =>
			req.reply({ practice_areas: [commercial(current)] })
		);
		cy.intercept('GET', '**/api/v1/admin/capabilities', capabilities());
		cy.intercept('PATCH', '**/api/v1/practice-areas/commercial', (req) => {
			current = req.body.agent_config;
			req.reply(commercial(current));
		}).as('patch');

		cy.visit('/lq-ai/admin/areas/commercial');
		cy.get('[data-testid="lq-admin-area-page"]', { timeout: 30000 }).should('exist');

		// (1) Roster renders as three editable rows — no JSON textarea.
		cy.get('[data-testid="lq-admin-area-roster-list"]').should('be.visible');
		cy.get('[data-testid="lq-admin-area-roster-item-0"]').should('exist');
		cy.get('[data-testid="lq-admin-area-roster-item-2"]').should('exist');
		cy.get('[data-testid="lq-admin-area-roster-name-1"]').should('have.value', 'clause-drafter');
		cy.get('[data-testid="lq-admin-area-roster"]').should('not.exist'); // the old JSON textarea is gone

		// Save is disabled until something changes (dirty gate).
		cy.get('[data-testid="lq-admin-area-roster-save"]').should('be.disabled');

		// (2) Edit clause-drafter's instructions → Save PATCHes the whole config.
		cy.get('[data-testid="lq-admin-area-roster-instructions-1"]')
			.clear()
			.type('You are a commercial contracts drafter. Begin with DRAFTER-EDIT-OK.');
		cy.get('[data-testid="lq-admin-area-roster-save"]').should('not.be.disabled').click();

		cy.wait('@patch').then((i) => {
			const cfg = i.request.body.agent_config;
			const subs = cfg.subagents;
			expect(subs).to.have.length(3);
			expect(subs[1].name).to.eq('clause-drafter');
			expect(subs[1].system_prompt).to.contain('DRAFTER-EDIT-OK');
			expect(subs[1].skills).to.deep.eq(['surgical-redline', 'nda-review']);
			// No forbidden keys anywhere (ADR-F010 gateway-bypass fence).
			subs.forEach((s: Record<string, unknown>) => {
				expect(s).not.to.have.property('model');
				expect(s).not.to.have.property('tools');
			});
			// By-reference passthrough preserved untouched.
			expect(cfg.playbooks).to.deep.eq([PLAYBOOK_ID]);
		});
		cy.screenshot('b5-roster-commercial', { capture: 'viewport' });

		// After save the row keeps the edit and Save re-disables (re-synced, not dirty).
		cy.get('[data-testid="lq-admin-area-roster-save"]').should('be.disabled');

		// (3) Add a blank sub-agent → required-field gate disables Save + shows errors.
		cy.get('[data-testid="lq-admin-area-roster-add"]').click();
		cy.get('[data-testid="lq-admin-area-roster-item-3"]').should('exist');
		cy.get('[data-testid="lq-admin-area-roster-errors"]').should('be.visible');
		cy.get('[data-testid="lq-admin-area-roster-save"]').should('be.disabled');
		cy.get('[data-testid="lq-admin-area-roster-remove-3"]').click();
		cy.get('[data-testid="lq-admin-area-roster-item-3"]').should('not.exist');
	});
});
