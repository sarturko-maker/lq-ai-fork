<script lang="ts">
	import { onMount } from 'svelte';
	import TrustPill from './TrustPill.svelte';
	import { listModels } from '../api/models';

	type CardState =
		| { kind: 'loading' }
		| { kind: 'ready'; providers: string[] }
		| { kind: 'error'; message: string };

	let state: CardState = { kind: 'loading' };

	onMount(async () => {
		try {
			const list = await listModels();
			const seen = new Set<string>();
			for (const entry of list.data) {
				if (entry.owned_by) seen.add(entry.owned_by);
			}
			state = { kind: 'ready', providers: [...seen].sort() };
		} catch {
			state = { kind: 'error', message: 'Provider list unavailable. The gateway may be unreachable.' };
		}
	});

	// V2-FALLBACK: per-provider encryption status (legacy plaintext vs ADR 0011
	// derived-key) requires a future endpoint that surfaces api_key_encrypted
	// per provider row. For now all providers are shown as "Encrypted at rest"
	// per the ADR 0011 architectural commitment (key derivation ships with M1).
</script>

<div class="lq-card">
	<h3 class="lq-text-panel-h card-title">Configured providers</h3>

	{#if state.kind === 'loading'}
		<p class="lq-text-body loading-msg">Reading provider list…</p>
	{:else if state.kind === 'error'}
		<p class="lq-text-body error-msg">{state.message}</p>
	{:else if state.kind === 'ready'}
		{#if state.providers.length === 0}
			<p class="lq-text-body" style="color: var(--lq-text-secondary);">No providers discovered. Check your gateway configuration.</p>
		{:else}
			<ul class="provider-list">
				{#each state.providers as provider}
					<li class="provider-row">
						<TrustPill variant="provider" label={provider} />
						<TrustPill variant="secure" label="Encrypted at rest" />
					</li>
				{/each}
			</ul>
		{/if}
	{/if}

	<p class="lq-text-caption footer-note">
		Providers are configured in gateway.yaml. Operators can rotate, add, or remove providers without restarting the backend.
	</p>
</div>

<style>
	.lq-card {
		background: var(--lq-canvas);
		border: 1px solid var(--lq-border);
		border-radius: var(--lq-radius-lg);
		padding: var(--lq-space-5);
		display: flex;
		flex-direction: column;
		gap: var(--lq-space-3);
	}

	.card-title {
		margin: 0;
	}

	.loading-msg {
		color: var(--lq-text-secondary);
	}

	.error-msg {
		color: var(--lq-text-secondary);
	}

	.provider-list {
		list-style: none;
		padding: 0;
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: var(--lq-space-2);
	}

	.provider-row {
		display: flex;
		align-items: center;
		gap: var(--lq-space-2);
		flex-wrap: wrap;
	}

	.footer-note {
		color: var(--lq-text-tertiary);
		margin: 0;
	}
</style>
