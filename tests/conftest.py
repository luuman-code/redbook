"""pytest configuration and fixtures"""
import pytest
import asyncio
import os
import sys

# Ensure redbook root is in path for imports
redbook_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if redbook_root not in sys.path:
    sys.path.insert(0, redbook_root)

# Add config-ui/backend to path for imports
config_ui_backend = os.path.join(redbook_root, "config-ui", "backend")
if config_ui_backend not in sys.path:
    sys.path.insert(0, config_ui_backend)


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def test_client():
    """Test client fixture for async tests"""
    from httpx import AsyncClient, ASGITransport

    # Import app from config-ui backend main module
    from main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
def mock_auth_token():
    """Mock authentication token"""
    return "Bearer test_token_12345"
