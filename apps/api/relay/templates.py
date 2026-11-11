from typing import Any

AGENTS = [
    {
        "id": "supervisor",
        "name": "Supervisor",
        "role": "Coordinator",
        "description": "Validates the selected template and delegates a bounded plan.",
        "tools": ["workflow_status"],
        "max_iterations": 1,
        "output_schema": "Plan",
    },
    {
        "id": "planner",
        "name": "Planner",
        "role": "Planning",
        "description": "Builds typed steps and approval constraints.",
        "tools": [],
        "max_iterations": 1,
        "output_schema": "Plan",
    },
    {
        "id": "research",
        "name": "Researcher",
        "role": "Evidence",
        "description": "Retrieves scoped documents and extracts source-backed evidence.",
        "tools": ["retrieve_documents", "structured_data"],
        "max_iterations": 3,
        "output_schema": "ResearchResult",
    },
    {
        "id": "analysis",
        "name": "Analyst",
        "role": "Analysis",
        "description": "Compares evidence and classifies support requests.",
        "tools": ["calculate"],
        "max_iterations": 2,
        "output_schema": "AnalysisResult",
    },
    {
        "id": "writer",
        "name": "Writer",
        "role": "Documentation",
        "description": "Creates cited drafts and incorporates review comments.",
        "tools": ["report"],
        "max_iterations": 3,
        "output_schema": "DraftResult",
    },
    {
        "id": "reviewer",
        "name": "Reviewer",
        "role": "Quality assurance",
        "description": "Independently checks evidence, coverage and completeness.",
        "tools": [],
        "max_iterations": 2,
        "output_schema": "ReviewResult",
    },
    {
        "id": "risk",
        "name": "Risk assessor",
        "role": "Policy",
        "description": "Flags sensitive requests; deterministic application rules require approval.",
        "tools": [],
        "max_iterations": 1,
        "output_schema": "RiskResult",
    },
    {
        "id": "execution",
        "name": "Executor",
        "role": "Approved actions",
        "description": "Writes approved local artifacts and updates local tickets atomically.",
        "tools": ["record_update", "ticket_update", "export"],
        "max_iterations": 1,
        "output_schema": "Artifact",
    },
]

NODES = [
    {"id": "plan", "label": "Plan & delegate", "agent": "supervisor", "type": "trigger"},
    {"id": "research", "label": "Collect evidence", "agent": "research", "type": "agent"},
    {"id": "analysis", "label": "Analyze findings", "agent": "analysis", "type": "agent"},
    {"id": "risk", "label": "Assess risk", "agent": "risk", "type": "condition"},
    {"id": "draft", "label": "Write draft", "agent": "writer", "type": "agent"},
    {"id": "review", "label": "Quality review", "agent": "reviewer", "type": "review"},
    {"id": "approval", "label": "Human approval", "agent": "approver", "type": "approval"},
    {"id": "revise", "label": "Apply feedback", "agent": "writer", "type": "handoff"},
    {"id": "finalize", "label": "Save artifact", "agent": "execution", "type": "output"},
    {"id": "reject", "label": "Close rejected", "agent": "supervisor", "type": "end"},
]
EDGES = [
    {"source": a, "target": b, "label": label}
    for a, b, label in [
        ("plan", "research", ""),
        ("research", "analysis", "parallel"),
        ("research", "risk", "parallel"),
        ("analysis", "draft", "join"),
        ("risk", "draft", "join"),
        ("draft", "review", ""),
        ("review", "approval", "pass / review limit"),
        ("review", "revise", "quality revision"),
        ("approval", "finalize", "approve"),
        ("approval", "revise", "request changes"),
        ("approval", "reject", "reject"),
        ("revise", "draft", "bounded revision"),
    ]
]

TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "research",
        "name": "Research to report",
        "description": "Turn approved reference documents into an evidence-backed report, independently reviewed and approved by you.",
        "sample": {
            "topic": "Compare customer support platforms",
            "brief": "Compare the fictional Atlas and Beacon platforms using the bundled documents. Explain the tradeoffs for a small support team and identify missing evidence.",
        },
    },
    {
        "id": "support",
        "name": "Support ticket triage",
        "description": "Classify a local support ticket, consult the knowledge base, and approve a response draft.",
        "sample": {
            "topic": "Unable to sign in after password reset",
            "brief": "A customer reset their password but still cannot sign in. Classify this ticket, consult the bundled help article, and draft a helpful response. Do not send an external message.",
        },
    },
    {
        "id": "content",
        "name": "Content review",
        "description": "Draft grounded content, review its claims and language, then export after approval.",
        "sample": {
            "topic": "A guide to choosing support software",
            "brief": "Write a concise guide for small teams choosing support software, using only the provided fictional examples. Avoid unsupported marketing claims and acknowledge limitations.",
        },
    },
]
for template in TEMPLATES:
    template.update(version="1.0", nodes=NODES, edges=EDGES)

BUNDLED_SOURCES = [
    {
        "id": "sample-atlas",
        "title": "Atlas product brief (fictional sample)",
        "kind": "sample",
        "content": "Atlas is a fictional customer support platform used for this demonstration. It supports shared inboxes, routing rules, and audit logs. Its sample plan includes 5 seats. It does not include a built-in knowledge base. No measured latency, pricing, or customer satisfaction data is supplied.",
    },
    {
        "id": "sample-beacon",
        "title": "Beacon product brief (fictional sample)",
        "kind": "sample",
        "content": "Beacon is a fictional customer support platform used for this demonstration. It supports a knowledge base, ticket tags, and draft suggestions. Its sample plan includes 3 seats. Audit-log retention is unspecified. No measured latency, pricing, or customer satisfaction data is supplied.",
    },
    {
        "id": "sample-help",
        "title": "Account access knowledge base (sample)",
        "kind": "sample",
        "content": "For sign-in issues after a password reset, verify that the customer uses the correct email address. Ask them to use only the most recent reset link and try a private browser window. Never request passwords or one-time security codes. Escalate suspected account compromise to a human. Refunds and account deletion require separate authorization.",
    },
]
