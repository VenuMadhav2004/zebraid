"""Global + Local score fusion combining deep feature embeddings with ORB stripe matching."""
from __future__ import annotations
from typing import Sequence, Tuple, Optional
import numpy as np
from member1_dhanushya.recognition.local_matching import orb_similarity

def normalize_scores_per_query(scores_matrix: np.ndarray) -> np.ndarray:
    """Min-max normalize scores per query across gallery candidates to [0, 1]."""
    mins = scores_matrix.min(axis=1, keepdims=True)
    maxs = scores_matrix.max(axis=1, keepdims=True)
    diff = maxs - mins
    diff[diff < 1e-8] = 1.0
    return (scores_matrix - mins) / diff

def compute_orb_scores(query_images: Sequence[np.ndarray], gallery_images: Sequence[np.ndarray], max_features: int = 1000, ratio: float = 0.75) -> np.ndarray:
    """Compute pairwise ORB similarity matrix of shape (num_queries, num_gallery)."""
    n_q = len(query_images)
    n_g = len(gallery_images)
    scores = np.zeros((n_q, n_g), dtype=float)
    for i in range(n_q):
        for j in range(n_g):
            scores[i, j] = orb_similarity(query_images[i], gallery_images[j], max_features=max_features, ratio=ratio)
    return scores

def fuse_scores(global_scores: np.ndarray, local_scores: np.ndarray, alpha: float = 0.3, normalize: bool = True) -> np.ndarray:
    """Combine global embedding cosine similarities and local ORB match similarities.

    Args:
        global_scores: 2D array of cosine similarities (num_queries, num_gallery)
        local_scores: 2D array of local match ratios (num_queries, num_gallery)
        alpha: Weight on the local matcher (between 0.0 and 1.0)
        normalize: If True, min-max normalize both modalities per query before weighting.

    Returns:
        Fused scores matrix of shape (num_queries, num_gallery)
    """
    if not (0.0 <= alpha <= 1.0):
        raise ValueError("alpha must be in [0, 1]")
    if global_scores.shape != local_scores.shape:
        raise ValueError("global and local scores must have identical shape")

    if normalize:
        norm_global = normalize_scores_per_query(global_scores)
        norm_local = normalize_scores_per_query(local_scores)
        return (1.0 - alpha) * norm_global + alpha * norm_local
    else:
        return (1.0 - alpha) * global_scores + alpha * local_scores


class GlobalLocalFusionMatcher:
    """Class wrapper for Global + Local score fusion."""
    def __init__(self, alpha: float = 0.75, normalize: bool = True):
        self.alpha = alpha
        self.normalize = normalize

    def fuse(self, global_scores: np.ndarray, local_scores: np.ndarray) -> np.ndarray:
        return fuse_scores(global_scores, local_scores, alpha=self.alpha, normalize=self.normalize)
