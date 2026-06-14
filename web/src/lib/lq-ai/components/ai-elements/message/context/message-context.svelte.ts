// Vendored from Svelte AI Elements (SikandarJODD/ai-elements), MIT — ADR-F011.
// See ../../README.md for provenance + the token-remap convention.
//
// AE1 vendored ONLY the core layout primitives (Message + MessageContent). The
// upstream `message` block also ships branching/attachments/actions and a
// `MessageBranchController` here — those are deferred (branching is not a fork
// concept yet; the actions land in AE2). Only the shared types are kept.
export type MessageRole = 'user' | 'assistant' | 'system' | 'function' | 'data' | 'tool';

export type MessageVersion = {
	id: string;
	content: string;
};

export type MessageAttachmentData = {
	type: 'file';
	filename?: string;
	mediaType?: string;
	url?: string;
};
