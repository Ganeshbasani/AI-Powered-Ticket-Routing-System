"""Generate a realistic synthetic support-ticket dataset for local development.

This dataset is intentionally synthetic. It is useful for exercising the full
ML pipeline and evaluation workflow, but it must not be presented as evidence
of production performance.
"""

from __future__ import annotations

import csv
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "data" / "tickets.csv"

SEED = 2026
ROWS = 1500

ISSUE_PROFILES = {
    "Network": {
        "team": "L2-Network",
        "project": "Platform",
        "components": ["VPN", "WiFi", "Firewall", "DNS", "Load Balancer"],
        "subjects": [
            "VPN connection drops repeatedly",
            "Intermittent network connectivity",
            "DNS resolution failing for internal service",
            "Firewall blocks application traffic",
            "Load balancer health checks failing",
        ],
        "details": [
            "users cannot stay connected to the corporate network",
            "the service becomes unreachable every few minutes",
            "requests time out from the office network",
            "connections fail after authentication",
            "packets appear to be dropped intermittently",
        ],
    },
    "Application": {
        "team": "L2-Application",
        "project": "Customer Portal",
        "components": ["Checkout", "Authentication", "Notifications", "Search", "API"],
        "subjects": [
            "Checkout returns an error",
            "Application page shows a blank screen",
            "Notification jobs are delayed",
            "Search results fail to load",
            "API requests return HTTP 500",
        ],
        "details": [
            "the application worked yesterday but now fails for multiple users",
            "the same request succeeds after a retry",
            "the UI shows an unexpected error message",
            "logs contain repeated server errors",
            "customers are unable to complete the workflow",
        ],
    },
    "Database": {
        "team": "L3-Database",
        "project": "Data Services",
        "components": ["PostgreSQL", "MySQL", "Replication", "Backup", "Query Engine"],
        "subjects": [
            "Database queries are timing out",
            "Replication is lagging",
            "Database connection pool is exhausted",
            "Backup job failed overnight",
            "Reports are running much slower",
        ],
        "details": [
            "transactions are waiting longer than expected",
            "replica data is several minutes behind primary",
            "connections remain open after requests finish",
            "the scheduled backup did not complete successfully",
            "the issue is affecting reporting and analytics",
        ],
    },
    "Access": {
        "team": "Security",
        "project": "Identity",
        "components": ["SSO", "IAM", "MFA", "Permissions", "Password Reset"],
        "subjects": [
            "MFA challenge is failing",
            "User cannot access internal application",
            "Password reset link is invalid",
            "SSO login returns access denied",
            "Unexpected permission change detected",
        ],
        "details": [
            "the user receives an access denied response",
            "login works for other accounts but not this user",
            "the authentication flow stops before completion",
            "the account may have incorrect permissions",
            "the event should be reviewed for security impact",
        ],
    },
    "Hardware": {
        "team": "L1-Hardware",
        "project": "Workplace IT",
        "components": ["Laptop", "Monitor", "Keyboard", "Dock", "Printer"],
        "subjects": [
            "Laptop will not power on",
            "External monitor is not detected",
            "Keyboard stops responding",
            "Docking station disconnects",
            "Printer is unavailable",
        ],
        "details": [
            "the issue affects a single employee workstation",
            "restarting the device did not resolve the problem",
            "the peripheral is intermittently unavailable",
            "the device worked earlier in the day",
            "a replacement may be required if troubleshooting fails",
        ],
    },
}

PRIORITIES = ["Low", "Medium", "High"]
CHANNELS = ["Portal", "Email", "Jira", "Chat"]
CUSTOMER_TIERS = ["Standard", "Business", "Enterprise"]


def make_row(rng: random.Random, ticket_id: int) -> dict[str, object]:
    issue_type = rng.choice(list(ISSUE_PROFILES))
    profile = ISSUE_PROFILES[issue_type]
    priority = rng.choices(PRIORITIES, weights=[30, 45, 25], k=1)[0]
    component = rng.choice(profile["components"])
    subject = rng.choice(profile["subjects"])
    detail = rng.choice(profile["details"])
    extra = rng.choice([
        "The customer has already tried restarting the service.",
        "The problem is reproducible from the production environment.",
        "This started after a recent configuration change.",
        "The support team has attached the latest logs.",
        "The issue is currently affecting several users.",
    ])
    summary = subject
    description = f"{detail}. {extra}"

    # Keep ticket age varied but realistic for a support queue.
    created_hours = round(rng.uniform(0.2, 36.0), 2)

    # Add modest label noise so the benchmark is not trivially perfect.
    final_team = profile["team"]
    if rng.random() < 0.08:
        neighboring = {
            "Network": ["L2-Application", "L1-Hardware"],
            "Application": ["L1-General", "L2-Network"],
            "Database": ["L2-Application", "L1-General"],
            "Access": ["L1-General", "L2-Application"],
            "Hardware": ["L1-General", "L2-Network"],
        }
        final_team = rng.choice(neighboring[issue_type])

    # SLA breach is based on prediction-time conditions plus modest noise.
    customer_tier = rng.choice(CUSTOMER_TIERS)
    score = (
        {"Low": 0.0, "Medium": 0.8, "High": 1.8}[priority]
        + min(created_hours / 10.0, 2.8)
        + {"Network": 0.4, "Application": 0.7, "Database": 1.0, "Access": 0.9, "Hardware": 0.2}[issue_type]
        + {"Standard": 0.0, "Business": 0.2, "Enterprise": 0.4}[customer_tier]
    )
    breach = "Yes" if (score + rng.uniform(-0.8, 0.8)) >= 2.6 else "No"

    created_at = datetime.now(UTC) - timedelta(hours=rng.uniform(0, 720))
    return {
        "ticket_id": ticket_id,
        "summary": summary,
        "description": description,
        "priority": priority,
        "issue_type": issue_type,
        "project": profile["project"],
        "component": component,
        "customer_tier": customer_tier,
        "created_hours": created_hours,
        "channel": rng.choice(CHANNELS),
        "final_team": final_team,
        "sla_breach": breach,
        "created_timestamp": created_at.isoformat(),
    }


def main() -> None:
    rng = random.Random(SEED)
    rows = [make_row(rng, ticket_id) for ticket_id in range(1, ROWS + 1)]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Generated {len(rows):,} synthetic tickets at {OUTPUT}")


if __name__ == "__main__":
    main()
