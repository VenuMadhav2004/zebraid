"""Descriptive stripe measurements: confidence is not a biological certainty."""
import cv2
import numpy as np
from scipy.ndimage import gaussian_filter
from member2_nisan.zebra_vision.simulator import normalize_image, image_pyramid

def grayscale(image):
    a = normalize_image(image)
    return cv2.cvtColor(a, cv2.COLOR_RGB2GRAY) if a.ndim == 3 else a

def estimate_orientation_field(image, sigma=2.0):
    if sigma <= 0: raise ValueError('sigma must be positive')
    gray = grayscale(image)
    gy, gx = np.gradient(gray.astype(float))
    xx = gaussian_filter(gx*gx, sigma); yy = gaussian_filter(gy*gy, sigma); xy = gaussian_filter(gx*gy, sigma)
    energy = xx + yy
    coherence = np.sqrt((xx-yy)**2 + 4*xy**2) / (energy + 1e-12)
    # Tangent to the intensity gradient, axial orientation in [0, pi).
    angle = (0.5*np.arctan2(2*xy, xx-yy) + np.pi/2) % np.pi
    valid = (energy > 1e-5) & (coherence >= 0.3)
    return {'orientation_radians': angle, 'coherence': coherence, 'valid_mask': valid, 'energy': energy}

def estimate_spatial_frequency(image):
    gray = grayscale(image).astype(float); h,w = gray.shape
    if min(h,w) < 8: return {'cycles_per_pixel': None, 'period_pixels': None, 'confidence': 0.0}
    a = gray - gray.mean(); a *= np.outer(np.hanning(h), np.hanning(w))
    power = abs(np.fft.fft2(a))**2
    fy=np.fft.fftfreq(h)[:,None]; fx=np.fft.fftfreq(w)[None,:]; radius=np.hypot(fx,fy)
    power[radius < max(2/h,2/w)] = 0
    if power.sum() < 1e-12: return {'cycles_per_pixel': None, 'period_pixels': None, 'confidence': 0.0}
    idx=np.unravel_index(np.argmax(power),power.shape); frequency=float(radius[idx]); confidence=float(power[idx]/power.sum())
    return {'cycles_per_pixel': frequency, 'period_pixels': 1/frequency, 'confidence': confidence,
            'caveat':'global FFT peak; complex scenes, curvature and windows may bias estimate'}

def gabor_bank(image, wavelengths=(4., 8., 16.), orientations=8):
    a=grayscale(image)
    if not wavelengths or any(w < 2 for w in wavelengths) or orientations < 1: raise ValueError('invalid Gabor parameters')
    energies=[]
    for wavelength in wavelengths:
        for theta in np.linspace(0,np.pi,orientations,endpoint=False):
            sigma=.56*wavelength; k=min(101, max(5, int(np.ceil(6*sigma)) | 1))
            re=cv2.getGaborKernel((k,k),sigma,float(theta),wavelength,.5,0,ktype=cv2.CV_32F)
            im=cv2.getGaborKernel((k,k),sigma,float(theta),wavelength,.5,np.pi/2,ktype=cv2.CV_32F)
            re-=re.mean(); im-=im.mean()
            norm=np.sqrt((re*re+im*im).sum()); re/=norm; im/=norm
            response=np.hypot(cv2.filter2D(a,-1,re),cv2.filter2D(a,-1,im))
            energies.append({'wavelength_pixels':float(wavelength),'normal_angle_radians':float(theta),'mean_energy':float(response.mean())})
    return energies

def extract_stripe_features(image, config=None):
    cfg=config or {}; field=estimate_orientation_field(image, cfg.get('sigma',2)); valid=field['valid_mask']
    hist,_=np.histogram(field['orientation_radians'][valid], bins=cfg.get('orientation_bins',12), range=(0,np.pi), weights=field['coherence'][valid])
    hist=hist/(hist.sum() or 1)
    freq=estimate_spatial_frequency(image)
    return {'orientation_histogram':hist, 'orientation_field':field, 'frequency':freq,
            'gabor':gabor_bank(image,tuple(cfg.get('wavelengths',(4.,8.,16.)))),
            'valid_fraction':float(valid.mean()), 'stripe_width_estimate_pixels': None if freq['period_pixels'] is None else freq['period_pixels']/2,
            'width_caveat':'half-period assumes equal-width alternating bars; unreliable for irregular stripes'}

def extract_emergent_pattern(image, sigma=4.):
    a=normalize_image(image)
    if sigma <= 0: raise ValueError('sigma must be positive')
    return gaussian_filter(a, (sigma,sigma) if a.ndim==2 else (sigma,sigma,0)).astype(np.float32)

def multiscale_features(image, levels=3):
    return [extract_stripe_features(level) for level in image_pyramid(image,levels)]

def compare_stripe_structure(original, transformed):
    a,b=extract_stripe_features(original),extract_stripe_features(transformed)
    return {'original':a, 'transformed':b, 'orientation_histogram_l1':float(np.abs(a['orientation_histogram']-b['orientation_histogram']).sum())}


