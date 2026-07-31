"""Cookie-authenticated data API integration (connect + upload)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.schemas.auth import AuthTokenResponse, UserPublic
from app.schemas.data_source import WarehouseConnectResponse
from app.services.auth_service import IssuedAuth
from tests.conftest import DEMO_SOURCE_ID, WAREHOUSE_CONNECT_PAYLOAD


def _issued(user) -> IssuedAuth:
    return IssuedAuth(
        access_token="cookie-access-token",
        refresh_token="cookie-refresh-token",
        refresh_max_age=604800,
        response=AuthTokenResponse(
            expires_in=1800,
            user=UserPublic.model_validate(user),
        ),
    )


class TestCookieAuthDataFlow:
    """Uses real cookie deps (no get_current_user override) for connect/upload."""

    def test_connect_and_upload_with_access_cookie(
        self,
        unauthenticated_client: TestClient,
        sample_user,
        warehouse_connect_response: WarehouseConnectResponse,
    ) -> None:
        with patch(
            "app.routes.auth.AuthService.login",
            new=AsyncMock(return_value=_issued(sample_user)),
        ):
            login = unauthenticated_client.post(
                "/api/auth/login",
                json={"identifier": "analyst", "password": "Str0ng!Pass99"},
            )
        assert login.status_code == 200
        assert "vdda_access" in login.cookies
        assert "access_token" not in login.json()

        with (
            patch(
                "app.deps.auth.decode_access_token",
                return_value={"sub": str(sample_user.id)},
            ),
            patch(
                "app.deps.auth.AuthService.get_user",
                new=AsyncMock(return_value=sample_user),
            ),
            patch(
                "app.routes.data.DataSourceService.connect",
                new=AsyncMock(return_value=warehouse_connect_response),
            ),
        ):
            connect = unauthenticated_client.post(
                "/api/data/connect",
                json=WAREHOUSE_CONNECT_PAYLOAD,
            )
        assert connect.status_code == 200
        assert connect.json()["data_source_id"] == str(DEMO_SOURCE_ID)

        upload_payload = {
            "data_source_id": DEMO_SOURCE_ID,
            "name": "sales (upload)",
            "host": "localhost",
            "port": 5433,
            "database": "bi_warehouse",
            "schema_name": "u_abc123def456",
            "table_name": "sales",
            "rows_loaded": 2,
            "columns": ["region", "amount"],
            "file_kind": "csv",
            "status": "loaded",
        }
        with (
            patch(
                "app.deps.auth.decode_access_token",
                return_value={"sub": str(sample_user.id)},
            ),
            patch(
                "app.deps.auth.AuthService.get_user",
                new=AsyncMock(return_value=sample_user),
            ),
            patch(
                "app.routes.data.UploadService.upload",
                new=AsyncMock(return_value=upload_payload),
            ),
        ):
            upload = unauthenticated_client.post(
                "/api/data/upload",
                files={"file": ("demo.csv", b"a,b\n1,2\n", "text/csv")},
            )
        assert upload.status_code == 200
        assert upload.json()["status"] == "loaded"

    def test_connect_without_cookie_still_401(
        self, unauthenticated_client: TestClient
    ) -> None:
        response = unauthenticated_client.post(
            "/api/data/connect",
            json=WAREHOUSE_CONNECT_PAYLOAD,
        )
        assert response.status_code == 401
