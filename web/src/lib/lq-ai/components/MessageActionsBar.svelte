<!--
	AE2 (ADR-F011) — per-message hover-action toolbar for assistant messages.

	Wraps the vendored AI Elements `MessageActions`/`MessageAction` primitives so
	the shadcn `Button` `onclick` is forwarded from a **runes** parent (a legacy
	parent's `on:click` on a runes component is a silent no-op — see HANDOFF
	gotchas). `MessageBubble` stays legacy and feeds this bar plain props +
	callbacks, which cross the legacy→runes boundary cleanly.

	Copy/copy-sources are self-contained (clipboard + a transient "copied" tick);
	Retry delegates to the caller (re-runs the preceding prompt through the normal
	send path). Quiet by default, brightening on hover — the AI Elements look.
-->
<script lang="ts">
	import {
		MessageActions,
		MessageAction
	} from '$lib/lq-ai/components/ai-elements/message/index.js';
	import Copy from '@lucide/svelte/icons/copy';
	import Check from '@lucide/svelte/icons/check';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import Quote from '@lucide/svelte/icons/quote';

	let {
		/** The answer text to copy (think-stripped, the same text the user reads). */
		answer,
		/** Pre-formatted source lines; empty array hides the copy-sources action. */
		sources = [],
		/** Disable Retry while a stream is in flight. */
		retryDisabled = false,
		/** Re-run the prompt that produced this message. */
		onRetry = () => {}
	}: {
		answer: string;
		sources?: string[];
		retryDisabled?: boolean;
		onRetry?: () => void;
	} = $props();

	let copied = $state(false);
	let copyTimer: ReturnType<typeof setTimeout> | undefined;

	async function copy(text: string): Promise<void> {
		if (!text) return;
		try {
			await navigator.clipboard.writeText(text);
			copied = true;
			if (copyTimer) clearTimeout(copyTimer);
			copyTimer = setTimeout(() => (copied = false), 1500);
		} catch (err) {
			// Clipboard can be blocked (permissions / insecure context); fail
			// quietly — copy is a convenience, never load-bearing.
			console.warn('[AE2] clipboard write failed', err);
		}
	}
</script>

<MessageActions
	class="opacity-70 transition-opacity group-hover:opacity-100 focus-within:opacity-100"
	data-testid="lq-ai-message-actions"
>
	<MessageAction
		tooltip={copied ? 'Copied' : 'Copy'}
		label="Copy answer"
		data-testid="lq-ai-action-copy"
		onclick={() => copy(answer)}
	>
		{#if copied}
			<Check class="size-4" aria-hidden="true" />
		{:else}
			<Copy class="size-4" aria-hidden="true" />
		{/if}
	</MessageAction>

	<MessageAction
		tooltip="Retry"
		label="Re-run this prompt"
		data-testid="lq-ai-action-retry"
		disabled={retryDisabled}
		onclick={() => onRetry()}
	>
		<RefreshCw class="size-4" aria-hidden="true" />
	</MessageAction>

	{#if sources.length > 0}
		<MessageAction
			tooltip="Copy sources"
			label="Copy sources"
			data-testid="lq-ai-action-copy-sources"
			onclick={() => copy(sources.join('\n'))}
		>
			<Quote class="size-4" aria-hidden="true" />
		</MessageAction>
	{/if}
</MessageActions>
