"""Scientific v1: image-space analysis; not biological or clinical ground truth."""
from pathlib import Path
import json,math
import cv2,numpy as np
from member2_nisan.zebra_vision import normalize_image,simulate_vision
from member2_nisan.stripe_analysis.features import estimate_orientation_field,estimate_spatial_frequency

WARNINGS=['Intensity-derived mask is not a validated anatomical or stripe segmentation.','Computational filters do not establish actual zebra perception.','Image-space frequencies are not physical distances or stripe widths.','A single image cannot establish individual discriminability.']

def _save(path,image):
 a=np.asarray(image)
 if np.issubdtype(a.dtype,np.floating):a=np.uint8(np.rint(np.clip(a,0,1)*255))
 if a.ndim==3:a=cv2.cvtColor(a,cv2.COLOR_RGB2BGR)
 if not cv2.imwrite(str(path),a):raise OSError('failed to write analysis image')

def _fft_summary(image):
 gray=cv2.cvtColor(image,cv2.COLOR_RGB2GRAY) if image.ndim==3 else image
 h,w=gray.shape;centered=(gray-gray.mean())*np.outer(np.hanning(h),np.hanning(w));spectrum=np.fft.fft2(centered);power=np.abs(spectrum)**2
 fy=np.fft.fftfreq(h)[:,None];fx=np.fft.fftfreq(w)[None,:];radius=np.hypot(fx,fy);angles=np.broadcast_to(np.mod(np.arctan2(fy,fx),np.pi),(h,w));bins=np.linspace(0,.5,11)
 radial=[float(power[(radius>=lo)&(radius<hi)].sum()) for lo,hi in zip(bins[:-1],bins[1:])];total=sum(radial);radial=[v/total if total else 0. for v in radial]
 orient=[]
 for lo,hi in zip(np.linspace(0,np.pi,9)[:-1],np.linspace(0,np.pi,9)[1:]):orient.append(float(power[(angles>=lo)&(angles<hi)&(radius>0)&(radius<=.5)].sum()))
 norm=sum(orient);orient=[x/norm if norm else 0. for x in orient]
 display=np.log1p(np.fft.fftshift(power));display/=display.max() or 1
 return {'radial_bins_cycles_per_pixel':bins.tolist(),'radial_energy_fraction':radial,'orientation_bins_radians':np.linspace(0,np.pi,9).tolist(),'orientation_energy_fraction':orient},display

def analyze_image(image,output_dir,*,roi=None,filter_type='gaussian',cutoff_cpp=.06,band_low_cpp=.03,source_reference=None,recognizer=None,candidate_identity=None):
 """Analyze RGB image and write a new local output directory, never overwriting.

 ROI is [x,y,width,height] in input pixels. Returned paths are local file references.
 Optional recognizer must implement identify/analyze; scores preserve its semantics.
 """
 a=normalize_image(image)
 if a.ndim==2:a=np.repeat(a[:,:,None],3,axis=2)
 h,w=a.shape[:2]
 if max(h,w)>8192:raise ValueError('image exceeds supported 8192 pixel dimension')
 if roi is None:roi=[0,0,w,h]
 if not isinstance(roi,(list,tuple)) or len(roi)!=4 or any(not isinstance(x,int) or isinstance(x,bool) for x in roi):raise ValueError('roi must contain four integer coordinates')
 x,y,rw,rh=roi
 if x<0 or y<0 or rw<16 or rh<16 or x+rw>w or y+rh>h:raise ValueError('ROI must fit image and be at least 16x16')
 if not isinstance(cutoff_cpp,(int,float)) or not math.isfinite(cutoff_cpp) or not 1e-5<=cutoff_cpp<=.5:raise ValueError('invalid cutoff')
 crop=a[y:y+rh,x:x+rw]
 if filter_type in ('gaussian','butterworth'):
  sim=simulate_vision(crop,mode='exploratory',detail_cutoff_cpp=cutoff_cpp,filter_type=filter_type);filtered=sim['image'];filter_metadata=sim['metadata']
 elif filter_type=='bandpass':
  if not isinstance(band_low_cpp,(int,float)) or not 1e-5<=band_low_cpp<cutoff_cpp:raise ValueError('band low cutoff must be positive and below high cutoff')
  high=simulate_vision(crop,mode='exploratory',detail_cutoff_cpp=cutoff_cpp)['image'];low=simulate_vision(crop,mode='exploratory',detail_cutoff_cpp=band_low_cpp)['image'];filtered=np.clip(.5+high-low,0,1);filter_metadata={'mode':'image_space_bandpass','low_cycles_per_pixel':band_low_cpp,'high_cycles_per_pixel':cutoff_cpp,'display_midpoint':.5}
 else:raise ValueError('filter_type must be gaussian, butterworth or bandpass')
 field=estimate_orientation_field(crop);freq=estimate_spatial_frequency(crop);spectrum,plot=_fft_summary(crop);gray=cv2.cvtColor(crop,cv2.COLOR_RGB2GRAY)
 _,mask=cv2.threshold(np.uint8(gray*255),0,255,cv2.THRESH_BINARY_INV|cv2.THRESH_OTSU)
 hsv=np.zeros((rh,rw,3),np.uint8);hsv[:,:,0]=np.uint8(field['orientation_radians']/np.pi*179);hsv[:,:,1]=255;hsv[:,:,2]=np.uint8(np.clip(field['coherence'],0,1)*255);orientation=cv2.cvtColor(hsv,cv2.COLOR_HSV2RGB);orientation[~field['valid_mask']]=0
 # One-image control quantifies sensitivity only, not identity information.
 rng=np.random.default_rng(20261121);shuffled=gray.ravel()[rng.permutation(gray.size)].reshape(gray.shape);control,_=_fft_summary(shuffled)
 evidence=None
 if candidate_identity is not None:
  if recognizer is None:raise ValueError('candidate identity requires a recognizer')
  evidence=recognizer.analyze(crop,map_identity=candidate_identity)
 ranking=recognizer.identify(crop) if recognizer is not None else None
 out=Path(output_dir);out.mkdir(parents=True,exist_ok=False)
 for name,im in [('original_roi.png',crop),('filtered.png',filtered),('intensity_mask.png',mask),('orientation.png',orientation),('spectrum.png',plot)]:_save(out/name,im)
 result={'schema_version':'stripecode.science.v1','source_reference':source_reference,'roi':list(roi),'files':{k:str(out/v) for k,v in {'original_roi':'original_roi.png','filtered':'filtered.png','intensity_mask':'intensity_mask.png','orientation':'orientation.png','spectrum':'spectrum.png'}.items()},'frequency':freq,'spectrum':spectrum,'negative_control':{'method':'seeded pixel shuffle','seed':20261121,'spectrum':control},'measurements':{'mean_intensity':float(gray.mean()),'intensity_std':float(gray.std()),'dark_fraction':float((mask>0).mean()),'orientation_valid_fraction':float(field['valid_mask'].mean())},'filter':filter_metadata,'ranking':ranking,'candidate_evidence':evidence,'warnings':WARNINGS}
 with (out/'analysis.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
 return result

def safe_analyze(*args,**kwargs):
 """Return versioned JSON-compatible success/error envelope."""
 try:return {'schema_version':'stripecode.science.envelope.v1','ok':True,'result':analyze_image(*args,**kwargs)}
 except (ValueError,TypeError,FileNotFoundError,FileExistsError,OSError) as e:return {'schema_version':'stripecode.science.envelope.v1','ok':False,'error':{'type':type(e).__name__,'message':str(e)}}
