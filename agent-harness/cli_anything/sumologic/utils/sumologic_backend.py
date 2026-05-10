"""HTTP backend for the Sumo Logic Search Job API.

All API calls go through this module. The real Sumo Logic SaaS service is the
required backend — this is not a simulation.

Auth: HTTP Basic with Access ID + Access Key.
Base URL: https://api.<deployment>.sumologic.com/api/v1/
"""

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional


class SumoLogicClient:
    """Thin HTTP client for the Sumo Logic Search Job API."""

    def __init__(self, endpoint: str, access_id: str, access_key: str):
        """
        Args:
            endpoint: Full base URL, e.g. https://api.us2.sumologic.com/api/v1
            access_id: Sumo Logic Access ID
            access_key: Sumo Logic Access Key
        """
        self.endpoint = endpoint.rstrip("/")
        creds = f"{access_id}:{access_key}"
        encoded = base64.b64encode(creds.encode()).decode()
        self._auth_header = f"Basic {encoded}"

    def _url(self, path: str) -> str:
        return f"{self.endpoint}/{path.lstrip('/')}"

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> Any:
        url = self._url(path)
        if params:
            url = url + "?" + urllib.parse.urlencode(params)

        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", self._auth_header)
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")

        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read()
                if raw:
                    return json.loads(raw)
                return None
        except urllib.error.HTTPError as e:
            body_text = e.read().decode(errors="replace")
            raise RuntimeError(
                f"Sumo Logic API error {e.code} {e.reason} on {method} {url}:\n"
                f"{body_text}"
            ) from e
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Network error reaching Sumo Logic ({url}): {e.reason}\n"
                "Check your SUMO_ENDPOINT and network connectivity."
            ) from e

    def create_job(
        self,
        query: str,
        from_time: str,
        to_time: str,
        timezone: str = "UTC",
    ) -> dict[str, Any]:
        """POST /search/jobs — create a search job, return { id }."""
        return self._request("POST", "/search/jobs", body={
            "query": query,
            "from": from_time,
            "to": to_time,
            "timeZone": timezone,
        })

    def get_status(self, job_id: str) -> dict[str, Any]:
        """GET /search/jobs/{id} — poll job status."""
        return self._request("GET", f"/search/jobs/{job_id}")

    def get_messages(
        self,
        job_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """GET /search/jobs/{id}/messages — fetch raw log messages."""
        return self._request(
            "GET",
            f"/search/jobs/{job_id}/messages",
            params={"limit": limit, "offset": offset},
        )

    def get_records(
        self,
        job_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """GET /search/jobs/{id}/records — fetch aggregate records."""
        return self._request(
            "GET",
            f"/search/jobs/{job_id}/records",
            params={"limit": limit, "offset": offset},
        )

    def delete_job(self, job_id: str) -> None:
        """DELETE /search/jobs/{id} — cancel/delete a search job."""
        self._request("DELETE", f"/search/jobs/{job_id}")


def make_client(endpoint: str, access_id: str, access_key: str) -> SumoLogicClient:
    """Construct a SumoLogicClient, validating that credentials are provided."""
    if not endpoint:
        raise RuntimeError(
            "Sumo Logic endpoint is required.\n"
            "Set SUMO_ENDPOINT env var or run: cli-anything-sumologic auth configure\n"
            "Example: https://api.us2.sumologic.com/api/v1"
        )
    if not access_id or not access_key:
        raise RuntimeError(
            "Sumo Logic credentials are required.\n"
            "Set SUMO_ACCESS_ID and SUMO_ACCESS_KEY env vars,\n"
            "or run: cli-anything-sumologic auth configure"
        )
    return SumoLogicClient(endpoint, access_id, access_key)
