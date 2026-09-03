"""Tiny attention-aware policies for the robot brain training loop.

The policy architecture stays deliberately small so it can be trained with the
Cross-Entropy Method using only NumPy. The attention mask lets us simulate the
paper's dynamic processing: at inference time the policy only receives the most
salient subset of the observation vector.
"""
from __future__ import annotations

import numpy as np


class AttentionMLPPolicy:
    """Small ReLU MLP with optional hard attention input masking.

    Architecture is fixed so the flattened weight vector is deterministic and
    can be saved alongside a trained brain bundle.
    """

    INPUT_DIM = 6
    HIDDEN_DIM = 12
    OUTPUT_DIM = 2

    @classmethod
    def n_params(cls) -> int:
        return (
            cls.INPUT_DIM * cls.HIDDEN_DIM
            + cls.HIDDEN_DIM
            + cls.HIDDEN_DIM * cls.OUTPUT_DIM
            + cls.OUTPUT_DIM
        )

    def __init__(self, weights: np.ndarray, attention_mask: np.ndarray | None = None) -> None:
        if weights.shape != (self.n_params(),):
            raise ValueError(
                f"weights must have shape {(self.n_params(),)}, got {weights.shape}"
            )
        self.weights = np.asarray(weights, dtype=float)
        self.W1, self.b1, self.W2, self.b2 = self._unpack(self.weights)
        if attention_mask is None:
            self.mask = np.ones(self.INPUT_DIM, dtype=float)
        else:
            self.mask = np.asarray(attention_mask, dtype=float)
            if self.mask.shape != (self.INPUT_DIM,):
                raise ValueError(
                    f"attention_mask must have shape {(self.INPUT_DIM,)}, got {self.mask.shape}"
                )

    @staticmethod
    def _unpack(weights: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        idx = 0
        W1 = weights[idx : idx + AttentionMLPPolicy.INPUT_DIM * AttentionMLPPolicy.HIDDEN_DIM].reshape(
            AttentionMLPPolicy.INPUT_DIM, AttentionMLPPolicy.HIDDEN_DIM
        )
        idx += AttentionMLPPolicy.INPUT_DIM * AttentionMLPPolicy.HIDDEN_DIM
        b1 = weights[idx : idx + AttentionMLPPolicy.HIDDEN_DIM]
        idx += AttentionMLPPolicy.HIDDEN_DIM
        W2 = weights[idx : idx + AttentionMLPPolicy.HIDDEN_DIM * AttentionMLPPolicy.OUTPUT_DIM].reshape(
            AttentionMLPPolicy.HIDDEN_DIM, AttentionMLPPolicy.OUTPUT_DIM
        )
        idx += AttentionMLPPolicy.HIDDEN_DIM * AttentionMLPPolicy.OUTPUT_DIM
        b2 = weights[idx : idx + AttentionMLPPolicy.OUTPUT_DIM]
        return W1, b1, W2, b2

    def __call__(self, obs: np.ndarray) -> np.ndarray:
        x = np.asarray(obs, dtype=float)[: self.INPUT_DIM] * self.mask
        h = np.maximum(x @ self.W1 + self.b1, 0.0)
        return np.asarray(h @ self.W2 + self.b2, dtype=float).ravel()

    def set_attention_mask(self, mask: np.ndarray) -> None:
        """Replace the hard attention mask (length ``INPUT_DIM``)."""
        self.mask = np.asarray(mask, dtype=float)
        if self.mask.shape != (self.INPUT_DIM,):
            raise ValueError(
                f"attention_mask must have shape {(self.INPUT_DIM,)}, got {self.mask.shape}"
            )
