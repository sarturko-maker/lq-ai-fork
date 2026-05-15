<script lang="ts">
  import { onMount } from 'svelte';
  import { listUsers, patchUserRole } from '../api/admin';
  import { LQAIApiError } from '../api/client';
  import type { AdminUserRow, AdminUserListQuery, UserRole } from '../types';

  let users: AdminUserRow[] = [];
  let totalCount = 0;
  let limit = 50;
  let offset = 0;

  let loading = true;
  let fetchError = '';

  let roleFilter: UserRole | '' = '';
  let emailQuery = '';

  let inlineError = '';

  function formatRelativeDate(isoDate: string | null | undefined): string {
    if (!isoDate) return 'never';
    const d = new Date(isoDate);
    const diffMs = Date.now() - d.getTime();
    const diffDays = Math.floor(diffMs / 86400000);
    if (diffDays === 0) return 'today';
    if (diffDays === 1) return 'yesterday';
    if (diffDays < 30) return `${diffDays}d ago`;
    const diffMonths = Math.floor(diffDays / 30);
    if (diffMonths < 12) return `${diffMonths}mo ago`;
    return `${Math.floor(diffMonths / 12)}y ago`;
  }

  async function fetchUsers() {
    loading = true;
    fetchError = '';
    try {
      const query: AdminUserListQuery = { limit, offset };
      if (roleFilter) query.role = roleFilter;
      if (emailQuery.trim()) query.email_q = emailQuery.trim();
      const resp = await listUsers(query);
      users = resp.users;
      totalCount = resp.total_count;
    } catch (err) {
      fetchError = err instanceof Error ? err.message : 'Failed to load users.';
    } finally {
      loading = false;
    }
  }

  async function handleRoleChange(userId: string, newRole: UserRole) {
    inlineError = '';
    try {
      const updated = await patchUserRole(userId, newRole);
      users = users.map((u) => (u.id === userId ? { ...u, role: updated.role } : u));
    } catch (err) {
      if (err instanceof LQAIApiError && err.status === 409) {
        inlineError = "Can't demote the last admin. Promote another user first.";
      } else {
        inlineError = err instanceof Error ? err.message : 'Failed to update role.';
      }
    }
  }

  function prevPage() {
    if (offset > 0) {
      offset = Math.max(0, offset - limit);
      fetchUsers();
    }
  }

  function nextPage() {
    if (offset + limit < totalCount) {
      offset += limit;
      fetchUsers();
    }
  }

  function applyFilters() {
    offset = 0;
    fetchUsers();
  }

  onMount(fetchUsers);
</script>

