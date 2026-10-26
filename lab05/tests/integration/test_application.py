"""Do the two apps behave correctly when you use them through the load balancer?

Run after the targets are healthy:     pytest -m integration
"""

import uuid

import pytest
import requests

from tests.helpers import tier_url, wait_until


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def uploader_url(settings, outputs):
    return tier_url(
        outputs,
        settings,
        "uploader",
    )


@pytest.fixture(scope="module")
def viewer_url(settings, outputs):
    return tier_url(
        outputs,
        settings,
        "viewer",
    )


def _upload(
    url,
    filename,
    content,
    mimetype,
):
    files = {
        "txtfile": (
            filename,
            content,
            mimetype,
        )
    }

    return requests.post(
        url + "upload",
        files=files,
        timeout=10,
    )


def test_uploader_serves_its_form(
    uploader_url,
):
    response = requests.get(
        uploader_url,
        timeout=10,
    )

    assert response.status_code == 200
    assert "Uploader" in response.text


def test_viewer_serves_its_page(
    viewer_url,
):
    response = requests.get(
        viewer_url,
        timeout=10,
    )

    assert response.status_code == 200
    assert "Viewer" in response.text


def test_text_file_uploaded_on_one_tier_appears_on_the_other(
    uploader_url,
    viewer_url,
):
    token = f"lab05-{uuid.uuid4()}"

    response = _upload(
        uploader_url,
        "lab05.txt",
        token.encode(),
        "text/plain",
    )

    assert response.status_code == 200
    assert "Upload successful" in response.text

    def viewer_shows_token():
        return token in requests.get(
            viewer_url,
            timeout=10,
        ).text

    assert wait_until(
        viewer_shows_token,
        timeout=30,
        interval=2,
    )


def test_non_txt_file_is_rejected(
    uploader_url,
):
    response = _upload(
        uploader_url,
        "picture.png",
        b"not text",
        "image/png",
    )

    assert response.status_code == 415


def test_file_over_1mb_is_rejected(
    uploader_url,
):
    too_big = b"a" * (
        1024 * 1024 + 1
    )

    response = _upload(
        uploader_url,
        "big.txt",
        too_big,
        "text/plain",
    )

    assert response.status_code == 413
