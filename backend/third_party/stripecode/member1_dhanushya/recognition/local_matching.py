"""Optional local keypoint matching: a visual descriptor baseline, not a trained zebra model."""
import cv2
import numpy as np
from member2_nisan.zebra_vision import normalize_image

def _gray(image):
    a=normalize_image(image)
    if a.ndim==3: a=cv2.cvtColor(a,cv2.COLOR_RGB2GRAY)
    return np.rint(a*255).astype(np.uint8)

def orb_similarity(query, gallery, *, max_features=1000, ratio=0.75):
    """Ratio-test fraction of query ORB descriptors with a matching gallery descriptor.

    Directional, not a calibrated probability; low-texture images may have zero keypoints.
    Geometric verification is not performed. An ORB match is not a stripe-specific proof.
    """
    if max_features < 2 or not 0 < ratio < 1: raise ValueError('invalid ORB parameters')
    orb=cv2.ORB_create(nfeatures=max_features)
    qa,qd=orb.detectAndCompute(_gray(query),None); ga,gd=orb.detectAndCompute(_gray(gallery),None)
    if qd is None or gd is None or len(gd)<2: return 0.0
    matches=cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(qd,gd,k=2)
    good=sum(1 for m in matches if len(m)==2 and m[0].distance < ratio*m[1].distance)
    return float(good/len(qd))

def partial_crops(image, fraction, positions=('center','top_left','top_right','bottom_left','bottom_right')):
    """Return named crops retaining approximately `fraction` of the image area."""
    a=normalize_image(image)
    if not 0 < fraction <= 1: raise ValueError('fraction must be in (0,1]')
    h,w=a.shape[:2]; ch=max(2,round(h*np.sqrt(fraction))); cw=max(2,round(w*np.sqrt(fraction)))
    coords={'center':((w-cw)//2,(h-ch)//2),'top_left':(0,0),'top_right':(w-cw,0),
            'bottom_left':(0,h-ch),'bottom_right':(w-cw,h-ch)}
    if not positions or any(p not in coords for p in positions): raise ValueError('invalid crop positions')
    return [{'position':p,'fraction':fraction,'box':(coords[p][0],coords[p][1],cw,ch),
             'image':a[coords[p][1]:coords[p][1]+ch,coords[p][0]:coords[p][0]+cw]} for p in positions]


def random_partial_crops(image, fraction, *, count=3, seed=42):
    """Geometric area-fraction crops at seeded image-coordinate positions.

    Crops are not anatomical labels. Repeated positions are possible for small images.
    """
    a=normalize_image(image)
    if not 0 < fraction <= 1 or not isinstance(count,int) or count<1: raise ValueError('invalid fraction or count')
    h,w=a.shape[:2]; ch=max(2,round(h*np.sqrt(fraction))); cw=max(2,round(w*np.sqrt(fraction)))
    rng=np.random.default_rng(seed);output=[]
    for _ in range(count):
        x=int(rng.integers(0,w-cw+1));y=int(rng.integers(0,h-ch+1))
        output.append({'position':'random','fraction':fraction,'box':(x,y,cw,ch),'image':a[y:y+ch,x:x+cw]})
    return output
