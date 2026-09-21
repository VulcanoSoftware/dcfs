import pytest

from asgidav.app import extract_path_from_destination, split_path


class TestAppHelpers:
    def test_split_path_root(self):
        parent, name = split_path("/")
        assert parent == "/"
        assert name == ""

    def test_split_path_single_level(self):
        parent, name = split_path("/test")
        assert parent == "/"
        assert name == "test"

    def test_split_path_multiple_levels(self):
        parent, name = split_path("/path/to/file.txt")
        assert parent == "path/to"
        assert name == "file.txt"

    def test_split_path_trailing_slash(self):
        parent, name = split_path("/path/to/folder/")
        assert parent == "path/to"
        assert name == "folder"

    def test_extract_path_from_destination_http(self):
        url = "http://example.com/webdav/path/to/file.txt"
        result = extract_path_from_destination(url)
        assert result == "/webdav/path/to/file.txt"

    def test_extract_path_from_destination_https(self):
        url = "https://example.com/webdav/path/to/file.txt"
        result = extract_path_from_destination(url)
        assert result == "/webdav/path/to/file.txt"

    def test_extract_path_from_destination_path_only(self):
        path = "/webdav/path/to/file.txt"
        result = extract_path_from_destination(path)
        assert result == "/webdav/path/to/file.txt"

    def test_extract_path_from_destination_encoded(self):
        path = "/webdav/path%20with%20spaces/file.txt"
        result = extract_path_from_destination(path)
        assert result == "/webdav/path with spaces/file.txt"


class TestAppEndpoints:
    @pytest.mark.asyncio
    async def test_proppatch_endpoint_found(self, mocker):
        from fastapi.testclient import TestClient

        from asgidav.app import create_app

        from .common import MockResource

        mock_get_member = mocker.AsyncMock(return_value=MockResource("/test.txt"))
        app = create_app(get_member=mock_get_member)
        client = TestClient(app)

        response = client.request("PROPPATCH", "/test.txt")
        assert response.status_code == 207
        assert "multistatus" in response.text

    @pytest.mark.asyncio
    async def test_proppatch_endpoint_not_found(self, mocker):
        from fastapi.testclient import TestClient

        from asgidav.app import create_app

        mock_get_member = mocker.AsyncMock(return_value=None)
        app = create_app(get_member=mock_get_member)
        client = TestClient(app)

        response = client.request("PROPPATCH", "/nonexistent.txt")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_put_endpoint_calls_overwrite_for_chunked_or_missing_length(self, mocker):
        from fastapi.testclient import TestClient

        from asgidav.app import create_app

        from .common import MockResource

        mock_res = MockResource("/test.txt")
        mock_overwrite = mocker.patch.object(
            mock_res, "overwrite", new_callable=mocker.AsyncMock
        )

        mock_get_member = mocker.AsyncMock(return_value=mock_res)
        app = create_app(get_member=mock_get_member)
        client = TestClient(app)

        # 1. PUT with Transfer-Encoding: chunked
        res1 = client.put(
            "/test.txt", content=b"hello", headers={"Transfer-Encoding": "chunked"}
        )
        assert res1.status_code == 201
        assert mock_overwrite.called
        assert mock_overwrite.call_args[1]["size"] == -1

        # 2. PUT with fixed Content-Length
        mock_overwrite.reset_mock()
        res2 = client.put("/test.txt", content=b"hello")
        assert res2.status_code == 201
        assert mock_overwrite.called
        assert mock_overwrite.call_args[1]["size"] == 5
