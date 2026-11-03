"""Preview-image acquisition must not damage the model registry on failure."""
from __future__ import annotations

import json

import pytest

from argazui import fetch_images


pytestmark = pytest.mark.tier1


def test_missing_upstream_image_preserves_declared_preview_path(tmp_path, monkeypatch):
    registry_path = tmp_path / "models.json"
    registry_path.write_text(json.dumps({"models": [{
        "id": "iris",
        "source": "SITL_Models/Gazebo/docs/Iris.md",
        "image": "/static/models/iris.png",
    }]}), encoding="utf-8")

    monkeypatch.setattr(fetch_images.paths, "MODELS_JSON", registry_path)
    monkeypatch.setattr(fetch_images, "IMAGES_DIR", tmp_path / "static-models")
    monkeypatch.setattr(fetch_images, "_from_local_thumbnail", lambda *_: False)
    monkeypatch.setattr(fetch_images, "_from_doc", lambda *_: False)

    assert fetch_images.main([]) == 0
    written = json.loads(registry_path.read_text(encoding="utf-8"))
    assert written["models"][0]["image"] == "/static/models/iris.png"
