// HMAC-SHA256 of a Notion webhook body, keyed by the subscription's verification token.
// Notion sends the hex digest in `X-Notion-Signature` as `sha256=<hex>`. The bytes must be
// the raw request body: re-serializing the JSON changes the signature.
// https://developers.notion.com/reference/webhooks

export async function notionSignature(body: Uint8Array, verificationToken: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(verificationToken),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const mac = await crypto.subtle.sign("HMAC", key, body as BufferSource);
  const hex = [...new Uint8Array(mac)].map((b) => b.toString(16).padStart(2, "0")).join("");
  return `sha256=${hex}`;
}

export async function verifyNotionSignature(
  body: Uint8Array,
  signature: string | null,
  verificationToken: string,
): Promise<boolean> {
  if (!signature || !verificationToken) return false;
  const expected = await notionSignature(body, verificationToken);
  if (expected.length !== signature.length) return false;
  let diff = 0;
  for (let i = 0; i < expected.length; i++) diff |= expected.charCodeAt(i) ^ signature.charCodeAt(i);
  return diff === 0;
}

/** Constant-time string compare for the reconcile secret. A length mismatch fails closed. */
export function timingSafeEqualStr(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}
