// Vendored from Svelte AI Elements (SikandarJODD/ai-elements), MIT — ADR-F011.
// See ../README.md for provenance + the token-remap convention.
//
// AE1 vendored the core layout primitives; AE2 adds the `actions/` subtree
// (hover toolbar: copy / retry / copy-sources, wired in MessageBubble). Still
// NOT vendored: the Streamdown-based `MessageResponse` (its sink would bypass
// our hardened `renderModelMarkdown` — we render the assistant "Response" as
// sanitized markdown inside MessageContent), and `branching` / `attachments`.
import Message from './core/message.svelte';
import MessageContent from './core/message-content.svelte';
import MessageAction from './actions/message-action.svelte';
import MessageActions from './actions/message-actions.svelte';
import MessageToolbar from './actions/message-toolbar.svelte';

export { Message, MessageContent, MessageAction, MessageActions, MessageToolbar };
export type {
	MessageRole,
	MessageVersion,
	MessageAttachmentData
} from './context/message-context.svelte.js';
