// Cypress support for the LQ.AI shell (post-F0-S6).
//
// The OpenWebUI bootstrap that lived here (cy.registerAdmin + the
// spec-name-pattern guard that exempted `f*-`/`wave-`/`m*-` specs) died with
// the husk: there is no OpenWebUI user table left to pollute, so fork specs
// no longer need a name prefix to dodge it. Shared helpers are plain imports
// from ./lq-ai-helpers.ts.
export {};
