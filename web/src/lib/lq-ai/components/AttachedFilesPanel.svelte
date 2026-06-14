<script lang="ts">
	/**
	 * Per-chat attached-files panel.
	 *
	 * M1 surface: file picker, upload progress, list of attached files,
	 * detach. Project-attached files (inherited from the chat's Project) are
	 * shown read-only with a tag — those flow through `attached_file_ids`
	 * on the project.
	 *
	 * The file's `ingestion_status` is surfaced (pending / processing /
	 * ready / failed) so the user can see when a file is parseable.
	 *
	 * The citation engine is a future-release item; this panel deliberately
	 * does not surface citation links yet (and the message bubble renders
	 * nothing for empty citation arrays — see MessageBubble's docstring).
	 *
	 * R8: migrated to Svelte 5 runes + semantic tokens (cockpit `bg-card`/
	 * `border-border`); the two duplicated file-row blocks collapse onto the
	 * shared `primitives/UploadChip.svelte`; the "+ Files" button is the
	 * shadcn `Button` primitive (runes is what lets its `onclick` forward).
	 * No `<style>` block.
	 */
	import { Button } from '$lib/components/ui/button';
	import UploadChip from './primitives/UploadChip.svelte';
	import type { FileMeta } from '../types';

	let {
		chatFiles = [],
		projectFiles = [],
		uploading = false,
		onUpload = () => undefined,
		onDetach = () => undefined
	}: {
		chatFiles?: FileMeta[];
		projectFiles?: FileMeta[];
		uploading?: boolean;
		onUpload?: (file: File) => void;
		onDetach?: (file: FileMeta) => void;
	} = $props();

	let fileInput = $state<HTMLInputElement | null>(null);

	function handlePicked(event: Event) {
		const input = event.target as HTMLInputElement;
		if (input.files && input.files.length > 0) {
			onUpload(input.files[0]);
			input.value = '';
		}
	}
</script>

<section
	class="flex w-72 flex-col gap-3 overflow-y-auto border-l border-border bg-card p-3"
	data-testid="lq-ai-attached-files-panel"
>
	<div>
		<h3 class="text-sm font-semibold text-foreground">Attached files</h3>
		<p class="mt-0.5 text-xs text-muted-foreground">Upload documents the skill should review.</p>
	</div>

	<Button
		variant="outline"
		size="sm"
		class="self-start"
		onclick={() => fileInput?.click()}
		disabled={uploading}
		data-testid="lq-ai-upload-btn"
	>
		{uploading ? 'Uploading…' : '+ Files'}
	</Button>
	<input
		bind:this={fileInput}
		type="file"
		class="hidden"
		onchange={handlePicked}
		data-testid="lq-ai-file-input"
	/>

	{#if chatFiles.length > 0}
		<div>
			<h4 class="mb-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">
				This chat
			</h4>
			<ul class="space-y-1">
				{#each chatFiles as f (f.id)}
					<UploadChip file={f} {onDetach} />
				{/each}
			</ul>
		</div>
	{/if}

	{#if projectFiles.length > 0}
		<div>
			<h4 class="mb-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">
				From project (read-only here)
			</h4>
			<ul class="space-y-1">
				{#each projectFiles as f (f.id)}
					<UploadChip file={f} readonly />
				{/each}
			</ul>
		</div>
	{/if}

	{#if chatFiles.length === 0 && projectFiles.length === 0}
		<p class="text-xs text-muted-foreground italic">No files attached yet.</p>
	{/if}
</section>
