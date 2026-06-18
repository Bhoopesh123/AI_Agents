from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ENV_PATH = Path(__file__).resolve().parents[1] / ".env"

DEFAULT_QUERIES = {
    "cpu": '100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)',
    "memory": '(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100',
    "disk": '(1 - (node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay"})) * 100',
    "uptime": "up",
    "health": "up",
}


def load_dotenv(path: Path = ENV_PATH) -> None:
    """Load simple KEY=VALUE pairs without overriding real environment values."""
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class GrafanaConfig:
    url: str
    api_key: str
    datasource_uid: str
    org_id: str | None
    verify_ssl: bool
    timeout_seconds: int

    @classmethod
    def from_env(cls) -> "GrafanaConfig":
        load_dotenv()
        return cls(
            url=os.getenv("GRAFANA_URL", "").rstrip("/"),
            api_key=os.getenv("GRAFANA_API_KEY", ""),
            datasource_uid=os.getenv("GRAFANA_DATASOURCE_UID", ""),
            org_id=os.getenv("GRAFANA_ORG_ID"),
            verify_ssl=os.getenv("GRAFANA_VERIFY_SSL", "true").lower() not in {"0", "false", "no"},
            timeout_seconds=int(os.getenv("GRAFANA_TIMEOUT_SECONDS", "20")),
        )

    @property
    def is_ready(self) -> bool:
        return bool(self.url and self.api_key and self.datasource_uid)


class GrafanaAgent:
    """Fetches Grafana health and datasource metric data for the supervisor."""

    def __init__(self, config: GrafanaConfig | None = None) -> None:
        self.config = config or GrafanaConfig.from_env()

    def handle(self, task: dict[str, Any]) -> dict[str, Any]:
        if not self.config.is_ready:
            return self._not_configured_response(task)

        intent = task.get("intent", "health")
        query = task.get("query") or self._query_for_intent(intent)
        lookback_seconds = int(task.get("lookback_seconds", 3600))

        if intent == "grafana_health":
            return self._grafana_health()

        if not query:
            return {
                "ok": False,
                "summary": "I could not map that request to a Grafana query.",
                "details": {"intent": intent},
                "suggestions": ["Try asking for CPU, memory, disk, uptime, or provide an explicit PromQL query."],
            }

        return self._query_range(query=query, lookback_seconds=lookback_seconds, intent=intent)

    def _grafana_health(self) -> dict[str, Any]:
        try:
            result = self._request("GET", "/api/health")
            return {
                "ok": True,
                "summary": f"Grafana API is reachable. Database status: {result.get('database', 'unknown')}.",
                "details": result,
                "suggestions": [],
            }
        except Exception as exc:
            return {
                "ok": False,
                "summary": "Grafana API health check failed.",
                "details": {"error": str(exc)},
                "suggestions": ["Verify GRAFANA_URL and GRAFANA_API_KEY.", "Check network access from this backend host."],
            }

    def _query_range(self, query: str, lookback_seconds: int, intent: str) -> dict[str, Any]:
        now = int(time.time())
        payload = {
            "queries": [
                {
                    "refId": "A",
                    "datasource": {"uid": self.config.datasource_uid},
                    "expr": query,
                    "range": True,
                    "intervalMs": 15000,
                    "maxDataPoints": 120,
                }
            ],
            "from": str((now - lookback_seconds) * 1000),
            "to": str(now * 1000),
        }

        try:
            raw = self._request("POST", "/api/ds/query", payload)
            series = self._extract_series(raw)
            summary = self._summarize_series(intent, series)
            return {
                "ok": True,
                "summary": summary,
                "details": {"query": query, "series": series[:8], "series_count": len(series)},
                "suggestions": self._suggestions_for_series(intent, series),
            }
        except Exception as exc:
            return {
                "ok": False,
                "summary": "Grafana query failed.",
                "details": {"query": query, "error": str(exc)},
                "suggestions": [
                    "Confirm GRAFANA_DATASOURCE_UID points to a Prometheus-compatible datasource.",
                    "Check that the metric names exist in your environment.",
                ],
            }

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
        }
        if self.config.org_id:
            headers["X-Grafana-Org-Id"] = self.config.org_id

        request = urllib.request.Request(
            url=f"{self.config.url}{path}",
            data=body,
            method=method,
            headers=headers,
        )
        context = None if self.config.verify_ssl else ssl._create_unverified_context()

        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds, context=context) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            message = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {message}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Connection error: {exc.reason}") from exc

    def _extract_series(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        frames = raw.get("results", {}).get("A", {}).get("frames", [])
        series: list[dict[str, Any]] = []
        for frame in frames:
            fields = frame.get("schema", {}).get("fields", [])
            values = frame.get("data", {}).get("values", [])
            if len(values) < 2:
                continue

            timestamps = values[0]
            samples = values[1]
            labels = {}
            name = "series"
            if len(fields) > 1:
                labels = fields[1].get("labels") or {}
                name = fields[1].get("name") or name

            numeric_samples = [float(value) for value in samples if isinstance(value, (int, float))]
            if not numeric_samples:
                continue

            series.append(
                {
                    "name": name,
                    "labels": labels,
                    "latest": numeric_samples[-1],
                    "min": min(numeric_samples),
                    "max": max(numeric_samples),
                    "avg": sum(numeric_samples) / len(numeric_samples),
                    "points": len(numeric_samples),
                    "start": timestamps[0] if timestamps else None,
                    "end": timestamps[-1] if timestamps else None,
                }
            )
        return series

    def _query_for_intent(self, intent: str) -> str:
        return DEFAULT_QUERIES.get(intent, DEFAULT_QUERIES.get("health", "up"))

    def _summarize_series(self, intent: str, series: list[dict[str, Any]]) -> str:
        if not series:
            return "Grafana returned no time series for that request."

        if intent in {"cpu", "memory", "disk"}:
            highest = max(series, key=lambda item: item["latest"])
            label = highest.get("labels", {}).get("instance") or highest.get("name", "top series")
            return f"{intent.title()} latest high-water mark is {highest['latest']:.2f}% on {label}."

        if intent in {"uptime", "health"}:
            down = [item for item in series if item["latest"] < 1]
            if down:
                names = ", ".join((item.get("labels", {}).get("instance") or item.get("name", "unknown")) for item in down[:5])
                return f"{len(down)} target(s) appear down: {names}."
            return f"All {len(series)} returned target(s) are reporting up."

        latest = series[0]["latest"]
        return f"Grafana returned {len(series)} series. First latest value is {latest:.2f}."

    def _suggestions_for_series(self, intent: str, series: list[dict[str, Any]]) -> list[str]:
        if not series:
            return ["Check the datasource UID, query, and selected time range."]

        if intent in {"cpu", "memory", "disk"}:
            top = max(series, key=lambda item: item["latest"])
            if top["latest"] >= 90:
                return ["Investigate saturation above 90%.", "Correlate with recent deploys, traffic spikes, and node pressure."]
            if top["latest"] >= 75:
                return ["Watch this resource closely; it is above 75%."]

        return []

    def _not_configured_response(self, task: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "summary": "Grafana agent is running, but Grafana connection variables are not configured yet.",
            "details": {
                "requested_task": task,
                "required_env": ["GRAFANA_URL", "GRAFANA_API_KEY", "GRAFANA_DATASOURCE_UID"],
                "backend_mode": "configuration_pending",
            },
            "suggestions": [
                "Set GRAFANA_URL to your Grafana base URL.",
                "Set GRAFANA_API_KEY to a Grafana service account token.",
                "Set GRAFANA_DATASOURCE_UID to the Prometheus datasource UID.",
            ],
        }
