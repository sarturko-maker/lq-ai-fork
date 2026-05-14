<script lang="ts">
  /**
   * MessageOverflowMenu — generic ⋯ menu rendered on assistant message
   * footers (Wave D.2 Task 5.3). Composable by intent: callers pass in an
   * `onCapture` handler and toggle `captureInOverflow` to surface (or omit)
   * the "Capture as skill" item depending on whether the inline 📝 button
   * is already showing in the parent's action row. Copy markdown / Retry
   * are placeholders for later waves and stay disabled here.
   *
   * Notes for reviewers:
   *   - Scoped style block uses the same token vocabulary as
   *     `CaptureSkillModal.svelte` / `AttachKBModal.svelte`. There is NO
   *     `--lq-surface-tinted` token; hover uses `--lq-inset` (the
   *     subtle-surface neutral) which already shipped in `practice.css`.
   *   - Close-on-blur uses a microtask defer (requestAnimationFrame) so a
   *     click on a menu item registers BEFORE the focusout handler tears
   *     the menu down — the naive `e.relatedTarget` check fires before the
   *     button receives focus on some browsers and swallows the click.
   *   - data-testid hooks anchor Cypress (Wave 8): `lq-ai-message-overflow-trigger`
   *     and `lq-ai-message-overflow-capture`.
   */
  import { tick } from 'svelte';

  export let onCapture: () => void;
  export let captureInOverflow = false;

  let open = false;
  let rootEl: HTMLDivElement;

  function toggle(): void {
    open = !open;
  }

  /**
   * On focusout we defer a frame: clicking a menu button briefly removes
   * focus from the previously focused element BEFORE the new focus target
   * registers, so `relatedTarget` can be `null` even when the click landed
   * inside the menu. Re-checking `document.activeElement` after the next
   * paint avoids the false-positive close. Falls back to immediate close
   * when focus genuinely left the menu.
   */
  async function handleFocusout(): Promise<void> {
    await tick();
    requestAnimationFrame(() => {
      if (!rootEl) return;
      if (!rootEl.contains(document.activeElement)) {
        open = false;
      }
    });
  }

  function handleCapture(): void {
    open = false;
    onCapture();
  }
</script>

<!-- svelte-ignore a11y-no-static-element-interactions -->
<div class="overflow" bind:this={rootEl} on:focusout={handleFocusout}>
  <button
    type="button"
    class="trigger"
    aria-label="More actions"
    aria-haspopup="menu"
    aria-expanded={open}
    data-testid="lq-ai-message-overflow-trigger"
    on:click={toggle}
  >⋯</button>
  {#if open}
    <ul class="menu" role="menu">
      {#if captureInOverflow}
        <li role="none">
          <button
            type="button"
            role="menuitem"
            data-testid="lq-ai-message-overflow-capture"
            on:click={handleCapture}
          >📝 Capture as skill</button>
        </li>
      {/if}
      <li role="none">
        <button type="button" role="menuitem" disabled>Copy markdown</button>
      </li>
      <li role="none">
        <button type="button" role="menuitem" disabled>Retry</button>
      </li>
    </ul>
  {/if}
</div>

<style>
  @import '$lib/lq-ai/styles/practice.css';

  .overflow {
    position: relative;
    display: inline-block;
  }

  .trigger {
    background: transparent;
    border: 0;
    padding: 4px 8px;
    cursor: pointer;
    color: var(--lq-text-tertiary, #9ca3af);
    font-size: 16px;
    line-height: 1;
    border-radius: var(--lq-radius-sm, 4px);
  }

  .trigger:hover {
    background: var(--lq-inset, #fafbfa);
    color: var(--lq-text-secondary, #6b7280);
  }

  .menu {
    list-style: none;
    padding: 4px 0;
    margin: 0;
    position: absolute;
    right: 0;
    top: 100%;
    background: var(--lq-canvas, #ffffff);
    border: 1px solid var(--lq-border, #e5e7eb);
    border-radius: var(--lq-radius, 6px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
    min-width: 180px;
    z-index: 10;
  }

  .menu button {
    width: 100%;
    text-align: left;
    padding: 6px 12px;
    background: transparent;
    border: 0;
    font-size: 14px;
    cursor: pointer;
    color: inherit;
    font-family: inherit;
  }

  .menu button:hover:not(:disabled) {
    background: var(--lq-inset, #fafbfa);
  }

  .menu button:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
</style>
