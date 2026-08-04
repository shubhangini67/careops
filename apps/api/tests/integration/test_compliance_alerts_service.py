"""Live integration test for ComplianceAlertsService (P6-A23).

No mocking -- hits FSSAI's real public notifications page, per this task's
acceptance criteria ("Scrape returns real recent notices in a live test").
Requires network access.
"""

import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.infrastructure.external.compliance_alerts_service import ComplianceAlertsService


@pytest.mark.asyncio
async def test_live_notices_from_real_fssai_page():
    result = await ComplianceAlertsService().get_alerts()

    print(f"\nCompliance alerts: {result}")

    assert result is not None
    assert result["notice_count"] > 0
    for notice in result["notices"]:
        assert notice["title"]
        assert notice["uploaded_on"]
        assert notice["url"].startswith("https://fssai.gov.in/")
