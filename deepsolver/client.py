"""Deepsolver API client for submitting and retrieving solver results."""

import time
from typing import Any

import requests

from .config import DEEPSOLVER_BASE_URL


class DeepsolverError(Exception):
    """Base exception for Deepsolver API errors."""
    pass


class DeepsolverTimeoutError(DeepsolverError):
    """Raised when polling for results times out."""
    pass


class DeepsolverClient:
    """Client for the Deepsolver poker GTO solver API."""

    def __init__(
        self,
        api_token: str,
        base_url: str = DEEPSOLVER_BASE_URL,
    ):
        """
        Initialize the Deepsolver client.

        Args:
            api_token: API authentication token
            base_url: Base URL for the API (default: production endpoint)
        """
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Token {api_token}",
            "Content-Type": "application/json",
        })

    def schedule(self, request: dict[str, Any]) -> str:
        """
        Submit a solver request to the API.

        Args:
            request: The solver request payload (board, ranges, tree_request, etc.)

        Returns:
            task_id: The ID of the scheduled task

        Raises:
            DeepsolverError: If the API returns an error
        """
        url = f"{self.base_url}/task/cfr/schedule"

        response = self.session.post(url, json=request)

        if response.status_code != 200:
            raise DeepsolverError(
                f"Failed to schedule task: {response.status_code} - {response.text}"
            )

        data = response.json()
        task_id = data.get("task_id")

        if not task_id:
            raise DeepsolverError(f"No task_id in response: {data}")

        # Log queue position if available
        queue_pos = data.get("queue_pos")
        queue_eta = data.get("queue_eta")
        if queue_pos is not None:
            print(f"  Queue position: {queue_pos}, ETA: {queue_eta}s")

        return task_id

    def get_result(self, task_id: str) -> dict[str, Any] | None:
        """
        Get the result of a solver task.

        Args:
            task_id: The task ID returned from schedule()

        Returns:
            The solver result (tree, stats, config) if ready, None if still processing

        Raises:
            DeepsolverError: If the API returns an unexpected error
        """
        url = f"{self.base_url}/task/cfr/result/{task_id}"

        response = self.session.get(url)

        # 404 means still processing
        if response.status_code == 404:
            return None

        if response.status_code != 200:
            raise DeepsolverError(
                f"Failed to get result: {response.status_code} - {response.text}"
            )

        return response.json()

    def run_and_wait(
        self,
        request: dict[str, Any],
        timeout_seconds: int = 300,
        poll_interval_seconds: int = 5,
    ) -> dict[str, Any]:
        """
        Submit a solver request and wait for the result.

        Args:
            request: The solver request payload
            timeout_seconds: Maximum time to wait for result (default: 5 minutes)
            poll_interval_seconds: Time between polling attempts (default: 5 seconds)

        Returns:
            The solver result (tree, stats, config)

        Raises:
            DeepsolverTimeoutError: If the result is not ready within timeout
            DeepsolverError: If the API returns an error
        """
        print("Submitting solve request...")
        task_id = self.schedule(request)
        print(f"Got task_id: {task_id}")

        start_time = time.time()
        poll_count = 0

        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout_seconds:
                raise DeepsolverTimeoutError(
                    f"Result not ready after {timeout_seconds}s (task_id: {task_id})"
                )

            poll_count += 1
            print(f"Polling for result... (attempt {poll_count}, {elapsed:.0f}s elapsed)")

            result = self.get_result(task_id)
            if result is not None:
                print(f"Result received!")
                return result

            time.sleep(poll_interval_seconds)
