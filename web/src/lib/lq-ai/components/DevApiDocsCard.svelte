<script lang="ts">
  // V2-FALLBACK — URLs are hardcoded for Wave B v2.
  // A future /api/v1/admin/developer/openapi-urls endpoint will derive these
  // from operator config (deploy-time host/port overrides).
  const backendBase = 'http://localhost:8000';
  const gatewayBase = 'http://localhost:8001';

  const links = [
    { label: 'Swagger UI (backend)', href: `${backendBase}/docs`, desc: 'Interactive API explorer for the LQ.AI backend.' },
    { label: 'ReDoc (backend)', href: `${backendBase}/redoc`, desc: 'Read-only reference for the backend OpenAPI spec.' },
    { label: 'Swagger UI (gateway)', href: `${gatewayBase}/docs`, desc: 'Interactive API explorer for the Inference Gateway.' },
    { label: 'OpenAPI JSON', href: `${backendBase}/openapi.json`, desc: 'Machine-readable schema — import into Postman, Insomnia, etc.' }
  ];

  const metricsLinks = [
    { label: 'Backend /metrics', href: `${backendBase}/metrics` },
    { label: 'Gateway /metrics', href: `${gatewayBase}/metrics` }
  ];
</script>

<div class="dev-card">
  <h2 class="dev-card-title">API documentation</h2>
  <ul class="doc-links">
    {#each links as link}
      <li class="doc-link-item">
        <a href={link.href} target="_blank" rel="noopener noreferrer" class="doc-link">{link.label}</a>
        <span class="doc-link-desc">{link.desc}</span>
      </li>
    {/each}
  </ul>
  <div class="metrics-section">
    <p class="metrics-label">Prometheus metrics</p>
    <ul class="metrics-links">
      {#each metricsLinks as m}
        <li><a href={m.href} target="_blank" rel="noopener noreferrer" class="doc-link">{m.label}</a></li>
      {/each}
    </ul>
    <p class="metrics-caption">Operator may need to expose these ports outside Docker.</p>
  </div>
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

  .doc-links {
    list-style: none;
    margin: 0 0 var(--lq-space-4);
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--lq-space-3);
  }

  .doc-link-item {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .doc-link {
    color: var(--lq-accent);
    text-decoration: none;
    font-size: 14px;
    font-weight: 500;
  }

  .doc-link:hover {
    text-decoration: underline;
  }

  .doc-link-desc {
    font-size: 12px;
    color: var(--lq-text-secondary);
  }

  .metrics-section {
    border-top: 1px solid var(--lq-border);
    padding-top: var(--lq-space-3);
  }

  .metrics-label {
    font-size: 12px;
    font-weight: 600;
    color: var(--lq-text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin: 0 0 var(--lq-space-2);
  }

  .metrics-links {
    list-style: none;
    margin: 0 0 var(--lq-space-2);
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--lq-space-1);
  }

  .metrics-caption {
    font-size: 12px;
    color: var(--lq-text-secondary);
    margin: 0;
  }
</style>
