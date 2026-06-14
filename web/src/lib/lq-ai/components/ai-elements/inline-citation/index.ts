// AE identity from Svelte AI Elements (SikandarJODD/ai-elements), MIT — ADR-F011.
// See ../README.md for provenance + the token-remap convention.
//
// AE3: only the two dependency-free presentational primitives this slice needs
// are vendored (each needs just `cn`) — `inline-citation-source` (the document
// name/meta block) and `inline-citation-quote` (the cited passage). The rest of
// the upstream `inline-citation` block (the hover-card `Card` + embla `Carousel`
// + the `inline-citation`/`-text` prose-wrappers) is SKIPPED: the heavy pieces
// pull `hover-card` + `carousel` registry deps we don't ship, and our static
// Sources card is not a hover carousel (ADR-F011 option-2 + AE0 "take only what
// you need").
import InlineCitationSource from './inline-citation-source.svelte';
import InlineCitationQuote from './inline-citation-quote.svelte';

export { InlineCitationSource, InlineCitationQuote };