<div class="dev-card">
  <h2 class="dev-card-title">Role management</h2>

  <div class="filters">
    <select
      class="filter-select"
      bind:value={roleFilter}
      on:change={applyFilters}
      aria-label="Filter by role"
    >
      <option value="">All roles</option>
      <option value="admin">admin</option>
      <option value="member">member</option>
      <option value="viewer">viewer</option>
    </select>
    <input
      type="text"
      class="filter-input"
      placeholder="Search email..."
      bind:value={emailQuery}
      on:input={applyFilters}
      aria-label="Filter by email"
    />
  </div>

  {#if inlineError}
    <div class="inline-error" role="alert">{inlineError}</div>
  {/if}

  {#if loading}
    <p class="state-msg">Loading users…</p>
  {:else if fetchError}
    <p class="state-msg state-msg--error">{fetchError}</p>
  {:else if users.length === 0}
    <p class="state-msg">No users found.</p>
  {:else}
    <div class="table-wrap">
      <table class="users-table">
        <thead>
          <tr>
            <th>Email</th>
            <th>Role</th>
            <th>Last login</th>
            <th>Deletion</th>
          </tr>
        </thead>
        <tbody>
          {#each users as user (user.id)}
            <tr>
              <td class="email-cell" title={user.email}>{user.email}</td>
              <td>
                <select
                  class="role-select"
                  value={user.role}
                  on:change={(e) => handleRoleChange(user.id, (e.target as HTMLSelectElement).value as UserRole)}
                  aria-label={`Role for ${user.email}`}
                >
                  <option value="admin">admin</option>
                  <option value="member">member</option>
                  <option value="viewer">viewer</option>
                </select>
              </td>
              <td class="secondary-cell">{formatRelativeDate(user.last_login_at)}</td>
              <td>
                {#if user.deletion_scheduled_at}
                  <span class="deletion-pill">Scheduled</span>
                {/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    <div class="pagination">
      <span class="pagination-info">Showing {offset + 1}–{Math.min(offset + limit, totalCount)} of {totalCount}</span>
      <div class="pagination-btns">
        <button class="page-btn" on:click={prevPage} disabled={offset === 0}>Prev</button>
        <button class="page-btn" on:click={nextPage} disabled={offset + limit >= totalCount}>Next</button>
      </div>
    </div>
  {/if}
</div>

<style>
  .dev-card {
    background: var(--lq-surface);
    border: 1px solid var(--lq-border);
    border-radius: var(--lq-radius);
    padding: var(--lq-space-5);
  }

  .dev-card-title {
    font-size: 15px;
    font-weight: 600;
    color: var(--lq-text);
    margin: 0 0 var(--lq-space-4);
  }

  .filters {
    display: flex;
    gap: var(--lq-space-3);
    margin-bottom: var(--lq-space-4);
    flex-wrap: wrap;
  }

  .filter-select,
  .filter-input {
    padding: var(--lq-space-2) var(--lq-space-3);
    border: 1px solid var(--lq-border);
    border-radius: var(--lq-radius-sm);
    background: var(--lq-surface);
    color: var(--lq-text);
    font-size: 13px;
  }

  .filter-input {
    flex: 1;
    min-width: 160px;
  }

  .inline-error {
    background: var(--lq-error-soft);
    border: 1px solid var(--lq-error-border);
    color: var(--lq-error);
    border-radius: var(--lq-radius-sm);
    padding: var(--lq-space-2) var(--lq-space-3);
    font-size: 13px;
    margin-bottom: var(--lq-space-3);
  }

  .state-msg {
    font-size: 14px;
    color: var(--lq-text-secondary);
    margin: 0;
  }

  .state-msg--error {
    color: var(--lq-error);
  }

  .table-wrap {
    overflow-x: auto;
    margin-bottom: var(--lq-space-4);
  }

  .users-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }

  .users-table th {
    text-align: left;
    font-weight: 600;
    color: var(--lq-text-secondary);
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    padding: var(--lq-space-2) var(--lq-space-3);
    border-bottom: 1px solid var(--lq-border);
    white-space: nowrap;
  }

  .users-table td {
    padding: var(--lq-space-2) var(--lq-space-3);
    border-bottom: 1px solid var(--lq-border);
    vertical-align: middle;
  }

  .email-cell {
    max-width: 200px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .secondary-cell {
    color: var(--lq-text-secondary);
  }

  .role-select {
    padding: 2px var(--lq-space-2);
    border: 1px solid var(--lq-border);
    border-radius: var(--lq-radius-sm);
    background: var(--lq-surface);
    color: var(--lq-text);
    font-size: 13px;
    cursor: pointer;
  }

  .deletion-pill {
    display: inline-block;
    padding: 2px 8px;
    background: var(--lq-warn-soft);
    color: var(--lq-warn);
    border: 1px solid var(--lq-warn-border);
    border-radius: var(--lq-radius-pill);
    font-size: 11px;
    font-weight: 500;
  }

  .pagination {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: var(--lq-space-2);
  }

  .pagination-info {
    font-size: 12px;
    color: var(--lq-text-secondary);
  }

  .pagination-btns {
    display: flex;
    gap: var(--lq-space-2);
  }

  .page-btn {
    padding: var(--lq-space-1) var(--lq-space-3);
    border: 1px solid var(--lq-border);
    border-radius: var(--lq-radius-sm);
    background: var(--lq-surface);
    color: var(--lq-text);
    font-size: 13px;
    cursor: pointer;
    transition: background 0.12s;
  }

  .page-btn:hover:not(:disabled) {
    background: var(--lq-inset);
  }

  .page-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
</style>
