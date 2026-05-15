<script lang="ts">
	export let label: string;
	export let description: string;
	export let value: string;
	export let options: { value: string; label: string; description?: string }[];
	export let onChange: (v: string) => void;

	$: name = label.replace(/\s+/g, '-').toLowerCase();
</script>

<fieldset class="stg-fieldset">
	<legend class="lq-text-panel-h stg-legend">{label}</legend>
	{#if description}
		<p class="lq-text-caption stg-desc">{description}</p>
	{/if}
	<div class="stg-options">
		{#each options as opt}
			<label class="stg-option" class:stg-option--selected={value === opt.value}>
				<input
					type="radio"
					{name}
					value={opt.value}
					checked={value === opt.value}
					on:change={() => onChange(opt.value)}
					class="stg-radio"
				/>
				<span class="stg-option-body">
					<span class="lq-text-label stg-option-label">{opt.label}</span>
					{#if opt.description}
						<span class="lq-text-caption stg-option-desc">{opt.description}</span>
					{/if}
				</span>
			</label>
		{/each}
	</div>
</fieldset>

<style>
	.stg-fieldset {
		border: 1px solid var(--lq-border);
		border-radius: var(--lq-radius);
		padding: var(--lq-space-4);
		margin-bottom: var(--lq-space-5);
		background: var(--lq-canvas);
	}

	.stg-legend {
		padding: 0 var(--lq-space-2);
		color: var(--lq-text);
	}

	.stg-desc {
		color: var(--lq-text-secondary);
		margin: 0 0 var(--lq-space-3) 0;
	}

	.stg-options {
		display: flex;
		flex-direction: column;
		gap: var(--lq-space-2);
	}

	.stg-option {
		display: flex;
		align-items: flex-start;
		gap: var(--lq-space-3);
		padding: var(--lq-space-3);
		border: 1px solid var(--lq-border);
		border-radius: var(--lq-radius-sm);
		cursor: pointer;
		background: var(--lq-inset);
		transition: border-color 0.12s, background 0.12s;
	}

	.stg-option:hover {
		border-color: var(--lq-accent-border);
		background: var(--lq-accent-soft);
	}

	.stg-option--selected {
		border-color: var(--lq-accent);
		background: var(--lq-accent-soft);
	}

	.stg-radio {
		margin-top: 2px;
		accent-color: var(--lq-accent);
		flex-shrink: 0;
	}

	.stg-option-body {
		display: flex;
		flex-direction: column;
		gap: var(--lq-space-1);
	}

	.stg-option-label {
		color: var(--lq-text);
	}

	.stg-option-desc {
		color: var(--lq-text-secondary);
	}
</style>
