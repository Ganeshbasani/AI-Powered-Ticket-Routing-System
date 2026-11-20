"""Opt-in recruiter demo account and sample tickets."""

from __future__ import annotations

from src.persistence.repository import TicketRepository


DEMO_TICKETS = [
    {
        "jira_issue_key": "DEMO-101", "summary": "VPN disconnects during customer calls",
        "description": "Remote support agent loses the secure connection several times an hour.",
        "priority": "High", "created_hours": 3.5, "assigned_team": "Network", "status": "open",
        "source": "demo", "actual_sla_breach": None,
    },
    {
        "jira_issue_key": "DEMO-102", "summary": "New starter needs access to the analytics portal",
        "description": "Provision read-only access for a new team member.",
        "priority": "Medium", "created_hours": 5, "assigned_team": "Identity", "status": "open",
        "source": "demo", "actual_sla_breach": None,
    },
    {
        "jira_issue_key": "DEMO-103", "summary": "Production checkout service returns errors",
        "description": "Several customers cannot complete purchases after the latest release.",
        "priority": "High", "created_hours": 7, "assigned_team": "Platform", "status": "in progress",
        "source": "demo", "actual_sla_breach": "Yes",
    },
    {
        "jira_issue_key": "DEMO-104", "summary": "Laptop camera is not detected",
        "description": "Camera is missing from meeting applications after a driver update.",
        "priority": "Low", "created_hours": 18, "assigned_team": "Workplace", "status": "open",
        "source": "demo", "actual_sla_breach": None,
    },
    {
        "jira_issue_key": "DEMO-105", "summary": "Email delivery is delayed for the finance team",
        "description": "Messages arrive in batches several minutes after sending.",
        "priority": "Medium", "created_hours": 10, "assigned_team": "Messaging", "status": "in progress",
        "source": "demo", "actual_sla_breach": "No",
    },
    {
        "jira_issue_key": "DEMO-106", "summary": "Shared drive unavailable to the design group",
        "description": "The team receives an access denied error for a previously available folder.",
        "priority": "High", "created_hours": 1.2, "assigned_team": "Identity", "status": "open",
        "source": "demo", "actual_sla_breach": None,
    },
    {
        "jira_issue_key": "DEMO-107", "summary": "Request a standard software installation",
        "description": "Install the approved diagramming tool on a managed workstation.",
        "priority": "Low", "created_hours": 2, "assigned_team": "Workplace", "status": "resolved",
        "source": "demo", "actual_sla_breach": "No",
    },
    {
        "jira_issue_key": "DEMO-108", "summary": "Database connections timing out in reporting",
        "description": "Scheduled reports fail intermittently during the morning peak.",
        "priority": "Medium", "created_hours": 6.5, "assigned_team": "Data Platform", "status": "open",
        "source": "demo", "actual_sla_breach": None,
    },
]


def setup_demo_account(repository: TicketRepository, email: str, password: str) -> int:
    """Create the recruiter admin once and seed stable, editable demo records."""
    existing = repository.get_user_by_email(email)
    if existing:
        if existing["role"] != "admin":
            raise ValueError("The configured demo account exists but is not an administrator.")
        user_id = int(existing["id"])
    else:
        user_id = int(repository.create_user(email, password, "admin")["id"])

    for ticket in DEMO_TICKETS:
        if not repository.get_ticket_by_jira_key(ticket["jira_issue_key"]):
            repository.upsert_ticket(ticket)
    return user_id
