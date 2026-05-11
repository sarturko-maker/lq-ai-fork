<script lang="ts">
  import { onMount } from 'svelte';
  import { auth } from '$lib/lq-ai/auth/store';
  import {
    isPasswordRotated,
    hasRunSkill,
    hasTriedEnhance,
    hasAttachedKnowledge,
    hasSavedSkill
  } from '$lib/lq-ai/getting-started-signals';

  interface ChecklistItem {
    label: string;
    done: boolean;
    cta: string;
    href: string;
  }

  let items: ChecklistItem[] = [
    { label: 'Log in & rotate password', done: false, cta: 'Change password →', href: '/lq-ai/change-password' },
    { label: 'Run a skill on a document', done: false, cta: 'Open chats →', href: '/lq-ai/chats' },
    { label: 'Try Enhance Prompt', done: false, cta: 'Open chats →', href: '/lq-ai/chats' },
    { label: 'Attach a knowledge base', done: false, cta: 'Browse knowledge →', href: '/lq-ai/knowledge' },
    { label: 'Save a prompt as a skill', done: false, cta: 'Skill Creator →', href: '/lq-ai/skills/new' }
  ];

  $: allDone = items.every((i) => i.done);

  onMount(async () => {
    const user = $auth.user;
    const savedSkill = await hasSavedSkill();

    items = [
      { ...items[0], done: isPasswordRotated(user) },
      { ...items[1], done: hasRunSkill() },
      { ...items[2], done: hasTriedEnhance() },
      { ...items[3], done: hasAttachedKnowledge() },
      { ...items[4], done: savedSkill }
    ];
  });
</script>

{#if !allDone}
  <section style="margin-bottom: var(--lq-space-6);">
    <p class="lq-text-label" style="margin-bottom: var(--lq-space-3);">Getting started</p>
    <div class="checklist">
      {#each items as item, i (i)}
        <div class="checklist-row" class:done={item.done}>
          <span class="check-icon" aria-hidden="true">{item.done ? '✓' : '○'}</span>
          <span class="item-label lq-text-body" class:strikethrough={item.done}>{item.label}</span>
          {#if !item.done}
            <a href={item.href} class="item-cta lq-text-body-sm">{item.cta}</a>
          {/if}
        </div>
      {/each}
    </div>
  </section>
{/if}

<style>
  .checklist {
    border: 1px solid var(--lq-border);
    border-radius: var(--lq-radius-lg);
    background: var(--lq-canvas);
    overflow: hidden;
  }

  .checklist-row {
    display: flex;
    align-items: center;
    gap: var(--lq-space-3);
    padding: var(--lq-space-3) var(--lq-space-4);
    border-bottom: 1px solid var(--lq-border);
  }
  .checklist-row:last-child { border-bottom: none; }
  .checklist-row.done { background: var(--lq-inset); }

  .check-icon {
    font-size: 14px;
    width: 18px;
    text-align: center;
    flex-shrink: 0;
    color: var(--lq-accent);
  }
  .checklist-row:not(.done) .check-icon { color: var(--lq-text-tertiary); }

  .item-label { flex: 1; }
  .strikethrough { text-decoration: line-through; color: var(--lq-text-tertiary); }

  .item-cta {
    color: var(--lq-accent);
    text-decoration: none;
    flex-shrink: 0;
  }
  .item-cta:hover { text-decoration: underline; }
</style>
