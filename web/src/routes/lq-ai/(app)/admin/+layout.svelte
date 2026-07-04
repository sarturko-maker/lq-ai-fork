<script lang="ts">
	import { page } from '$app/stores';

	import { auth } from '$lib/lq-ai/auth/store';

	$: pathname = $page.url.pathname;

	// SETUP-3b fence gating (ADR-F061 D4): /admin/models is the gateway alias
	// editor — operator-only server-side, so the link hides for non-operators
	// (the page keeps its own guard; the server 403s regardless).
	$: navLinks = [
		{ href: '/lq-ai/admin/audit-log', label: 'Audit log' },
		{ href: '/lq-ai/admin/users', label: 'Users' },
		...($auth.user?.role === 'operator' ? [{ href: '/lq-ai/admin/models', label: 'Models' }] : []),
		{ href: '/lq-ai/admin/word-addin', label: 'Word add-in' },
		{ href: '/lq-ai/admin/intake-bridges', label: 'Intake bridges' },
		{ href: '/lq-ai/admin/developer', label: 'Developer Support' }
	];
</script>

<div class="admin-shell">
	<nav class="admin-nav" aria-label="Admin navigation">
		<ul class="admin-nav-list">
			{#each navLinks as link}
				<li>
					<a
						href={link.href}
						class="admin-nav-link"
						class:admin-nav-link--active={pathname.startsWith(link.href)}
						aria-current={pathname.startsWith(link.href) ? 'page' : undefined}
					>
						{link.label}
					</a>
				</li>
			{/each}
		</ul>
	</nav>
	<div class="admin-content">
		<slot />
	</div>
</div>

<style>
	.admin-shell {
		display: flex;
		flex-direction: column;
		gap: 0;
		width: 100%;
		min-height: 0;
	}

	/* F2-M8: color --lq-* → semantic + F013 calm. Horizontal tab strip keeps the
	   underline idiom but inks the active marker (--foreground), not the old teal
	   accent; scarce blue is reserved for focus (--ring). */
	.admin-nav {
		border-bottom: 1px solid var(--border);
		background: var(--background);
	}

	.admin-nav-list {
		list-style: none;
		margin: 0;
		padding: 0 var(--lq-space-5);
		display: flex;
		gap: 0;
	}

	.admin-nav-link {
		display: block;
		padding: var(--lq-space-3) var(--lq-space-4);
		color: var(--muted-foreground);
		text-decoration: none;
		font-size: 14px;
		font-weight: 500;
		border-bottom: 2px solid transparent;
		margin-bottom: -1px;
		transition:
			color 0.12s,
			border-color 0.12s;
	}

	.admin-nav-link:hover {
		color: var(--foreground);
	}

	.admin-nav-link:focus-visible {
		outline: 2px solid var(--ring);
		outline-offset: -2px;
	}

	.admin-nav-link--active {
		color: var(--foreground);
		border-bottom-color: var(--foreground);
	}

	.admin-content {
		flex: 1;
		min-width: 0;
	}
</style>
