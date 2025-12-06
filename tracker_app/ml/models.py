"""TensorFlow model definitions with small, fast architectures."""
from __future__ import annotations

from typing import Any

try:  # TensorFlow is optional in some dev environments
    import tensorflow as tf
except Exception:  # noqa: BLE001
    tf = None  # type: ignore


def build_duration_model(input_dim: int) -> Any:
    if tf is None:
        return None
    model = tf.keras.Sequential(
        [
            tf.keras.layers.Input(shape=(input_dim,)),
            tf.keras.layers.Dense(32, activation="relu"),
            tf.keras.layers.Dense(16, activation="relu"),
            tf.keras.layers.Dense(1, activation="linear"),
        ]
    )
    model.compile(optimizer="adam", loss="mse")
    return model


def build_priority_model(input_dim: int) -> Any:
    if tf is None:
        return None
    model = tf.keras.Sequential(
        [
            tf.keras.layers.Input(shape=(input_dim,)),
            tf.keras.layers.Dense(32, activation="relu"),
            tf.keras.layers.Dense(4, activation="softmax"),
        ]
    )
    model.compile(optimizer="adam", loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    return model

