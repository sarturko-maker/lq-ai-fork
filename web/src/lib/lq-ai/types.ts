/**
 * Hand-typed wire shapes for the LQ.AI backend.
 *
 * Source of truth: docs/api/backend-openapi.yaml. These are the schemas the
 * LQ.AI chat shell consumes; not every backend schema is mirrored here.
 *
 * Contract test in __tests__/types.contract.test.ts pins the field set against
 * the OpenAPI sketch's required-list. If you add a property here, add it to
 * the contract test too.
 */

// ----- Auth / users -----

export type UserRole = 'admin' | 'member' | 'viewer';

export type ReasoningVisibility = 'always_show' | 'disclosure' | 'on_request';
export type FeaturedTools = 'prominent' | 'inline';
export type WorkspaceLayout = 'three_pane' | 'two_pane' | 'one_pane';
export type TrustPills = 'labels' | 'dots';
export type ProvenancePills = 'always' | 'collapsed';

export interface Preferences {
	reasoning_visibility: ReasoningVisibility;
	featured_tools: FeaturedTools;
	workspace_layout: WorkspaceLayout;
	trust_pills: TrustPills;
	provenance_pills: ProvenancePills;
}

export type PreferencesUpdate = Partial<Preferences>;

export interface User {
	id: string;
	email: string;
	display_name?: string | null;
	is_admin: boolean;
	role?: UserRole;
	mfa_enabled: boolean;
	must_change_password: boolean;
	created_at: string;
	last_login_at?: string | null;
	reasoning_visibility?: ReasoningVisibility;
	featured_tools?: FeaturedTools;
	workspace_layout?: WorkspaceLayout;
	trust_pills?: TrustPills;
	provenance_pills?: ProvenancePills;
}

export interface LoginRequest {
	email: string;
	password: string;
}

export interface LoginResponse {
	access_token: string;
	token_type: 'Bearer';
	expires_in: number;
	refresh_token?: string;
	user: User;
}

export interface TokenResponse {
	access_token: string;
	refresh_token: string;
	token_type: 'Bearer';
	expires_in: number;
}

export interface ChangePasswordRequest {
	current_password: string;
	new_password: string;
}

// ----- MFA -----

export interface MfaSetupResponse {
	secret: string;
	provisioning_uri: string;
	recovery_codes: string[];
}

export interface MfaEnableRequest {
	code: string;
}

export interface MfaDisableRequest {
	password: string;
	code: string;
}

// ----- Account ops -----

export type ExportJobStatus = 'queued' | 'processing' | 'completed' | 'failed';

export interface ExportJob {
	job_id: string;
	status: ExportJobStatus;
	download_url?: string | null;
}

export interface DeleteScheduledResponse {
	scheduled_deletion_at: string;
	grace_period_days: number;
}

// ----- Errors -----

export interface ErrorBody {
	detail?: {
		code: string;
		message: string;
		details?: Record<string, unknown>;
	};
}

// ----- Projects -----

export interface Project {
	id: string;
	name: string;
	slug: string;
	description?: string | null;
	context_md?: string | null;
	owner_id: string;
	privileged: boolean;
	minimum_inference_tier?: 1 | 2 | 3 | 4 | 5 | null;
	attached_skill_names?: string[];
	attached_file_ids?: string[];
	attached_knowledge_base_ids?: string[];
	archived_at?: string | null;
	created_at: string;
	updated_at: string;
}

export interface ProjectCreate {
	name: string;
	slug?: string;
	description?: string;
	context_md?: string;
	privileged?: boolean;
	minimum_inference_tier?: 1 | 2 | 3 | 4 | 5;
}

// ----- Chats / messages -----

export interface Chat {
	id: string;
	title: string;
	owner_id: string;
	project_id?: string | null;
	archived_at?: string | null;
	message_count?: number;
	created_at: string;
	updated_at: string;
}

export interface ChatCreate {
	title?: string;
	project_id?: string | null;
}

export interface ChatUpdate {
	title?: string;
	archived?: boolean;
}

export interface PaginatedChats {
	items: Chat[];
	next_cursor: string | null;
}

// ----- Chat search (Wave B — /chats/search) -----

export interface ChatSearchHit {
	chat_id: string;
	title: string;
	snippet: string;
	match_source: 'title' | 'message';
	rank: number;
	created_at: string;
	updated_at: string;
}

export interface ChatSearchResponse {
	items: ChatSearchHit[];
	query: string;
}

export interface Citation {
	id: string;
	source_file_id: string;
	source_offset_start: number;
	source_offset_end: number;
	source_page?: number | null;
	source_text: string;
	verified: boolean;
}

export type MessageRole = 'user' | 'assistant' | 'system' | 'tool';

