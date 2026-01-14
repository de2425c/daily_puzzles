"""Configuration for Deepsolver API client."""

import os
from pathlib import Path

# Try to load from .env file
try:
    from dotenv import load_dotenv

    # Look for .env in the daily_puzzles directory
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass  # python-dotenv not installed, rely on environment variables

# API Configuration
DEEPSOLVER_BASE_URL = "https://gcp-fn-treebuilder.prod-eu01.deepsolver.cloud"


def get_api_token() -> str:
    """Get the Deepsolver API token from environment."""
    token = os.getenv("DEEPSOLVER_API_TOKEN")
    if not token:
        raise ValueError(
            "DEEPSOLVER_API_TOKEN not set. "
            "Set it in your environment or create a .env file."
        )
    return token
