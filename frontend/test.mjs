import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
const source = await readFile("src/app.js", "utf8");
for (const text of ["/auth/login", "/tickets", "PATCH", "/analytics", "/sla/alerts", "/integrations/jira/import", "/users", "ticket-form", "function ticketForm", "filters", "id=\"prev\"", "id=\"next\"", "Prediction history", "ML classification and forecasts", "Current age", "/decision", "overridden", "accepted", "Critical", "Current SLA policy status", "ML-predicted breach risk", "review_reasons", "setInterval"]) assert.ok(source.includes(text), `Missing product flow: ${text}`);
assert.ok(!source.includes("localStorage.token") && !source.includes("localStorage.role"), "Access tokens must not be restored from localStorage");
assert.ok(source.includes("&quot;") && source.includes("&#39;"), "HTML attributes must escape both quote types");
assert.ok(source.indexOf("login-page") < source.indexOf("api('/demo-info')"), "Login UI must render before loading optional demo details");
console.log("frontend static contract checks passed");
