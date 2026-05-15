<script lang="ts">
	type TabId = 'use' | 'source' | 'try' | 'versions';

	export let activeTab: TabId = 'use';
	export let onTabChange: (tab: TabId) => void;

	const tabs: { id: TabId; label: string }[] = [
		{ id: 'use', label: 'Use it' },
		{ id: 'source', label: 'View source' },
		{ id: 'try', label: 'Try it' },
		{ id: 'versions', label: 'Versions' }
	];
</script>

<nav role="tablist" aria-label="Skill detail tabs" class="lq-skill-tabs">
	{#each tabs as t (t.id)}
		<button
			role="tab"
			type="button"
			aria-selected={activeTab === t.id}
			class:active={activeTab === t.id}
			on:click={() => onTabChange(t.id)}
		>{t.label}</button>
	{/each}
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
	.lq-skill-tabs button:focus-visible {
		outline: 2px solid var(--lq-accent);
		outline-offset: 2px;
	}
</style>
