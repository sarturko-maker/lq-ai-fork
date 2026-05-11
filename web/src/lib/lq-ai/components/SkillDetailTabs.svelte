<script lang="ts">
	export let activeTab: 'use' | 'source' = 'use';
	export let onTabChange: (tab: 'use' | 'source') => void;
</script>

<nav role="tablist" aria-label="Skill detail tabs" class="lq-skill-tabs">
	<button
		role="tab"
		type="button"
		aria-selected={activeTab === 'use'}
		class:active={activeTab === 'use'}
		on:click={() => onTabChange('use')}
	>Use it</button>
	<button
		role="tab"
		type="button"
		aria-selected={activeTab === 'source'}
		class:active={activeTab === 'source'}
		on:click={() => onTabChange('source')}
	>View source</button>
	<button role="tab" type="button" aria-disabled="true" disabled title="Wave D">Try it</button>
	<button role="tab" type="button" aria-disabled="true" disabled title="Wave D">Versions</button>
</nav>

<style>
	.lq-skill-tabs {
		display: flex;
		gap: var(--lq-space-4);
		border-bottom: 1px solid var(--lq-border);
		padding: 0 var(--lq-space-4);
	}
	.lq-skill-tabs button {
		background: transparent;
		border: 0;
		padding: var(--lq-space-3) var(--lq-space-1);
		color: var(--lq-text-secondary);
		cursor: pointer;
		border-bottom: 2px solid transparent;
		font-size: 14px;
		font-weight: 500;
	}
	.lq-skill-tabs button.active {
		color: var(--lq-accent);
		border-bottom-color: var(--lq-accent);
	}
	.lq-skill-tabs button[disabled] {
		color: var(--lq-text-tertiary);
		cursor: not-allowed;
	}
	.lq-skill-tabs button:focus-visible {
		outline: 2px solid var(--lq-accent);
		outline-offset: 2px;
	}
</style>
