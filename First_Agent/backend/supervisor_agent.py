from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .grafana_agent import GrafanaAgent


@dataclass
class SupervisorResponse:
    answer: str
    route: str
    task: dict[str, Any]
    raw: dict[str, Any]


class SupervisorAgent:
    """Orchestrates user chat, parses intent, and delegates to sub-agents."""

    def __init__(self, grafana_agent: GrafanaAgent | None = None) -> None:
        self.grafana_agent = grafana_agent or GrafanaAgent()

    def chat(self, message: str) -> SupervisorResponse:
        cleaned = message.strip()
        if not cleaned:
            return SupervisorResponse(
                answer="Ask me about Grafana health, CPU, memory, disk, uptime, or an explicit PromQL query.",
                route="supervisor",
                task={},
                raw={"ok": True},
            )

        task = self._parse_task(cleaned)
        if task["route"] == "grafana":
            raw = self.grafana_agent.handle(task)
            answer = self._compose_grafana_answer(raw)
            return SupervisorResponse(answer=answer, route="grafana", task=task, raw=raw)

        return SupervisorResponse(
            answer=(
                "I can help with Grafana monitoring questions. Try asking for CPU, memory, disk, uptime, "
                "Grafana API health, or provide a PromQL query like `query up for last 30m`."
            ),
            route="supervisor",
            task=task,
            raw={"ok": True},
        )

    def _parse_task(self, message: str) -> dict[str, Any]:
        lower = message.lower()
        lookback_seconds = self._parse_lookback(lower)

        query_match = re.search(r"(?:query|promql)\s+(.+?)(?:\s+for\s+last\s+\d+\s*[smhd])?$", message, re.IGNORECASE)
        if query_match:
            return {
                "route": "grafana",
                "intent": "custom_query",
                "query": query_match.group(1).strip(),
                "lookback_seconds": lookback_seconds,
            }

        if "grafana" in lower and any(word in lower for word in ("health", "status", "api", "reachable")):
            return {"route": "grafana", "intent": "grafana_health", "lookback_seconds": lookback_seconds}

        intent_keywords = {
            "cpu": ["cpu", "processor", "load"],
            "memory": ["memory", "mem", "ram"],
            "disk": ["disk", "filesystem", "storage"],
            "uptime": ["uptime", "up", "down", "failing", "instance", "target"],
            "health": ["health", "healthy", "status", "monitoring"],
        }
        for intent, keywords in intent_keywords.items():
            if any(keyword in lower for keyword in keywords):
                return {"route": "grafana", "intent": intent, "lookback_seconds": lookback_seconds}

        return {"route": "supervisor", "intent": "unknown", "lookback_seconds": lookback_seconds}

    def _parse_lookback(self, lower_message: str) -> int:
        match = re.search(r"last\s+(\d+)\s*([smhd])", lower_message)
        if not match:
            return 3600

        amount = int(match.group(1))
        unit = match.group(2)
        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        return max(60, amount * multipliers[unit])

    def _compose_grafana_answer(self, raw: dict[str, Any]) -> str:
        lines = [raw.get("summary", "Grafana request completed.")]
        suggestions = raw.get("suggestions") or []
        if suggestions:
            lines.append("")
            lines.append("Suggested next step:")
            lines.extend(f"- {item}" for item in suggestions[:3])
        return "\n".join(lines)

