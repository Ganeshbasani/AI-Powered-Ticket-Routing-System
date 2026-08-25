import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
const source = await readFile("src/app.js", "utf8");
for (const text of ["/auth/login", "/tickets", "PATCH", "/analytics", "/integrations/jira/import", "/users", "ticket-form", "filters", "id=\"prev\"", "id=\"next\"", "Prediction history", "ML Model Status: Prototype"]) assert.ok(source.includes(text), `Missing product flow: ${text}`);
console.log("frontend static contract checks passed");
