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

export interface User {
	id: string;
	email: string;
	display_name?: string | null;
	is_admin: boolean;
	mfa_enabled: boolean;
	must_change_password: boolean;
	created_at: string;
	last_login_at?: string | null;
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
