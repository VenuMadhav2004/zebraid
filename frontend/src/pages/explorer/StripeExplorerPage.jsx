import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import AnalysisDrawer from '../../components/explorer/AnalysisDrawer.jsx'
import AnalysisHistory from '../../components/explorer/AnalysisHistory.jsx'
import ArtifactGallery from '../../components/explorer/ArtifactGallery.jsx'
import { ImageViewport } from '../../components/explorer/ImageViewport.jsx'
import LibraryPickerDialog from '../../components/explorer/LibraryPickerDialog.jsx'
import { ImageInfoPanel, SpatialPanel } from '../../components/explorer/Panels.jsx'
import { CombinedCaveatBanner, FrequencyResultPanel, MorphologyResultPanel } from '../../components/explorer/ScientificResults.jsx'
import { inferPairFromHistory, resolveDisplayedResults, retryRequest } from '../../lib/analysisResults.js'
import { GalleryIcon, SparkleIcon, StripesIcon } from '../../components/icons.jsx'
import { Button, Card, EmptyState, ErrorState, Spinner } from '../../components/ui/index.js'
import { useToast } from '../../hooks/toastContext.js'
import { cn } from '../../lib/cn.js'
import {
  deleteAnalysis,
  friendlyAnalysisError,
  getAnalysisCapability,
  listAnalyses,
  submitCombinedAnalysis,
  submitFrequency,
  submitMorphology,
  waitForAnalysis,
} from '../../services/stripeAnalysis.js'
import { ALLOWED_IMAGE_TYPES, checkImageFile, imagesApi } from '../../services/zebraid.js'

/** Decode an image to learn its real pixel size (browser applies EXIF orientation). */
function useDecodedSize(url) {
  const [state, setState] = useState({ url: null, size: null, error: null })
  useEffect(() => {
    if (!url) return
    let active = true
    const img = new Image()
    img.onload = () => active && setState({ url, size: { width: img.naturalWidth, height: img.naturalHeight }, error: null })
    img.onerror = () => active && setState({ url, size: null, error: 'The image could not be decoded.' })
    img.src = url
    return () => {
      active = false
    }
  }, [url])
  return state.url === url ? state : { url, size: null, error: null }
}

/** Crop the ROI from a stored image (fresh CORS-enabled signed URL) into a File of the same type. */
async function cropToFile(record, roi) {
  const { url } = await imagesApi.url(record.id, 300)
  const img = new Image()
  img.crossOrigin = 'anonymous'
  await new Promise((res, rej) => {
    img.onload = res
    img.onerror = () => rej(new Error('Could not load the image for cropping.'))
    img.src = url
  })
  const canvas = document.createElement('canvas')
  canvas.width = roi.width
  canvas.height = roi.height
  canvas.getContext('2d').drawImage(img, roi.x, roi.y, roi.width, roi.height, 0, 0, roi.width, roi.height)
  const type = ALLOWED_IMAGE_TYPES.includes(record.content_type) ? record.content_type : 'image/png'
  const blob = await new Promise((res) => canvas.toBlob(res, type, 0.95))
  if (!blob) throw new Error('The browser could not encode the region.')
  return new File([blob], `crop.${type.split('/')[1]}`, { type })
}

const TOOL_BTN = 'flex h-9 items-center gap-1.5 rounded-control px-3 text-xs font-medium transition-colors'

