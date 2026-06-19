<script lang="ts">
	/**
	 * One node in the data-flow graph (PRIV-6c) — a custom @xyflow/svelte node so
	 * the look stays LQ.AI F013 (charcoal card, scarce kind-accent, our humanised
	 * badges), never the library's chrome. Renders by `data.kind`; the source/
	 * target handles let the lineage edges attach.
	 */
	import { Handle, Position, type NodeProps } from '@xyflow/svelte';

	import {
		controllerRoleLabel,
		dpaStatusLabel,
		lawfulBasisLabel,
		systemTypeLabel,
		vendorRoleLabel
	} from './format';

	let { data }: NodeProps = $props();

	const kind = $derived(String(data.kind ?? ''));
	const label = $derived(String(data.label ?? ''));

	const KIND_LABEL: Record<string, string> = {
		system: 'System',
		activity: 'Activity',
		recipient: 'Recipient',
		destination: 'Third country'
	};

	// The compact detail line under the name, humanised per kind (categorical only).
	const detail = $derived.by(() => {
		if (kind === 'system') {
			const t = systemTypeLabel(data.system_type as string | null | undefined);
			return data.ai_usage ? `${t} · Uses AI` : t;
		}
		if (kind === 'activity') {
			const b = lawfulBasisLabel(data.lawful_basis as string | null | undefined);
			const role = controllerRoleLabel(data.controller_role as string | null | undefined);
			return data.special_category ? `${b} · ${role} · Special category` : `${b} · ${role}`;
		}
		if (kind === 'recipient') {
			const role = vendorRoleLabel(data.vendor_role as string | null | undefined);
			return `${role} · DPA ${dpaStatusLabel(data.dpa_status as string | null | undefined)}`;
		}
		return 'Cross-border transfer destination';
	});
</script>

<!-- Incoming edges attach left; outgoing edges leave right. -->
<Handle type="target" position={Position.Left} />
<div class="lqf-node lqf-node-{kind}">
	<div class="lqf-node-kind">{KIND_LABEL[kind] ?? kind}</div>
	<div class="lqf-node-label" title={label}>{label}</div>
	<div class="lqf-node-detail">{detail}</div>
</div>
<Handle type="source" position={Position.Right} />

<style>
	.lqf-node {
		width: 13rem;
		border-radius: 0.5rem;
		border: 1px solid var(--border);
		border-left-width: 3px;
		background: var(--card, var(--background));
		padding: 0.5rem 0.75rem;
	}
	.lqf-node-kind {
		font-size: 0.625rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--muted-foreground);
	}
	.lqf-node-label {
		margin-top: 0.125rem;
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--foreground);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.lqf-node-detail {
		margin-top: 0.125rem;
		font-size: 0.75rem;
		color: var(--muted-foreground);
	}
	/* Scarce kind-accent on the left border — calm, uses theme tokens only. */
	.lqf-node-system {
		border-left-color: var(--brand);
	}
	.lqf-node-activity {
		border-left-color: var(--foreground);
	}
	.lqf-node-recipient {
		border-left-color: var(--muted-foreground);
	}
	.lqf-node-destination {
		border-left-color: var(--destructive);
	}
</style>
