"""MegaDescriptor-DINOv2-518 adapter and feature extractor for animal re-ID."""
from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Sequence
import numpy as np
import torch
import torchvision.transforms as T
from PIL import Image
from member2_nisan.zebra_vision import normalize_image

MODEL_ID = "BVRA/MegaDescriptor-DINOv2-518"
MODEL_REVISION = "49d73b447ce335ff39f7d491e68485c4d0c52592"
CHECKPOINT_SHA256 = "2d4ccb1c61f2156dea8b93e98c1c65aff0e18cd76db55e83114baef6fad0d7b4"
CHECKPOINT_FILENAME = "megadescriptor-dinov2-518-49d73b44.bin"
EMBEDDING_DIM = 1024
INPUT_SIZE = 518

def _unit(vectors: np.ndarray) -> np.ndarray:
    x = np.asarray(vectors, dtype=np.float32)
    if x.ndim != 2 or not np.isfinite(x).all():
        raise ValueError("embeddings must be a finite 2D matrix")
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    if np.any(norms <= 1e-12):
        raise ValueError("zero embedding cannot be normalized")
    return x / norms

def get_dinov2_transform():
    return T.Compose([
        T.Resize((INPUT_SIZE, INPUT_SIZE), interpolation=T.InterpolationMode.BICUBIC),
        T.ToTensor(),
        T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])

def preprocess_dinov2_image(image: np.ndarray, transform=None) -> torch.Tensor:
    if transform is None:
        transform = get_dinov2_transform()
    a = normalize_image(image)
    if a.ndim == 2:
        a = np.repeat(a[:, :, None], 3, axis=2)
    pil = Image.fromarray(np.rint(a * 255).astype(np.uint8), mode="RGB")
    return transform(pil)

class MegaDescriptorDINOv2:
    """MegaDescriptor-DINOv2-518 feature extractor."""

    def __init__(self, model: torch.nn.Module, device: str = "cuda"):
        self.device = device
        self.model = model.eval().to(device)
        self.model_id = f"{MODEL_ID}@{MODEL_REVISION}"
        self.embedding_dim = EMBEDDING_DIM
        self.transform = get_dinov2_transform()

    def encode(self, images: Sequence[np.ndarray], batch_size: int = 4) -> np.ndarray:
        if not images or batch_size < 1:
            raise ValueError("nonempty images and positive batch_size required")
        result = []
        with torch.inference_mode():
            for offset in range(0, len(images), batch_size):
                batch = images[offset:offset + batch_size]
                tensors = [preprocess_dinov2_image(img, self.transform) for img in batch]
                batch_tensor = torch.stack(tensors).to(self.device)
                features = self.model(batch_tensor)
                result.append(features.detach().float().cpu().numpy())
        return _unit(np.concatenate(result, axis=0))

def load_megadescriptor_dinov2(checkpoint_path: str | Path, device: str = "cuda") -> MegaDescriptorDINOv2:
    """Load MegaDescriptor-DINOv2-518 from checkpoint after verifying hash."""
    import timm
    path = Path(checkpoint_path)
    if not path.is_file():
        raise FileNotFoundError(f"Checkpoint not found at: {path}")

    # Verify SHA256
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            hasher.update(chunk)
    actual_hash = hasher.hexdigest()
    if actual_hash != CHECKPOINT_SHA256:
        raise ValueError(f"Checkpoint SHA-256 mismatch: expected {CHECKPOINT_SHA256}, got {actual_hash}")

    if device.startswith("cuda") and not torch.cuda.is_available():
        raise ValueError("CUDA requested but not available; use device='cpu'")

    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    state_dict = ckpt["model"] if isinstance(ckpt, dict) and "model" in ckpt else ckpt
    clean_dict = {k.replace("backbone.", "").replace("module.", ""): v for k, v in state_dict.items()}

    model = timm.create_model("vit_large_patch14_dinov2", img_size=INPUT_SIZE, num_classes=0, pretrained=False)
    res = model.load_state_dict(clean_dict, strict=False)
    if res.missing_keys or res.unexpected_keys:
        raise RuntimeError(f"Unexpected keys loading DINOv2: missing {len(res.missing_keys)}, unexpected {len(res.unexpected_keys)}")

    return MegaDescriptorDINOv2(model, device=device)
