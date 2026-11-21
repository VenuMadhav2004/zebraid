"""Animal re-identification using normalized embeddings and an injectable encoder."""
from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol, Sequence
import hashlib
import time
import numpy as np
import cv2
from member2_nisan.zebra_vision import normalize_image

MODEL_ID = 'BVRA/MegaDescriptor-L-384'
MODEL_REVISION = '33b3c6f4ee0c386a4126cc3dcd23843920613fa1'
CHECKPOINT_SHA256 = 'ccfe757f50f7984a115ffe00921cd4c09e260e645215463b23814586040227a3'

class Encoder(Protocol):
    model_id: str
    def encode(self, images: Sequence[np.ndarray], batch_size: int = 8) -> np.ndarray: ...

def _unit(vectors):
    x=np.asarray(vectors,dtype=np.float32)
    if x.ndim != 2 or not np.isfinite(x).all(): raise ValueError('embeddings must be a finite 2D matrix')
    norms=np.linalg.norm(x,axis=1,keepdims=True)
    if np.any(norms <= 1e-12): raise ValueError('zero embedding cannot be normalized')
    return x/norms

PREPROCESSING_OPTIONS = ('model_card', 'checkpoint_config')

def preprocess_megadescriptor(image, interpretation='model_card'):
    """Apply one explicitly documented interpretation to an RGB image.

    The config interpretation follows timm's evaluation transform for crop_pct .9,
    bicubic resizing of the shorter edge to floor(384/.9), and a 384 center crop.
    """
    from PIL import Image
    from torchvision import transforms
    from torchvision.transforms import InterpolationMode
    if interpretation not in PREPROCESSING_OPTIONS: raise ValueError('unknown preprocessing interpretation')
    a=normalize_image(image)
    if a.ndim==2: a=np.repeat(a[:,:,None],3,axis=2)
    pil=Image.fromarray(np.rint(a*255).astype(np.uint8),mode='RGB')
    if interpretation=='model_card':
        transform=transforms.Compose([transforms.Resize((384,384),interpolation=InterpolationMode.BILINEAR),transforms.ToTensor(),transforms.Normalize([.5]*3,[.5]*3)])
    else:
        transform=transforms.Compose([transforms.Resize(int(384/.9),interpolation=InterpolationMode.BICUBIC),transforms.CenterCrop(384),transforms.ToTensor(),transforms.Normalize([.485,.456,.406],[.229,.224,.225])])
    return transform(pil)

class MegaDescriptor:
    """MegaDescriptor-L with an explicit preprocessing interpretation."""
    def __init__(self, model, device, preprocessing='model_card'):
        if preprocessing not in PREPROCESSING_OPTIONS: raise ValueError('unknown preprocessing interpretation')
        self.model=model.eval().to(device); self.device=device
        self.preprocessing=preprocessing
        suffix='card-384-mean0.5' if preprocessing=='model_card' else 'config-bicubic-centercrop-imagenet'
        self.model_id=f'{MODEL_ID}@{MODEL_REVISION}:{suffix}'
    def encode(self, images: Sequence[np.ndarray], batch_size: int = 8) -> np.ndarray:
        import torch
        if not images or batch_size < 1: raise ValueError('nonempty images and positive batch_size required')
        result=[]
        with torch.inference_mode():
            for offset in range(0,len(images),batch_size):
                tensors=[]
                for image in images[offset:offset+batch_size]:
                    tensors.append(preprocess_megadescriptor(image,self.preprocessing))
                output=self.model(torch.stack(tensors).to(self.device))
                result.append(output.detach().float().cpu().numpy())
        return _unit(np.concatenate(result))

