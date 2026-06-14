<!--
	UploadChip — one attached-file row (R8). Collapses the duplicated chat-file /
	project-file markup that AttachedFilesPanel hand-rolled twice. Shows the
	filename, a dark-safe ingestion-status badge, the size, and (for detachable
	files) a hover-revealed detach affordance. `readonly` renders the
	project-inherited variant with no detach. Semantic tokens only — the status
	tones carry `dark:` lifts so they read AA on the charcoal surface.
-->
<script lang="ts" module>
	/** Dark-safe tone per ingestion status. Exported so callers/tests can reuse. */
	export function statusTone(status: string | undefined): string {
		switch (status) {
			case 'ready':
				return 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300';
			case 'processing':
				return 'bg-amber-500/10 text-amber-700 dark:text-amber-300';
			case 'failed':
				return 'bg-destructive/10 text-destructive dark:text-red-300';
			case 'pending':
			default:
				return 'bg-muted text-muted-foreground';
		}
	}
</script>

<script lang="ts">
	import { Button } from '$lib/components/ui/button';
	import type { FileMeta } from '../../types';

	let {
		file,
		readonly = false,
		onDetach = () => undefined
	}: {
		file: FileMeta;
		readonly?: boolean;
		onDetach?: (file: FileMeta) => void;
	} = $props();
</script>

{#if readonly}
	<li class="truncate text-sm text-muted-foreground" title={file.filename}>
		{file.filename}
		<span class="ml-1 inline-block rounded px-1 py-0.5 text-xs {statusTone(file.ingestion_status)}">
			{file.ingestion_status ?? 'pending'}
		</span>
	</li>
{:else}
	<li class="group flex items-start justify-between gap-2">
		<div class="min-w-0 text-sm text-foreground">
			<div class="truncate" title={file.filename}>{file.filename}</div>
			<div class="flex items-center gap-1 text-xs text-muted-foreground">
				<span class="inline-block rounded px-1 py-0.5 {statusTone(file.ingestion_status)}">
					{file.ingestion_status ?? 'pending'}
				</span>
				<span>{Math.ceil(file.size_bytes / 1024)} KB</span>
			</div>
			{#if file.ingestion_error}
				<div class="text-xs text-destructive dark:text-red-300">{file.ingestion_error}</div>
			{/if}
		</div>
		<Button
			variant="ghost"
			size="xs"
			class="shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 hover:text-destructive dark:hover:text-red-300 focus-visible:opacity-100"
			title="Detach from this chat"
			data-testid={`lq-ai-detach-${file.id}`}
			onclick={() => onDetach(file)}
		>
			Detach
		</Button>
	</li>
{/if}
