"""Compare Keras 3 outputs with archived predictions from the Keras 2 runtime."""

import hashlib
import json
from pathlib import Path

import pytest

from app.inference import InferenceError, Predictor

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.inference
def test_model_preserves_legacy_predictions():
    pytest.importorskip("keras")
    reference = json.loads((ROOT / "tests/fixtures/legacy_predictions.json").read_text())
    model_path = ROOT / "app/janos-vgg16-model.h5"
    with model_path.open("rb") as model_file:
        assert hashlib.file_digest(model_file, "sha256").hexdigest() == reference["model_sha256"]
    predictor = Predictor(str(model_path))
    for sample in reference["samples"]:
        image_path = ROOT / sample["path"]
        assert hashlib.sha256(image_path.read_bytes()).hexdigest() == sample["sha256"]
        label, confidence = predictor.predict(image_path)
        score = sample["pneumonia_score"]
        expected_label = "Pneumonia" if score > 0.5 else "Normal"
        expected_confidence = (score if score > 0.5 else 1 - score) * 100
        assert label == expected_label
        assert confidence == pytest.approx(expected_confidence, abs=0.002)


@pytest.mark.inference
def test_missing_model_has_actionable_error(tmp_path):
    pytest.importorskip("keras")
    with pytest.raises(InferenceError, match="git lfs pull"):
        Predictor(str(tmp_path / "missing.h5")).predict(tmp_path / "image.png")