def local_orientation_histograms(image, *, cell_size=32, bins=12, sigma=2.0):
    """Axial orientation histograms in non-overlapping cells, weighted by coherence.

    Returns histograms and valid-pixel fractions; empty cells have all-zero histograms.
    Partial boundary cells are retained. These are descriptors, not zebra attention.
    """
    if not isinstance(cell_size, int) or cell_size < 2 or not isinstance(bins, int) or bins < 2:
        raise ValueError('cell_size and bins must be integers >= 2')
    field = estimate_orientation_field(image, sigma)
    angle, coherence, valid = field['orientation_radians'], field['coherence'], field['valid_mask']
    h, w = angle.shape
    ny, nx = (h + cell_size - 1)//cell_size, (w + cell_size - 1)//cell_size
    histograms = np.zeros((ny, nx, bins), dtype=float)
    valid_fraction = np.zeros((ny, nx), dtype=float)
    for iy in range(ny):
        for ix in range(nx):
            sl = (slice(iy*cell_size, min((iy+1)*cell_size, h)), slice(ix*cell_size, min((ix+1)*cell_size, w)))
            mask = valid[sl]
            valid_fraction[iy, ix] = mask.mean()
            hist, _ = np.histogram(angle[sl][mask], bins=bins, range=(0, np.pi), weights=coherence[sl][mask])
            if hist.sum(): histograms[iy, ix] = hist / hist.sum()
    return {'histograms': histograms, 'valid_fraction': valid_fraction, 'cell_size': cell_size, 'bins': bins}


def save_stripe_flow(image, output_path, *, step=16, sigma=2.0):
    """Save intensity, gradient magnitude and confident axial stripe-flow directions."""
    from pathlib import Path
    import matplotlib.pyplot as plt
    if not isinstance(step, int) or step < 1: raise ValueError('step must be positive')
    gray = grayscale(image)
    field = estimate_orientation_field(image, sigma)
    y, x = np.mgrid[0:gray.shape[0]:step, 0:gray.shape[1]:step]
    angles = field['orientation_radians'][::step, ::step]
    valid = field['valid_mask'][::step, ::step]
    fig, axes = plt.subplots(1, 2, figsize=(10, 5))
    axes[0].imshow(np.sqrt(field['energy']), cmap='magma'); axes[0].set_title('Gradient energy (smoothed)')
    axes[1].imshow(gray, cmap='gray', vmin=0, vmax=1)
    axes[1].quiver(x[valid], y[valid], np.cos(angles[valid]), np.sin(angles[valid]),
                   color='cyan', pivot='middle', angles='xy', scale_units='xy', scale=0.12,
                   headlength=0, headwidth=1, headaxislength=0)
    axes[1].set_title('Estimated axial stripe flow')
    for ax in axes: ax.axis('off')
    fig.tight_layout(); output = Path(output_path); output.parent.mkdir(parents=True, exist_ok=True)
    try: fig.savefig(output, dpi=120)
    finally: plt.close(fig)
    return str(output)


def estimate_local_frequency_map(image, *, patch_size=32, stride=16, min_peak_fraction=.02):
    """Patchwise FFT frequencies in cycles/pixel with an explicit reliability mask.

    Values measure dominant image texture, not necessarily zebra stripes. Missing or
    weak peaks are NaN. Background and curved/junction regions require segmentation
    and manual review; no conversion to physical stripe width is implied.
    """
    a=grayscale(image); h,w=a.shape
    if not isinstance(patch_size,int) or patch_size<8 or patch_size>min(h,w): raise ValueError('patch_size must be >=8 and fit image')
    if not isinstance(stride,int) or stride<1 or stride>patch_size: raise ValueError('invalid stride')
    if not np.isfinite(min_peak_fraction) or not 0<=min_peak_fraction<=1: raise ValueError('invalid minimum peak fraction')
    ys=sorted(set(list(range(0,h-patch_size+1,stride))+[h-patch_size]));xs=sorted(set(list(range(0,w-patch_size+1,stride))+[w-patch_size]))
    frequency=np.full((len(ys),len(xs)),np.nan);confidence=np.zeros_like(frequency);valid=np.zeros_like(frequency,dtype=bool)
    for iy,y in enumerate(ys):
        for ix,x in enumerate(xs):
            result=estimate_spatial_frequency(a[y:y+patch_size,x:x+patch_size]); conf=result['confidence'];confidence[iy,ix]=conf
            if result['cycles_per_pixel'] is not None and conf>=min_peak_fraction:
                frequency[iy,ix]=result['cycles_per_pixel'];valid[iy,ix]=True
    return {'cycles_per_pixel':frequency,'confidence':confidence,'valid_mask':valid,'x':np.asarray(xs),'y':np.asarray(ys),
            'patch_size':patch_size,'caveat':'Dominant local image texture, not a validated stripe-frequency map.'}


def candidate_junction_mask(image, *, sigma=2., min_energy=1e-5, max_coherence=.3):
    """Flag textured low-coherence pixels for review; not verified stripe junctions."""
    if min_energy<0 or not 0<=max_coherence<=1: raise ValueError('invalid threshold')
    f=estimate_orientation_field(image,sigma)
    return {'candidate_mask':(f['energy']>=min_energy)&(f['coherence']<=max_coherence),
            'energy':f['energy'],'coherence':f['coherence'],
            'warning':'Corners, noise and background can be flagged; no junction classification.'}
