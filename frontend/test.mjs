import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
const source = await readFile("src/app.js", "utf8");
for (const text of [
  "/auth/login", "/tickets", "PATCH", "/analytics", "/integrations/jira/import", "/users",
  "ticket-form", "filters", "id=\"prev\"", "id=\"next\"", "Prediction history",
  "sla_probability", "routing_confidence", "/feedback", "Accept recommendation", "Override team",
  "Human feedback", "Why the model chose this", "triage-v1.0"
]) assert.ok(source.includes(text), `Missing product flow: ${text}`);
console.log("frontend Stage 2 static contract checks passed");
