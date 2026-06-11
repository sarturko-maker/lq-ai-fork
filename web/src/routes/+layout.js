// SPA mode: the shell ships as a static bundle (adapter-static fallback)
// and the auth store reads localStorage — render client-side only.
export const ssr = false;
export const trailingSlash = 'ignore';
