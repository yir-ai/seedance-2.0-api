// Generate one Seedance 2.0 clip through Yir and save it to ./output.
// Usage: YIR_API_KEY=... node examples/generate.mjs "a prompt" [name=value ...] [--image URL ...]
// Example: node examples/generate.mjs "A bike courier in an orange rain jacket weaves through rainy neon traffic at night, handheld follow camera, rain and city sounds." resolution=480p duration=4 aspect_ratio=16:9 generate_audio=true
// --image URLs fill these roles in order: first_frame, last_frame (Image-to-video).
import { mkdir, writeFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import { createNodeYirClient, DEFAULT_USER_AGENT } from "@yir-ai/sdk/server";

const MODEL = "bytedance/seedance-2.0";
// Sent unless overridden on the command line; the README lists every parameter.
const PARAMETERS = {"resolution":"480p","duration":4,"aspect_ratio":"16:9","generate_audio":true};
const TYPES = {"duration":"integer","resolution":"string","aspect_ratio":"string","return_last_frame":"boolean","generate_audio":"boolean","n":"integer"};
const IMAGE_ROLES = ["first_frame","last_frame"];

const [prompt = "A bike courier in an orange rain jacket weaves through rainy neon traffic at night, handheld follow camera, rain and city sounds.", ...rest] = process.argv.slice(2);
const parameters = { ...PARAMETERS };
const references = [];
for (let i = 0; i < rest.length; i++) {
  if (rest[i] === "--image") {
    references.push({ role: IMAGE_ROLES[Math.min(references.length, IMAGE_ROLES.length - 1)], url: rest[++i] });
    continue;
  }
  const [name, value] = rest[i].split("=");
  parameters[name] = TYPES[name] === "boolean" ? value === "true" : TYPES[name] === "integer" ? Number(value) : value;
}

const client = createNodeYirClient({ userAgent: `yir-gh/seedance-2.0-api ${DEFAULT_USER_AGENT}` });
const request = {
  model: MODEL,
  input: references.length ? { type: "image", prompt, references } : { type: "text", prompt },
  parameters,
};

const quote = await client.quoteVideo(request);
const estimate = quote.expected_amount;
console.log(`Estimated: ${estimate ? `$${estimate}` : "not available in advance"}${quote.official?.amount ? ` (official: $${quote.official.amount})` : ""}`);

// max_cost only guards against runaway charges (3x the estimate leaves room for a pricier fallback).
// You pay what the channel bills. The UUID is the idempotency key: retry with the same one and the job is never submitted twice.
const cap = estimate ? { max_cost: (Number(estimate) * 3).toFixed(2) } : {};
const job = await client.submitVideo({ ...request, ...cap }, randomUUID());
console.log(`Job ${job.id}`);
const done = await client.waitForJob(job.id);

await mkdir("output", { recursive: true });
for (const [i, file] of done.result.files.entries()) {
  const path = `output/${job.id}-${i}.${file.media_type.split("/")[1]}`;
  await writeFile(path, Buffer.from(await (await fetch(file.url)).arrayBuffer()));
  console.log(`Saved ${path}`);
}
console.log(`Charged: $${done.billing?.total_charged_by_yir} via ${done.final_provider}`);
