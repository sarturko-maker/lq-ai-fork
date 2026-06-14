// AE identity from Svelte AI Elements (SikandarJODD/ai-elements), MIT — ADR-F011.
// See ../README.md for provenance + the token-remap convention.
//
// AE3: the `sources` block. `Sources` is an OPTION-2 hand-build on native
// `<details>` (the upstream Collapsible-based trigger/content trio collapsed
// into one component — we don't ship `collapsible`); `Source` is vendored
// faithfully (an href-optional book-icon entry).
import Sources from './sources.svelte';
import Source from './source.svelte';

export { Sources, Source };