def load_recognition_model(checkpoint_path: str | Path | Mapping, device: str = 'cpu', preprocessing: str = 'model_card') -> MegaDescriptor:
    """Load pinned official checkpoint, verifying SHA-256 before deserializing.

    This checkpoint is CC BY-NC 4.0 and the model card reports broad re-ID pretraining;
    test datasets may overlap its pretraining. No network download is performed here.
    A mapping may instead specify ``checkpoint_path``, ``device``, ``preprocessing``
    and ``model_type`` (currently only ``pretrained``). The existing path-based
    interface and its default preprocessing are unchanged.
    """
    if isinstance(checkpoint_path, Mapping):
        config=checkpoint_path
        if set(config)-{'checkpoint_path','model_type','device','preprocessing'}: raise ValueError('unknown model configuration key')
        if config.get('model_type','pretrained')!='pretrained': raise ValueError('only the pinned pretrained model is available')
        if not config.get('checkpoint_path'): raise ValueError('checkpoint_path required')
        device=config.get('device',device);preprocessing=config.get('preprocessing',preprocessing);checkpoint_path=config['checkpoint_path']
    if not isinstance(device,str) or preprocessing not in PREPROCESSING_OPTIONS: raise ValueError('invalid model configuration')
    import torch, timm
    path=Path(checkpoint_path)
    if not path.is_file(): raise FileNotFoundError(f'Checkpoint not found: {path}')
    digest=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(8*1024*1024),b''): digest.update(chunk)
    if digest.hexdigest()!=CHECKPOINT_SHA256: raise ValueError('checkpoint SHA-256 mismatch')
    if device.startswith('cuda') and not torch.cuda.is_available(): raise ValueError('CUDA requested but unavailable')
    model=timm.create_model('swin_large_patch4_window12_384',num_classes=0,pretrained=False)
    checkpoint=torch.load(path,map_location='cpu',weights_only=True)
    from timm.models.swin_transformer import checkpoint_filter_fn
    state=checkpoint_filter_fn(checkpoint, model)
    result=model.load_state_dict(state,strict=False)
    if result.missing_keys or result.unexpected_keys: raise RuntimeError(f'incompatible checkpoint: {len(result.missing_keys)} missing, {len(result.unexpected_keys)} unexpected keys')
    del checkpoint, state
    return MegaDescriptor(model,device,preprocessing)

@dataclass(frozen=True)
class Gallery:
    embeddings: np.ndarray
    identities: tuple[str,...]
    model_id: str
    sample_ids: tuple[str,...]
    fingerprints: tuple[str,...]

def build_gallery(images: Sequence[np.ndarray], identities: Sequence[str], model: Encoder, *, sample_ids=None, batch_size=8, cache_path=None) -> Gallery:
    """Encode reference images and optionally cache embeddings as a non-pickle NPZ."""
    if not len(images) or len(images)!=len(identities) or any(not str(x).strip() for x in identities): raise ValueError('aligned images and identities required')
    ids=tuple(str(x) for x in identities); sample_ids=tuple(str(i) for i in (sample_ids if sample_ids is not None else range(len(images))))
    if len(sample_ids)!=len(images) or len(set(sample_ids))!=len(images): raise ValueError('sample IDs must be unique and aligned')
    fingerprints=[]
    for image in images:
        a=np.ascontiguousarray(normalize_image(image)); fingerprints.append(hashlib.sha256(str(a.shape).encode()+a.tobytes()).hexdigest())
    if cache_path is not None and Path(cache_path).is_file():
        with np.load(cache_path,allow_pickle=False) as data:
            if (str(data['model_id'].item()) == model.model_id and data['identities'].tolist()==list(ids)
                and data['sample_ids'].tolist()==list(sample_ids) and data['fingerprints'].tolist()==fingerprints):
                return Gallery(_unit(data['embeddings']),ids,model.model_id,sample_ids,tuple(fingerprints))
    embeddings=_unit(model.encode(images,batch_size=batch_size))
    if len(embeddings)!=len(images): raise ValueError('encoder returned incorrect batch size')
    gallery=Gallery(embeddings,ids,model.model_id,sample_ids,tuple(fingerprints))
    if cache_path is not None:
        path=Path(cache_path); path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('wb') as f: np.savez_compressed(f,embeddings=embeddings,identities=np.asarray(ids),sample_ids=np.asarray(sample_ids),fingerprints=np.asarray(fingerprints),model_id=np.asarray(model.model_id))
    return gallery

