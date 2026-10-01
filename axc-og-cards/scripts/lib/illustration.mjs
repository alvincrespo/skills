// Requests one square illustration from OpenRouter's image API.
export async function generateIllustration({ post, apiKey, model, stylePrompt, params = {}, fetchImpl = fetch }) {
  const subject = [post.title, post.description].filter(Boolean).join(". ").slice(0, 400);
  const prompt = `${subject}\n\nStyle: ${stylePrompt}`;

  const response = await fetchImpl("https://openrouter.ai/api/v1/images", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    // Model-specific options override the defaults, but never the model or
    // the prompt.
    body: JSON.stringify({
      aspect_ratio: "1:1",
      output_format: "png",
      ...params,
      model,
      prompt,
    }),
  });

  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new Error(`OpenRouter image request failed for "${post.slug}": ${response.status} ${body}`);
  }

  const json = await response.json();
  const item = json?.data?.[0];
  if (!item?.b64_json) {
    throw new Error(`OpenRouter response for "${post.slug}" had no image data.`);
  }
  // A missing cost is reported to the caller (rather than thrown here) so the
  // already-generated, already-billed image and a ledger entry recording the
  // spend as unresolved both still get saved. Throwing here would discard
  // both and silently under-count real spend on the next run's budget check.
  const cost = json?.usage?.cost;
  const hasCost = typeof cost === "number" && !Number.isNaN(cost);

  return { buffer: Buffer.from(item.b64_json, "base64"), cost: hasCost ? cost : null };
}
