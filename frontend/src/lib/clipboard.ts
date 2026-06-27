/**
 * Copy text to the clipboard, falling back to a hidden textarea + execCommand
 * for non-secure contexts (e.g. plain HTTP) where navigator.clipboard is absent.
 */
export async function copyToClipboard(text: string): Promise<void> {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  try {
    const ok = document.execCommand("copy");
    if (!ok) throw new Error("copy command was rejected");
  } finally {
    document.body.removeChild(textarea);
  }
}
