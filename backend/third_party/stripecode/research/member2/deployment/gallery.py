"""Single-writer local gallery cache for an existing v1 embedding encoder."""
import hashlib,os,tempfile
from pathlib import Path
import numpy as np
from member1_dhanushya.recognition.engine import Gallery,identify_zebra
from member2_nisan.zebra_vision import normalize_image

class CpuGalleryIndex:
 """Persist non-pickle vectors atomically; callers provide access control and locking."""
 def __init__(self,model,path):
  self.model=model;self.path=Path(path);self.entries=[]
  if self.path.exists():self._load()
 def _load(self):
  with np.load(self.path,allow_pickle=False) as d:
   if str(d['model_id'].item())!=self.model.model_id:raise ValueError('gallery model/preprocessing mismatch')
   ids=d['identities'].tolist();samples=d['sample_ids'].tolist();fingerprints=d['fingerprints'].tolist();vectors=np.asarray(d['embeddings'],dtype=np.float32)
  if vectors.ndim!=2 or not np.isfinite(vectors).all() or not(len(ids)==len(samples)==len(fingerprints)==len(vectors)) or len(set(samples))!=len(samples):raise ValueError('invalid gallery cache')
  if any(not isinstance(x,str) or not x.strip() for x in ids+samples) or any(not isinstance(x,str) or len(x)!=64 for x in fingerprints):raise ValueError('invalid gallery metadata')
  if len(vectors) and (not vectors.shape[1] or np.any(np.abs(np.linalg.norm(vectors,axis=1)-1)>1e-4)):raise ValueError('invalid gallery embeddings')
  self.entries=[(s,i,f,v.copy()) for s,i,f,v in zip(samples,ids,fingerprints,vectors)]
 def _persist(self,entries):
  self.path.parent.mkdir(parents=True,exist_ok=True);dim=len(entries[0][3]) if entries else 0;vectors=np.stack([e[3] for e in entries]) if entries else np.empty((0,dim),np.float32)
  tmp=None
  try:
   with tempfile.NamedTemporaryFile(mode='w+b',prefix='.gallery-',dir=self.path.parent,delete=False) as f:
    tmp=f.name;os.fchmod(f.fileno(),0o600);np.savez_compressed(f,model_id=np.asarray(self.model.model_id),identities=np.asarray([e[1] for e in entries],dtype=str),sample_ids=np.asarray([e[0] for e in entries],dtype=str),fingerprints=np.asarray([e[2] for e in entries],dtype=str),embeddings=vectors);f.flush();os.fsync(f.fileno())
   os.replace(tmp,self.path);tmp=None
  finally:
   if tmp and os.path.exists(tmp):os.unlink(tmp)
  self.entries=entries
 def register(self,sample_id,identity,image,*,replace=False):
  if not isinstance(sample_id,str) or not sample_id.strip() or not isinstance(identity,str) or not identity.strip():raise ValueError('sample_id and identity must be nonempty strings')
  positions=[i for i,e in enumerate(self.entries) if e[0]==sample_id]
  if positions and not replace:raise ValueError('sample already exists')
  normalized=np.ascontiguousarray(normalize_image(image));fingerprint=hashlib.sha256(str(normalized.shape).encode()+normalized.tobytes()).hexdigest();vectors=np.asarray(self.model.encode([image],batch_size=1),dtype=np.float32)
  if vectors.ndim!=2 or vectors.shape[0]!=1 or not vectors.shape[1] or not np.isfinite(vectors).all():raise ValueError('invalid encoder output')
  v=vectors[0];norm=float(np.linalg.norm(v))
  if norm<=1e-12:raise ValueError('zero embedding')
  v=v/norm
  if self.entries and len(v)!=len(self.entries[0][3]):raise ValueError('embedding dimension mismatch')
  updated=list(self.entries);item=(sample_id,identity,fingerprint,v)
  if positions:updated[positions[0]]=item
  else:updated.append(item)
  self._persist(updated)
 def remove(self,sample_id):
  if not any(e[0]==sample_id for e in self.entries):raise KeyError(sample_id)
  self._persist([e for e in self.entries if e[0]!=sample_id])
 def gallery(self):
  if not self.entries:raise ValueError('gallery is empty')
  return Gallery(np.stack([e[3] for e in self.entries]),tuple(e[1] for e in self.entries),self.model.model_id,tuple(e[0] for e in self.entries),tuple(e[2] for e in self.entries))
 def identify(self,image,*,top_k=3):return identify_zebra(image,self.gallery(),self.model,top_k=top_k)
