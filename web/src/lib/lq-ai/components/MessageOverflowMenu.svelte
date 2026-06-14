<script lang="ts">
  /**
   * MessageOverflowMenu — generic ⋯ menu rendered on assistant message
   * footers (Wave D.2 Task 5.3). Composable by intent: callers pass in an
   * `onCapture` handler and toggle `captureInOverflow` to surface (or omit)
   * the "Capture as skill" item depending on whether the inline 📝 button
   * is already showing in the parent's action row.
   *
   * Trigger is hidden when no items would render — by default the inline
   * 📝 button covers the only currently-implemented action, so the overflow
   * trigger only appears when the user has demoted capture into the menu
   * (settings → "Show inline on AI messages" off). Copy markdown / Retry
   * are deferred to a future release and intentionally NOT rendered as
   * placeholder items — surfacing them as greyed-out controls reads as
   * broken UI rather than coming-soon. They land here when implemented.
   *
   * No unit tests — pure UI-state component; behavior covered by Wave 8
   * Cypress via the data-testids.
   *
   * A11y posture: this is a "disclosure widget" (expandable button group),
   * not a WAI-ARIA menu. The full menu pattern (arrow-key navigation,
   * roving tabindex, focus management) is deferred until Copy/Retry
   * placeholders wake up — track as a DE candidate. We keep `aria-expanded`
   * on the trigger because that correctly describes a disclosure.
   *
   * Notes for reviewers:
   *   - Styling (R8): migrated off the legacy `--lq-*` palette onto the
   *     shipped semantic tokens. The menu is a popover surface
   *     (`bg-popover`/`shadow-md`, matching SlashPopover); the trigger and
   *     items use `text-muted-foreground`/`hover:bg-muted`. No `<style>`
   *     block — utility classes only. Stays Svelte 4: the trigger keeps a
   *     `bind:this` to its DOM node for `.focus()` (the focusout/Escape
   *     focus dance below relies on real element refs).
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
  export let captureDisabled = false;

  let open = false;
  let rootEl: HTMLDivElement;
  let triggerEl: HTMLButtonElement;

  // Currently the only implemented item is Capture (gated by
  // `captureInOverflow`). When that's off too, the menu would only contain
  // future-release items, so we hide the trigger entirely rather than
  // present an empty / "broken" menu.
  $: hasItems = captureInOverflow;

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

  function handleKeydown(e: KeyboardEvent): void {
    if (open && e.key === 'Escape') {
      open = false;
      triggerEl?.focus();
    }
  }

  function handleCapture(): void {
    open = false;
    // Briefly restore focus to the trigger before the modal grabs it.
    // For future sync menuitems (Copy/Retry), focus correctly returns to
    // the trigger and no follow-up wiring is needed.
    triggerEl?.focus();
    onCapture();
  }
</script>

<svelte:window on:keydown={handleKeydown} />

{#if hasItems}
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div class="relative inline-block" bind:this={rootEl} on:focusout={handleFocusout}>
    <button
      type="button"
      class="rounded-sm px-2 py-1 text-base leading-none text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      aria-label="More actions"
      aria-expanded={open}
      data-testid="lq-ai-message-overflow-trigger"
      bind:this={triggerEl}
      on:click={toggle}
    >⋯</button>
    {#if open}
      <ul
        class="absolute right-0 top-full z-10 mt-1 min-w-[180px] list-none rounded-md border border-border bg-popover py-1 text-popover-foreground shadow-md"
      >
        {#if captureInOverflow}
          <li>
            <button
              type="button"
              class="w-full px-3 py-1.5 text-left text-sm transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40"
              disabled={captureDisabled}
              data-testid="lq-ai-message-overflow-capture"
              on:click={handleCapture}
            >📝 Capture as skill</button>
          </li>
        {/if}
      </ul>
    {/if}
  </div>
{/if}
