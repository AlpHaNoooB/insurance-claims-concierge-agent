import os
from unittest.mock import MagicMock

# Set mock environment variables before any imports happen
os.environ["GOOGLE_CLOUD_PROJECT"] = "mock-project-id"
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "False"

# Mock google.auth.default to prevent DefaultCredentialsError
import google.auth

google.auth.default = MagicMock(return_value=(MagicMock(), "mock-project-id"))

# Mock vertexai to avoid initializing real GCP connections in tests
import vertexai  # noqa: E402

vertexai.init = MagicMock()
