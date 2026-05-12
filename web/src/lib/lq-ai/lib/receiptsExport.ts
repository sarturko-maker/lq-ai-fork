/**
 * Triggers a browser download of JSONL text under the given filename.
 * Wraps the URL.createObjectURL + anchor-click + revoke pattern.
 */
export function triggerJsonlDownload(jsonl: string, filename: string): void {
  const blob = new Blob([jsonl], { type: 'application/jsonl' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * Sanity-check that a string looks like JSONL — every non-empty line
 * parses as JSON. Returns `{valid: true}` on success, `{valid: false,
 * error}` on the first parse failure. Used by the export-button
 * confirmation flow.
 */
export function isValidJsonl(text: string): { valid: boolean; error?: string } {
  const lines = text.split('\n').filter(l => l.trim());
  if (lines.length === 0) return { valid: false, error: 'Empty JSONL payload' };
  for (let i = 0; i < lines.length; i++) {
    try {
      JSON.parse(lines[i]);
    } catch {
      return { valid: false, error: `Line ${i + 1} is not valid JSON` };
    }
  }
  return { valid: true };
}