def score_all_identities(image: np.ndarray, gallery: Gallery, model: Encoder) -> list[dict]:
    if gallery.model_id!=model.model_id: raise ValueError('gallery and query model differ')
    q=_unit(model.encode([image],batch_size=1))[0]; vectors=_unit(gallery.embeddings)
    if vectors.shape[1]!=q.shape[0] or len(vectors)!=len(gallery.identities): raise ValueError('gallery dimensions do not match model')
    scores=vectors@q; best={}
    for identity, score in zip(gallery.identities,scores): best[identity]=max(best.get(identity,-float('inf')),float(score))
    return [{'identity':i,'similarity':s} for i,s in sorted(best.items(),key=lambda item:(-item[1],item[0]))]

def identify_zebra(image: np.ndarray, gallery: Gallery, model: Encoder, *, top_k=3, unknown_threshold=None) -> dict:
    """Return identity-level cosine similarities; threshold must be externally validated."""
    if not isinstance(top_k,int) or top_k<1: raise ValueError('top_k must be positive')
    if unknown_threshold is not None and (not np.isfinite(unknown_threshold) or not -1 <= unknown_threshold <= 1): raise ValueError('invalid threshold')
    start=time.perf_counter(); scores=score_all_identities(image,gallery,model)
    margin=scores[0]['similarity']-scores[1]['similarity'] if len(scores)>1 else None
    return {'matches':scores[:top_k], 'margin':margin, 'unknown':None if unknown_threshold is None else scores[0]['similarity']<unknown_threshold,
            'seconds':time.perf_counter()-start,'model_id':model.model_id, 'score_type':'cosine similarity, not probability'}

def evaluate_reidentification(query_images, query_identities, gallery, model, *, metadata):
    """Evaluate only after source/session leakage validation on combined images and metadata.

    Metadata must correspond to gallery images followed by query images. Gallery images
    must be supplied in metadata as 'image' arrays for duplicate checks.
    """
    from member2_nisan.experiments import validate_partitions
    if len(query_images)!=len(query_identities) or not query_images: raise ValueError('nonempty aligned queries required')
    if len(metadata)!=len(gallery.identities)+len(query_images): raise ValueError('metadata must include all gallery and query records')
    for i,r in enumerate(metadata):
        expected='gallery' if i<len(gallery.identities) else 'query'
        label=gallery.identities[i] if expected=='gallery' else str(query_identities[i-len(gallery.identities)])
        if r.get('partition')!=expected or str(r.get('identity'))!=label or 'image' not in r: raise ValueError('metadata does not match gallery/query order')
    all_images=[r['image'] for r in metadata]
    for im, expected in zip(all_images[:len(gallery.identities)], gallery.fingerprints):
        a=np.ascontiguousarray(normalize_image(im)); actual=hashlib.sha256(str(a.shape).encode()+a.tobytes()).hexdigest()
        if actual != expected: raise ValueError('gallery metadata image mismatch')
    for a,b in zip(all_images[len(gallery.identities):],query_images):
        if not np.array_equal(a,b): raise ValueError('query metadata image mismatch')
    validate_partitions(all_images,metadata)
    rows=[]
    for image, truth in zip(query_images,query_identities):
        scores=score_all_identities(image,gallery,model); correct=next(x['similarity'] for x in scores if x['identity']==str(truth))
        impostor=max(x['similarity'] for x in scores if x['identity']!=str(truth))
        rank=1+sum(x['similarity']>=correct for x in scores if x['identity']!=str(truth))
        rows.append({'identity':str(truth),'rank':rank,'margin':correct-impostor,'genuine':correct,'impostor':impostor})
    return {'queries':rows,'query_count':len(rows),'rank1':sum(r['rank']==1 for r in rows)/len(rows),
            'rank3':sum(r['rank']<=3 for r in rows)/len(rows),'mean_margin':float(np.mean([r['margin'] for r in rows]))}
