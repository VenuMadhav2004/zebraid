"""Model enhancement strategies: zebra flank cropping, viewpoint compatibility,
multi-reference gallery pooling, and occlusion-robust stripe matching.
"""
from __future__ import annotations
from typing import Sequence, List, Dict, Any, Tuple
import cv2
import numpy as np
from member2_nisan.zebra_vision import normalize_image

def flank_crop(image: np.ndarray, y_margin: float = 0.15, x_margin: float = 0.15) -> np.ndarray:
    """Crop the torso/flank region of the zebra to isolate stripe patterns from legs/background."""
    a = normalize_image(image)
    h, w = a.shape[:2]
    y1 = int(round(h * y_margin))
    y2 = int(round(h * (1.0 - y_margin)))
    x1 = int(round(w * x_margin))
    x2 = int(round(w * (1.0 - x_margin)))
    if y2 - y1 < 10 or x2 - x1 < 10:
        return a
    return a[y1:y2, x1:x2]

def multi_reference_pool(scores: np.ndarray, gallery_ids: Sequence[str], method: str = "max") -> Tuple[Dict[str, float], str]:
    """Aggregate per-image scores to identity-level score using multi-reference gallery pooling.

    Methods:
        'max': Best individual reference image score (standard pessimistic/optimistic)
        'mean': Mean score across all reference images of that identity
        'top2_mean': Mean of the top 2 reference images
    """
    identities = sorted(set(gallery_ids))
    gi = np.asarray(gallery_ids)
    id_scores = {}
    for ident in identities:
        matches = scores[gi == ident]
        if method == "max":
            id_scores[ident] = float(matches.max())
        elif method == "mean":
            id_scores[ident] = float(matches.mean())
        elif method == "top2_mean":
            if len(matches) >= 2:
                top2 = np.partition(matches, -2)[-2:]
                id_scores[ident] = float(top2.mean())
            else:
                id_scores[ident] = float(matches.max())
        else:
            raise ValueError(f"unknown pooling method: {method}")
    predicted = max(identities, key=lambda ident: (id_scores[ident], -ord(ident[0])))
    return id_scores, predicted

def multi_patch_stripe_similarity(query: np.ndarray, gallery: np.ndarray, grid_size: Tuple[int, int] = (2, 2)) -> float:
    """Compute patch-based local stripe consistency across grid quadrants for occlusion robustness."""
    a_q = normalize_image(query)
    a_g = normalize_image(gallery)
    h_q, w_q = a_q.shape[:2]
    h_g, w_g = a_g.shape[:2]
    rows, cols = grid_size
    dy_q, dx_q = h_q // rows, w_q // cols
    dy_g, dx_g = h_g // rows, w_g // cols

    from member1_dhanushya.recognition.local_matching import orb_similarity
    patch_scores = []
    for r in range(rows):
        for c in range(cols):
            pq = a_q[r*dy_q:(r+1)*dy_q, c*dx_q:(c+1)*dx_q]
            pg = a_g[r*dy_g:(r+1)*dy_g, c*dx_g:(c+1)*dx_g]
            if pq.size > 0 and pg.size > 0:
                s = orb_similarity(pq, pg, max_features=500, ratio=0.75)
                patch_scores.append(s)
    return float(np.mean(patch_scores)) if patch_scores else 0.0
