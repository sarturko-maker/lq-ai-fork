// Vendored from Svelte AI Elements (SikandarJODD/ai-elements), MIT — ADR-F011.
// See ../README.md for provenance + the token-remap convention.
//
// AE1 vendored only the core layout primitives. The upstream `message` block
// additionally ships branching / attachments / actions / a Streamdown-based
// `MessageResponse` — intentionally NOT vendored (the response sink would
// bypass our hardened `renderModelMarkdown`; actions land in AE2). We render
// the assistant "Response" as our sanitized markdown inside MessageContent.
import Message from './core/message.svelte';
import MessageContent from './core/message-content.svelte';

export { Message, MessageContent };
export type {
	MessageRole,
	MessageVersion,
	MessageAttachmentData
} from './context/message-context.svelte.js';
