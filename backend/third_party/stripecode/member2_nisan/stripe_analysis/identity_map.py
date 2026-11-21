"""Sliding window model-based discrimination maps; not animal gaze maps."""
from pathlib import Path
import csv
import numpy as np
import matplotlib.pyplot as plt
from member2_nisan.zebra_vision.simulator import normalize_image

def _starts(length, size, stride):
    return sorted(set(list(range(0,length-size+1,stride)) + [length-size]))

def generate_identity_map(image, identity_scoring_callback, *, patch_sizes=(64,), stride=32, validity_mask=None, min_valid_fraction=0.5):
    """Callback(patch, (x,y,w,h)) returns {'correct': float, 'impostors': sequence[float]}."""
    a=normalize_image(image); h,w=a.shape[:2]
    if not callable(identity_scoring_callback): raise ValueError('a real identity scorer callback is required')
    if validity_mask is None: mask=np.ones((h,w),dtype=bool)
    else:
        mask=np.asarray(validity_mask)
        if mask.shape!=(h,w) or mask.dtype!=bool: raise ValueError('validity_mask must be an H×W boolean array')
    if not np.isfinite(min_valid_fraction) or not 0<=min_valid_fraction<=1: raise ValueError('invalid minimum valid fraction')
    if not isinstance(stride,int) or stride<1: raise ValueError('stride must be positive integer')
    total=np.zeros((h,w),float); count=np.zeros((h,w),int); rows=[]
    for size in patch_sizes:
        if not isinstance(size,int) or size<2 or size>min(h,w): raise ValueError('patch size must fit image')
        if stride > size: raise ValueError('stride cannot exceed patch size; coverage would be incomplete')
        for y in _starts(h,size,stride):
            for x in _starts(w,size,stride):
                valid_fraction=float(mask[y:y+size,x:x+size].mean())
                if valid_fraction<min_valid_fraction or valid_fraction==0: continue
                scores=identity_scoring_callback(a[y:y+size,x:x+size],(x,y,size,size))
                imp=np.asarray(scores['impostors'],dtype=float); correct=float(scores['correct'])
                if imp.ndim != 1 or imp.size == 0 or not np.all(np.isfinite(imp)) or not np.isfinite(correct): raise ValueError('scorer must return finite correct and impostor scores')
                margin=correct-float(imp.max()); rows.append({'x':x,'y':y,'width':size,'height':size,'correct':correct,'best_impostor':float(imp.max()),'margin':margin,'valid_fraction':valid_fraction})
                patch_mask=mask[y:y+size,x:x+size]
                total[y:y+size,x:x+size]+=margin*patch_mask; count[y:y+size,x:x+size]+=patch_mask
    if not rows: raise ValueError('at least one patch size is required')
    covered=count>0; raw=np.divide(total,count,out=np.zeros_like(total),where=covered)
    lo,hi=float(raw[covered].min()),float(raw[covered].max())
    normalized=np.zeros_like(raw)
    if hi>lo: normalized[covered]=(raw[covered]-lo)/(hi-lo)
    return {'margin_map':raw,'normalized_map':normalized,'coverage':count,'valid_mask':covered,'patches':rows,
            'warning':'Model-based score margin, not evidence of where a zebra looks. Min-max normalization is image-relative.'}

def export_identity_map(result, image, output_prefix):
    prefix=Path(output_prefix); prefix.parent.mkdir(parents=True,exist_ok=True)
    with prefix.with_suffix('.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(result['patches'][0])); writer.writeheader(); writer.writerows(result['patches'])
    fig,ax=plt.subplots(); ax.imshow(normalize_image(image),cmap='gray'); ax.imshow(np.ma.masked_where(~result['valid_mask'],result['normalized_map']),cmap='magma',alpha=.5,vmin=0,vmax=1); ax.axis('off'); fig.savefig(prefix.with_suffix('.png'),bbox_inches='tight'); plt.close(fig)
    return {'csv':str(prefix.with_suffix('.csv')),'image':str(prefix.with_suffix('.png'))}