export interface Message {
	id: string;
	chat_id: string;
	role: MessageRole;
	content: string;
	applied_skills?: string[];
	routed_inference_tier?: 1 | 2 | 3 | 4 | 5 | null;
	routed_provider?: string | null;
	routed_model?: string | null;
	/**
	 * Originally-requested model alias or `provider/model` (ADR 0011
	 * follow-on). Differs from `routed_model` when an alias resolved
	 * server-side; null on rows persisted before this column existed.
	 */
	requested_model?: string | null;
	prompt_tokens?: number | null;
	completion_tokens?: number | null;
	cost_estimate?: number | null;
	error_code?: string | null;
	citations?: Citation[];
	created_at: string;
}

export interface PaginatedMessages {
	items: Message[];
	next_cursor: string | null;
}

export interface MessageCreate {
	content: string;
	model?: string;
	stream?: boolean;
	skills?: string[];
	skill_inputs?: Record<string, Record<string, unknown>>;
}

export interface MessagePostResponse {
	message: Message;
	citations: Citation[];
	routed_inference_tier?: 1 | 2 | 3 | 4 | 5 | null;
	routed_provider?: string | null;
	cost_estimate?: number | null;
	applied_skills?: string[];
}

// ----- SSE message-stream events -----

export interface MessageStartFrame {
	type: 'start';
	lq_ai_message_id: string;
	chat_id: string;
}

export interface MessageDeltaFrame {
	type: 'delta';
	delta: string;
	lq_ai_message_id: string;
	routed_inference_tier?: 1 | 2 | 3 | 4 | 5 | null;
	applied_skills?: string[];
}

export interface MessageCompleteFrame {
	type: 'complete';
	lq_ai_message_id: string;
	message: Message;
	citations?: Citation[];
	applied_skills?: string[];
	routed_inference_tier?: 1 | 2 | 3 | 4 | 5 | null;
	routed_provider?: string | null;
}

export interface MessageErrorFrame {
	type: 'error';
	error: {
		code: string;
		message: string;
		details?: Record<string, unknown>;
	};
}

export type MessageStreamEvent =
	| MessageStartFrame
	| MessageDeltaFrame
	| MessageCompleteFrame
	| MessageErrorFrame;

// ----- Skills -----

export interface SkillInputDef {
	name: string;
	type?: 'string' | 'enum' | 'boolean' | 'integer';
	required?: boolean;
	description?: string;
	enum?: string[];
	default?: unknown;
}

export interface SkillSummary {
	name: string;
	version: string;
	scope: 'builtin' | 'user' | 'team';
	title: string;
	description?: string;
	tags?: string[];
	jurisdiction?: string;
	minimum_inference_tier?: 1 | 2 | 3 | 4 | 5;
	output_format?: string;
}

export interface SkillReferenceFile {
	path: string;
	content: string;
}

export interface Skill extends SkillSummary {
	content_yaml: string;
	content_md: string;
	reference_files?: SkillReferenceFile[];
	example_files?: SkillReferenceFile[];
	/**
	 * Parsed inputs from the frontmatter. The OpenAPI sketch surfaces only
	 * `content_yaml` (the raw frontmatter); we parse it client-side to drive
	 * the input form. The shape mirrors `docs/skill-authoring-guide.md`.
	 *
	 * The backend MAY surface `inputs` as a top-level field in a future
	 * iteration; for now the LQ.AI shell parses YAML.
	 */
	inputs?: SkillInputDef[];
}

/** Response shape for GET /api/v1/skills/{name}/inputs. Resolves user > team > built-in. */
export interface SkillInputs {
	name: string;
	required: SkillInputDef[];
	optional: SkillInputDef[];
}

// ----- Files -----

export type IngestionStatus = 'pending' | 'processing' | 'ready' | 'failed';

export interface FileMeta {
	id: string;
	owner_id: string;
	project_id?: string | null;
	filename: string;
	mime_type: string;
	size_bytes: number;
	hash_sha256?: string;
	ingestion_status?: IngestionStatus;
	ingestion_error?: string | null;
	page_count?: number | null;
	character_count?: number | null;
	created_at: string;
}

// ----- Saved prompts (D7 / DE-013) -----

/**
 * Per-user saved prompt fragment. Lighter than a skill (no folder, no
 * frontmatter, no semver) — the in-chat reuse case for "the way I always
 * ask for an executive summary." Mirrors the ``SavedPrompt`` schema in
 * ``docs/api/backend-openapi.yaml``.
 */
export interface SavedPrompt {
	id: string;
	user_id: string;
	name: string;
	prompt_text: string;
	tags: string[];
	created_at: string;
	updated_at: string;
}

export interface SavedPromptCreate {
	name: string;
	prompt_text: string;
	tags?: string[];
}

export interface SavedPromptUpdate {
	name?: string;
	prompt_text?: string;
	tags?: string[];
}

