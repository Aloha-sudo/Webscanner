/** Copy text even when Clipboard API is unavailable on a plain HTTP page. */
export async function copyText(value: string): Promise<void> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return;
    }
  } catch {
    // Fall back when the browser denies the asynchronous clipboard API.
  }
  const focused = document.activeElement as HTMLElement | null;
  const field = document.createElement('textarea');
  field.value = value;
  field.setAttribute('readonly', '');
  field.style.position = 'fixed';
  field.style.left = '-9999px';
  document.body.appendChild(field);
  try {
    field.select();
    if (!document.execCommand('copy')) throw new Error('Copy failed');
  } finally {
    field.remove();
    focused?.focus?.({ preventScroll: true });
  }
}
