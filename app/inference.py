"""Lazy, serialized Keras inference with the original preprocessing contract."""

import json
import math
from pathlib import Path
from threading import Lock

from flask import current_app


class InferenceError(RuntimeError):
    """The model or its runtime could not produce a valid result."""


def load_legacy_model(path: Path):
    """Adapt the bundled Keras 2 Sequential config using public Keras 3 APIs.

    The original VGG16 Functional config returns a one-element list and legacy
    BatchNormalization axes are lists. Unwrap those structures without altering
    any tensor or learned weight. Other model formats use Keras' normal loader.
    """
    import h5py
    import keras

    if path.suffix.lower() not in {".h5", ".hdf5"}:
        return keras.models.load_model(path, compile=False)
    with h5py.File(path) as saved:
        config = json.loads(saved.attrs["model_config"])
    if config.get("class_name") != "Sequential":
        return keras.models.load_model(path, compile=False)
    model = keras.Sequential(name=config["config"]["name"])
    allowed = {"Dropout", "Flatten", "BatchNormalization", "Dense", "Activation"}
    for layer in config["config"]["layers"]:
        layer_config = dict(layer["config"])
        class_name = layer["class_name"]
        if class_name == "InputLayer":
            shape = layer_config.get("batch_input_shape", layer_config.get("batch_shape"))
            model.add(
                keras.Input(shape=tuple(shape[1:]), dtype=layer_config.get("dtype", "float32"))
            )
        elif class_name == "Functional":
            backbone = keras.Model.from_config(layer_config)
            if len(backbone.outputs) != 1:
                raise InferenceError("Expected one output from the nested feature extractor.")
            model.add(keras.Model(backbone.inputs, backbone.outputs[0], name=backbone.name))
        elif class_name in allowed:
            if class_name == "BatchNormalization" and isinstance(layer_config.get("axis"), list):
                if len(layer_config["axis"]) != 1:
                    raise InferenceError("Expected a single BatchNormalization axis.")
                layer_config["axis"] = layer_config["axis"][0]
            model.add(getattr(keras.layers, class_name).from_config(layer_config))
        else:
            raise InferenceError(f"Unsupported legacy model layer: {class_name}")
    model.load_weights(path)
    return model


class Predictor:
    """Cache one model per app and prevent simultaneous model calls."""

    def __init__(self, model_path: str):
        self.model_path = Path(model_path)
        self.model = None
        self.lock = Lock()

    def predict(self, image_path: Path) -> tuple[str, float]:
        try:
            import keras
            import numpy as np

            with self.lock:
                if self.model is None:
                    if not self.model_path.is_file() or self.model_path.stat().st_size < 1024:
                        raise InferenceError("Model missing; run git lfs pull.")
                    self.model = load_legacy_model(self.model_path)
                image = keras.utils.load_img(image_path, target_size=(224, 224), color_mode="rgb")
                try:
                    batch = np.expand_dims(keras.utils.img_to_array(image) / 255.0, axis=0)
                finally:
                    image.close()
                output = np.asarray(self.model(batch, training=False))
                if output.size != 1:
                    raise InferenceError("Expected a single binary classification score.")
                probability = float(output.item())
                if not math.isfinite(probability) or not 0 <= probability <= 1:
                    raise InferenceError("Model score is outside the expected probability range.")
                if probability > 0.5:
                    return "Pneumonia", probability * 100
                return "Normal", (1 - probability) * 100
        except InferenceError:
            raise
        except Exception as error:
            raise InferenceError("Unable to load the model or perform inference.") from error


def predict(image_path: Path) -> tuple[str, float]:
    predictor = current_app.extensions.setdefault(
        "janos_predictor", Predictor(current_app.config["MODEL_PATH"])
    )
    return predictor.predict(image_path)