// ----- User skills (D8 / ADR 0012) -----

/**
 * A DB-backed user- or team-scope skill. Shadows filesystem-canonical
 * built-ins (per ADR 0004) at slug collision when resolved for the
 * owning user's chats (user shadow) or for any team member's chats
 * (team shadow). The D8.1b resolver picks user > team > built-in.
 * Mirrors the ``UserSkill`` schema in ``docs/api/backend-openapi.yaml``.
 *
 * Exactly one of ``owner_user_id`` / ``owner_team_id`` is set (DB
 * CHECK ``ck_user_skills_scope_owner_consistency``); the other is
 * null.
 */
export interface UserSkill {
	id: string;
	scope: 'user' | 'team';
	owner_user_id: string | null;
	owner_team_id: string | null;
	slug: string;
	display_name: string;
	description: string;
	version: string;
	tags: string[];
	frontmatter_extra: Record<string, unknown>;
	body: string;
	archived_at: string | null;
	created_at: string;
	updated_at: string;
}

export interface UserSkillCreate {
	slug: string;
	display_name: string;
	description: string;
	body: string;
	version?: string;
	tags?: string[];
	frontmatter_extra?: Record<string, unknown>;
	/** D8.1b — defaults to 'user' on the server when omitted. */
	scope?: 'user' | 'team';
	/** Required when scope='team'; must be null/omitted when scope='user'. */
	owner_team_id?: string | null;
}

export interface UserSkillUpdate {
	display_name?: string;
	description?: string;
	body?: string;
	version?: string;
	tags?: string[];
	frontmatter_extra?: Record<string, unknown>;
}

// ----- Enhance Prompt (T6) -----

export interface EnhancePromptAttachedSkill {
	name: string;
	description?: string | null;
}

export interface EnhancePromptAttachedFile {
	file_id?: string | null;
	filename: string;
	mime_type?: string | null;
	description?: string | null;
}

export interface EnhancePromptRequest {
	raw_input: string;
	chat_id?: string | null;
	attached_skills?: EnhancePromptAttachedSkill[];
	attached_files?: EnhancePromptAttachedFile[];
	jurisdiction?: string | null;
	model?: string | null;
}

export interface EnhancePromptResponse {
	interaction_id: string;
	expansion_applied: boolean;
	expanded_prompt: string;
	reasoning: string[];
	skip_reason?: string | null;
	preview_to_user?: string;
	routed_inference_tier?: 1 | 2 | 3 | 4 | 5 | null;
	routed_provider?: string | null;
	routed_model?: string | null;
}

export interface EnhancePromptOutcomeUpdate {
	used?: boolean;
	edited_before_use?: boolean;
}

// ----- Admin usage -----

export type UsageGroupBy = 'user' | 'provider' | 'model' | 'tier' | 'day';

export interface UsageRow {
	group_key: string;
	request_count: number;
	tokens_in_sum: number;
	tokens_out_sum: number;
	cost_estimate_sum: number;
}

export interface UsageResponse {
	rows: UsageRow[];
	group_by: UsageGroupBy;
	total_request_count: number;
	total_tokens_in: number;
	total_tokens_out: number;
	total_cost_estimate: number;
}

export interface UsageQuery {
	group_by?: UsageGroupBy;
	date_from?: string;
	date_to?: string;
	user_id?: string;
	provider?: string;
	tier?: number;
}

// ----- Admin users -----

export interface AdminUserRow {
  id: string;
  email: string;
  display_name?: string | null;
  role: UserRole;
  is_admin: boolean;
  mfa_enabled: boolean;
  must_change_password: boolean;
  created_at: string;
  last_login_at?: string | null;
  deletion_scheduled_at?: string | null;
}

export interface AdminUserListResponse {
  users: AdminUserRow[];
  total_count: number;
  limit: number;
  offset: number;
}

export interface AdminUserListQuery {
  role?: UserRole;
  email_q?: string;
  limit?: number;
  offset?: number;
}

// ----- Teams (D8.1a + D8.1c caller_role) -----

/**
 * Compact team shape returned by the listing endpoints. ``caller_role``
 * (D8.1c) is populated for user-facing ``GET /api/v1/teams`` responses
 * and null for operator-admin views where the admin isn't a member.
 */
export interface TeamSummary {
	id: string;
	slug: string;
	name: string;
	description: string | null;
	created_by_user_id: string;
	member_count: number;
	caller_role: 'admin' | 'member' | null;
	created_at: string;
	updated_at: string;
}

export interface TeamMember {
	user_id: string;
	email: string;
	display_name: string | null;
	role: 'admin' | 'member';
	added_by_user_id: string;
	created_at: string;
}

export interface Team extends TeamSummary {
	members: TeamMember[];
}