export default function StripeExplorerPage() {
  const { toast } = useToast()
  const [params, setParams] = useSearchParams()
  const imageParam = params.get('image')

  const [source, setSource] = useState(null) // {type:'local', file, url} | {type:'library', record, url}
  const [loadError, setLoadError] = useState(null)
  const [loadingRecord, setLoadingRecord] = useState(false)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [tool, setTool] = useState('pan')
  const [roi, setRoi] = useState(null)
  const [cursor, setCursor] = useState(null)
  const [view, setView] = useState(null)
  const [resetSignal, setResetSignal] = useState(0)
  const [command, setCommand] = useState(null)
  const [capability, setCapability] = useState(null)
  const [refreshingCap, setRefreshingCap] = useState(false)
  const [busy, setBusy] = useState(null) // 'save' | 'crop' | 'submit'

  const [history, setHistory] = useState([])
  const [selectedJob, setSelectedJob] = useState(null)
  // Job ids of the latest POST /analyses/combined submission (same image + ROI by construction).
  const [pair, setPair] = useState(null)
  const [deletingId, setDeletingId] = useState(null)
  const [pollingElapsed, setPollingElapsed] = useState(0)
  const [overlay, setOverlay] = useState(null)
  const [overlayOpacity, setOverlayOpacity] = useState(0.65)
  const pollAbort = useRef(null)

  useEffect(() => {
    getAnalysisCapability().then(setCapability)
  }, [])

  const refreshCapability = useCallback(async () => {
    setRefreshingCap(true)
    try {
      const next = await getAnalysisCapability({ refresh: true })
      setCapability(next)
    } finally {
      setRefreshingCap(false)
    }
  }, [])

  const decoded = useDecodedSize(source?.url ?? null)

  const refreshHistory = useCallback(async (imageId) => {
    if (!imageId) return setHistory([])
    try {
      const page = await listAnalyses({ image_id: imageId, limit: 20 })
      const items = page.items || []
      setHistory(items)
      setSelectedJob((prev) => {
        if (!prev) return items[0] ?? null
        const updated = items.find((j) => j.id === prev.id)
        return updated || items[0] || null
      })
      setPair(inferPairFromHistory(items))
    } catch {
      setHistory([])
      setPair(null)
    }
  }, [])

  // Library image from ?image=<id>.
  useEffect(() => {
    if (!imageParam) return
    let active = true
    pollAbort.current?.abort()
    setLoadingRecord(true)
    setLoadError(null)
    setOverlay(null)
    Promise.all([imagesApi.get(imageParam), imagesApi.url(imageParam, 3600)])
      .then(([record, { url }]) => {
        if (!active) return
        setSource((prev) => {
          if (prev?.type === 'local') URL.revokeObjectURL(prev.url)
          return { type: 'library', record, url }
        })
        setRoi(null)
        setSelectedJob(null)
        setPair(null)
        refreshHistory(record.id)
      })
      .catch((err) => active && setLoadError(err))
      .finally(() => active && setLoadingRecord(false))
    return () => {
      active = false
    }
  }, [imageParam, refreshHistory])

  useEffect(() => () => source?.type === 'local' && URL.revokeObjectURL(source.url), [source])
  useEffect(() => () => pollAbort.current?.abort(), [])

  const isJobActive = selectedJob && (selectedJob.status === 'pending' || selectedJob.status === 'running')
  useEffect(() => {
    if (!isJobActive) return
    const started = Date.now()
    setPollingElapsed(0)
    const id = setInterval(() => setPollingElapsed(Math.floor((Date.now() - started) / 1000)), 1000)
    return () => clearInterval(id)
  }, [isJobActive, selectedJob?.id])

  function openLocal(file) {
    const problem = checkImageFile(file)
    if (problem) return setLoadError({ message: problem })
    pollAbort.current?.abort()
    setLoadError(null)
    setParams({}, { replace: true })
    setSource({ type: 'local', file, url: URL.createObjectURL(file) })
    setRoi(null)
    setHistory([])
    setSelectedJob(null)
    setPair(null)
    setOverlay(null)
  }

  const onViewChange = useCallback((v) => setView(v), [])

  async function saveToLibrary() {
    setBusy('save')
    try {
      const img = await imagesApi.upload(source.file, { kind: 'query' })
      toast({ title: 'Saved to image library', description: 'Stored privately as a query image.' })
      setParams({ image: img.id })
    } catch (err) {
      if (err.code === 'duplicate_image' && err.details?.existing_image_id) {
        toast({ tone: 'info', title: 'Already in the library', description: 'Opened the stored copy.' })
        setParams({ image: err.details.existing_image_id })
      } else {
        toast({ tone: 'danger', title: 'Could not save', description: err.message })
      }
    } finally {
      setBusy(null)
    }
  }

  async function saveCrop() {
    setBusy('crop')
    try {
      const file = await cropToFile(source.record, roi)
      const crop = await imagesApi.upload(file, { kind: 'crop', sourceImageId: source.record.id, cropBbox: roi })
      toast({ title: 'Region saved as crop', description: `${roi.width} × ${roi.height} px, linked to its source image.` })
      setParams({ image: crop.id })
    } catch (err) {
      toast({
        tone: 'danger',
        title: 'Could not save region',
        description: err.code === 'duplicate_image' ? 'An identical crop already exists.' : err.message,
      })
    } finally {
      setBusy(null)
    }
  }

  function upsertJob(job) {
    setHistory((prev) => [job, ...prev.filter((x) => x.id !== job.id)])
  }

  // `target` lets a retry reuse the failed job's own image and ROI instead of the current selection.
  async function runAndPoll(submitFn, target = null) {
    const imageId = target?.imageId ?? source?.record?.id
    if (!imageId) return
    pollAbort.current?.abort()
    setBusy('submit')
    setOverlay(null)
    try {
      const job = await submitFn(imageId, target ? target.roi : roi)
      setSelectedJob(job)
      upsertJob(job)
      const controller = new AbortController()
      pollAbort.current = controller
      const finalJob = await waitForAnalysis(job.id, {
        signal: controller.signal,
        timeoutSeconds: capability?.limits?.timeout_seconds ?? 120,
        onUpdate: (j) => {
          setSelectedJob(j)
          upsertJob(j)
        },
      })
      if (finalJob.status === 'completed') {
        toast({ title: 'Analysis completed', description: `${finalJob.artifacts.length} visualization artifact(s) ready.` })
      } else if (finalJob.status === 'failed') {
        toast({ tone: 'danger', title: 'Analysis failed', description: finalJob.error_message || finalJob.error_code })
      }
    } catch (err) {
      if (err?.name !== 'AbortError') {
        toast({ tone: 'danger', title: 'Analysis error', description: friendlyAnalysisError(err) })
      }
    } finally {
      setBusy(null)
    }
  }

  async function runCombined({ morphologyConfig, frequencyOptions }) {
    if (!source?.record?.id) return
    pollAbort.current?.abort()
    setBusy('submit')
    setOverlay(null)
    try {
      // One atomic request: both jobs are queued, or neither (error thrown).
      const { morphology, frequency } = await submitCombinedAnalysis(source.record.id, roi, {
        morphologyConfig,
        frequencyOptions,
      })
      const submitted = [morphology, frequency]
      submitted.forEach(upsertJob)
      setPair({ morphologyId: morphology.id, frequencyId: frequency.id })
      setSelectedJob(morphology)

      const controller = new AbortController()
      pollAbort.current = controller
      const timeoutSeconds = (capability?.limits?.timeout_seconds ?? 120) * submitted.length

      const results = await Promise.allSettled(
        submitted.map((job) =>
          waitForAnalysis(job.id, {
            signal: controller.signal,
            timeoutSeconds,
            onUpdate: (j) => {
              upsertJob(j)
              setSelectedJob((curr) => (curr?.id === j.id ? j : curr))
            },
          }),
        ),
      )

      const completedCount = results.filter((r) => r.status === 'fulfilled' && r.value.status === 'completed').length
      if (completedCount > 0) {
        toast({
          title: completedCount === 2 ? 'Combined analysis completed' : 'Partial analysis completed',
          description: `${completedCount} of ${submitted.length} scientific module(s) finished.`,
        })
      }
    } catch (err) {
      if (err?.name !== 'AbortError') {
        toast({ tone: 'danger', title: 'Combined analysis error', description: friendlyAnalysisError(err) })
      }
    } finally {
      setBusy(null)
    }
  }

  function handleRetryJob(failedJob) {
    const req = retryRequest(failedJob)
    if (!req) return
    if (req.kind === 'stripe_morphology') {
      runAndPoll((id, r) => submitMorphology(id, r, req.config), req)
    } else {
      runAndPoll((id, r) => submitFrequency(id, r, req.options), req)
    }
  }

  async function handleDeleteJob(jobId) {
    setDeletingId(jobId)
    try {
      await deleteAnalysis(jobId)
      if (overlay?.jobId === jobId) setOverlay(null)
      setHistory((prev) => prev.filter((j) => j.id !== jobId))
      setSelectedJob((prev) => (prev?.id === jobId ? null : prev))
      setPair((prev) => (prev && (prev.morphologyId === jobId || prev.frequencyId === jobId) ? null : prev))
      toast({ title: 'Analysis deleted' })
    } catch (err) {
      toast({ tone: 'danger', title: 'Could not delete analysis', description: err.message })
    } finally {
      setDeletingId(null)
    }
  }

  const naturalSize = decoded.size
  const ready = Boolean(source && naturalSize)

  // Never mix unrelated runs: combined only for one submitted pair on the same image + ROI.
  const displayed = resolveDisplayedResults({ selectedJob, pair, history })
  const displayMorphology = displayed.morphology
  const displayFrequency = displayed.frequency

  const assistantLink = (() => {
    if (!source?.record?.id) return '/assistant'
    const ids = [displayMorphology?.id, displayFrequency?.id].filter(Boolean)
    const qs = new URLSearchParams({ image: source.record.id })
    if (ids.length) qs.set('analyses', ids.join(','))
    return `/assistant?${qs.toString()}`
  })()

  const fileInput = (
    <input
      id="explorer-file"
      type="file"
      accept={ALLOWED_IMAGE_TYPES.join(',')}
      className="sr-only"
      onChange={(e) => {
        if (e.target.files?.[0]) openLocal(e.target.files[0])
        e.target.value = ''
      }}
    />
  )

  return (
    <div className="space-y-4">
      {fileInput}
      <Card className="flex flex-wrap items-center gap-2 p-2.5">
        <label htmlFor="explorer-file" className={cn(TOOL_BTN, 'cursor-pointer bg-accent text-accent-ink hover:bg-accent-strong')}>
          Open file
        </label>
        <button type="button" onClick={() => setPickerOpen(true)} className={cn(TOOL_BTN, 'border border-line bg-raised text-ink hover:border-line-strong')}>
          <GalleryIcon className="h-4 w-4" /> Library
        </button>
        <span className="mx-1 hidden h-6 w-px bg-line sm:block" />
        <div role="radiogroup" aria-label="Tool" className="flex rounded-control border border-line bg-raised p-0.5">
          {[
            ['pan', 'Pan'],
            ['roi', 'Region'],
          ].map(([id, label]) => (
            <button
              key={id}
              type="button"
              role="radio"
              aria-checked={tool === id}
              disabled={!ready}
              onClick={() => setTool(id)}
              className={cn('h-8 rounded-[0.375rem] px-3 text-xs font-medium', tool === id ? 'bg-surface text-accent shadow-card' : 'text-muted hover:text-ink')}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1">
          {[
            ['Zoom out', '−', () => setCommand({ type: 'zoomOut', n: Date.now() })],
            ['Zoom in', '+', () => setCommand({ type: 'zoomIn', n: Date.now() })],
            ['Actual size (100%)', '1:1', () => setCommand({ type: 'actual', n: Date.now() })],
            ['Reset view (fit)', 'Fit', () => setResetSignal((n) => n + 1)],
          ].map(([label, text, fn]) => (
            <button
              key={label}
              type="button"
              aria-label={label}
              title={label}
              disabled={!ready}
              onClick={fn}
              className={cn(TOOL_BTN, 'min-w-9 justify-center px-2 font-mono text-muted hover:bg-raised hover:text-ink disabled:opacity-40')}
            >
              {text}
            </button>
          ))}
        </div>
        {source?.type === 'library' && (
          <Link
            to={assistantLink}
            className={cn(TOOL_BTN, 'border border-line bg-raised text-accent hover:border-accent/60')}
          >
            <SparkleIcon className="h-4 w-4" /> Explain with Gemini
          </Link>
        )}
        <span className="tabular ml-auto hidden font-mono text-xs text-faint sm:block">{view && ready ? `${Math.round(view.scale * 100)}%` : ''}</span>
      </Card>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_24rem]">
        <Card className="min-w-0 overflow-hidden">
          {loadingRecord || (source && !naturalSize && !decoded.error) ? (
            <div className="flex h-[60vh] min-h-80 items-center justify-center gap-2 text-sm text-muted lg:h-[calc(100vh-15rem)]">
              <Spinner className="h-5 w-5 text-accent" /> Loading image…
            </div>
          ) : loadError || decoded.error ? (
            <ErrorState className="h-[60vh] min-h-80" title="Cannot open image" error={loadError} message={decoded.error || undefined} />
          ) : !source ? (
            <EmptyState
              className="h-[60vh] min-h-80 lg:h-[calc(100vh-15rem)]"
              icon={<StripesIcon />}
              title="Open an image to explore"
              description="Load a local photograph or a stored image. Zoom, pan and select a region; run Member 1 morphology, Member 2 spatial-frequency, or combined scientific analysis."
              action={
                <>
                  <label htmlFor="explorer-file" className={cn(TOOL_BTN, 'cursor-pointer bg-accent text-accent-ink hover:bg-accent-strong')}>
                    Open file
                  </label>
                  <Button variant="secondary" size="sm" onClick={() => setPickerOpen(true)}>
                    From library
                  </Button>
                </>
              }
            />
          ) : (
            <ImageViewport
              className="h-[60vh] min-h-80 lg:h-[calc(100vh-15rem)]"
              src={source.url}
              naturalSize={naturalSize}
              tool={tool}
              roi={roi}
              onRoiChange={setRoi}
              onViewChange={onViewChange}
              onCursor={setCursor}
              resetSignal={resetSignal}
              command={command}
              overlay={overlay ? { ...overlay, opacity: overlayOpacity } : null}
            />
          )}
        </Card>

        <div className="min-w-0 space-y-4">
          <ImageInfoPanel source={source} naturalSize={naturalSize} />
          {source?.type === 'local' && (
            <Button variant="secondary" className="w-full" loading={busy === 'save'} onClick={saveToLibrary}>
              Save to image library
            </Button>
          )}
          <SpatialPanel
            naturalSize={naturalSize}
            view={ready ? view : null}
            cursor={cursor}
            roi={roi}
            onRoiChange={setRoi}
            cropAction={
              roi && (
                <div className="mt-3">
                  <Button
                    size="sm"
                    variant="secondary"
                    className="w-full"
                    loading={busy === 'crop'}
                    disabled={source?.type !== 'library'}
                    onClick={saveCrop}
                  >
                    Save region as crop
                  </Button>
                  {source?.type !== 'library' && <p className="mt-1.5 text-[0.6875rem] text-faint">Save the image to the library first.</p>}
                </div>
              )
            }
          />
          <AnalysisDrawer
            source={source}
            naturalSize={naturalSize}
            roi={roi}
            capability={capability}
            refreshingCap={refreshingCap}
            onRefreshCapability={refreshCapability}
            activeJob={selectedJob}
            pollingElapsed={pollingElapsed}
            submitting={busy === 'submit'}
            onSubmitMorphology={(cfg) => runAndPoll((id, r) => submitMorphology(id, r, cfg))}
            onSubmitFrequency={(opts) => runAndPoll((id, r) => submitFrequency(id, r, opts))}
            onSubmitCombined={runCombined}
            onRetryJob={handleRetryJob}
            onStopPolling={() => pollAbort.current?.abort()}
            onSaveCrop={saveCrop}
            cropBusy={busy === 'crop'}
          />

          <CombinedCaveatBanner morphologyJob={displayMorphology} frequencyJob={displayFrequency} combined={displayed.combined} />

          {displayMorphology && (
            <>
              <MorphologyResultPanel job={displayMorphology} />
              <ArtifactGallery
                job={displayMorphology}
                activeOverlay={overlay}
                opacity={overlayOpacity}
                onOpacityChange={setOverlayOpacity}
                onToggleOverlay={setOverlay}
              />
            </>
          )}

          {displayFrequency && (
            <>
              <FrequencyResultPanel job={displayFrequency} />
              <ArtifactGallery
                job={displayFrequency}
                activeOverlay={overlay}
                opacity={overlayOpacity}
                onOpacityChange={setOverlayOpacity}
                onToggleOverlay={setOverlay}
              />
            </>
          )}

          <AnalysisHistory
            items={history}
            selectedId={selectedJob?.id}
            onSelect={(j) => {
              setSelectedJob(j)
              setOverlay(null)
            }}
            onDelete={handleDeleteJob}
            deletingId={deletingId}
          />
        </div>
      </div>

      {pickerOpen && (
        <LibraryPickerDialog
          onClose={() => setPickerOpen(false)}
          onPick={(img) => {
            setPickerOpen(false)
            setParams({ image: img.id })
          }}
        />
      )}
    </div>
  )
}
