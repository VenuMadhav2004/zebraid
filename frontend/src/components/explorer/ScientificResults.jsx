import { useState } from 'react'
import { describeFrequencyFilter, fmtMeasure, jobCommit, shortCommit } from '../../lib/analysisResults.js'
import { formatDateTime } from '../../lib/format.js'
import { Badge, Card } from '../ui/index.js'

// Missing or non-finite measurements are shown as "unavailable", never as a substitute value.
const fmt = fmtMeasure
const count = (v) => (Number.isInteger(v) ? v.toLocaleString() : 'unavailable')

const REGION_ONLY_NOTE =
  'These are image-space measurements of one region of one photograph. They do not identify an individual, and differences between regions or photographs do not show that they belong to different zebras.'

function ObservedHeading({ module }) {
  return (
    <p className="text-[0.6875rem] text-faint">
      <span className="font-medium text-muted">Observed measurements</span> reported by {module}. Interpretation is not part of
      this output.
    </p>
  )
}

function StatRows({ rows }) {
  return (
    <dl className="divide-y divide-line text-xs">
      {rows.map(([k, v]) => (
        <div key={k} className="flex items-baseline justify-between gap-3 py-1.5">
          <dt className="text-faint">{k}</dt>
          <dd className="tabular text-right font-mono text-ink">{v}</dd>
        </div>
      ))}
    </dl>
  )
}

function ProvenanceStrip({ job, processingSeconds }) {
  const p = job?.provider || {}
  const commit = jobCommit(job) ? shortCommit(jobCommit(job)) : 'not recorded'
  return (
    <div className="rounded-control border border-line bg-raised/50 px-2.5 py-2 text-[0.6875rem] text-faint space-y-0.5">
      <div className="flex flex-wrap items-center justify-between gap-1">
        <span className="font-mono text-muted">{p.function || job.kind}</span>
        <span className="font-mono text-ink">commit {commit}</span>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-1">
        <span>
          Schema {p.library_schema_version || '—'} · ROI mode: <span className="font-mono text-muted">{job.roi_mode}</span>
        </span>
        <span className="tabular">
          {typeof processingSeconds === 'number' ? `${fmt(processingSeconds, 2)} s` : job.completed_at ? formatDateTime(job.completed_at) : ''}
        </span>
      </div>
    </div>
  )
}

function RawJsonToggle({ data }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="pt-2 border-t border-line">
      <button type="button" onClick={() => setOpen((o) => !o)} className="text-[0.6875rem] text-muted hover:text-accent">
        {open ? 'Hide raw result JSON' : 'Show raw result JSON'}
      </button>
      {open && (
        <pre className="mt-2 max-h-60 overflow-auto rounded-control bg-raised p-2.5 font-mono text-[0.6875rem] text-muted">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  )
}

function SpectrumBars({ title, labels, signal = [], control = [] }) {
  if (!signal.length) return null
  const maxVal = Math.max(0.001, ...signal, ...control)
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-[0.6875rem]">
        <span className="eyebrow">{title}</span>
        <span className="flex items-center gap-2 text-faint">
          <span className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-sm bg-accent" />
            ROI
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-sm bg-muted/60" />
            Shuffled control
          </span>
        </span>
      </div>
      <div className="overflow-x-auto">
        <div className="space-y-1.5 min-w-[14rem]">
          {signal.map((v, i) => {
            const c = control[i] ?? 0
            return (
              <div key={i} className="grid grid-cols-[4.5rem_1fr_3.5rem] items-center gap-2 text-[0.6875rem]">
                <span className="truncate font-mono text-faint">{labels[i] ?? `Bin ${i + 1}`}</span>
                <div className="space-y-0.5">
                  <div className="h-1.5 rounded bg-raised overflow-hidden">
                    <div className="h-full bg-accent" style={{ width: `${Math.min(100, (v / maxVal) * 100)}%` }} />
                  </div>
                  <div className="h-1.5 rounded bg-raised overflow-hidden">
                    <div className="h-full bg-muted/60" style={{ width: `${Math.min(100, (c / maxVal) * 100)}%` }} />
                  </div>
                </div>
                <span className="tabular text-right font-mono text-ink">{fmt(v, 3)}</span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

/**
 * Shown only for the two jobs of one combined submission (same image and ROI, see
 * resolveDisplayedResults). The modules still report separately below.
 */
export function CombinedCaveatBanner({ morphologyJob, frequencyJob, combined }) {
  if (!combined || !morphologyJob || !frequencyJob) return null
  const r = morphologyJob.roi || {}
  return (
    <Card className="border-info/30 bg-info/10 p-3 text-xs space-y-1">
      <div className="flex items-center justify-between gap-2">
        <span className="font-semibold text-ink">Combined submission: two separate module results</span>
        <Badge tone="info">Same image &amp; ROI</Badge>
      </div>
      <p className="text-[0.6875rem] text-muted">
        Region {r.width} × {r.height} px at ({r.x}, {r.y}). Member 1 ({morphologyJob.roi_mode}) preprocesses the full image and
        restricts measurements to this rectangle as a mask; Member 2 ({frequencyJob.roi_mode}) crops and analyses only this box.
        The two outputs are reported separately and are not merged into one measurement.
      </p>
      <p className="text-[0.6875rem] text-faint">{REGION_ONLY_NOTE}</p>
    </Card>
  )
}

export function MorphologyResultPanel({ job }) {
  const res = job?.result
  if (!res) return null
  const commit = jobCommit(job) ? shortCommit(jobCommit(job)) : 'commit not recorded'
  const q = res.quality_metrics || {}
  const w = res.width_statistics || {}
  const sp = res.spacing_statistics || {}
  const o = res.orientation_statistics || {}
  const cv = res.curvature_statistics || {}
  const br = res.branching_statistics || {}
  const dens = res.stripe_density || {}
  const meta = res.input_and_region_metadata || {}
  const units = res.measurement_units || {}
  const warnings = Array.isArray(res.warnings) ? res.warnings : []

  return (
    <Card className="p-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-ink">Stripe morphology (M1)</h3>
        <div className="flex flex-wrap gap-1.5">
          <Badge tone="info">Member 1 · {commit}</Badge>
          <Badge tone={res.segmentation_status === 'SUCCESS' ? 'success' : res.segmentation_status ? 'warning' : 'neutral'}>
            {res.segmentation_status || 'status not reported'}
          </Badge>
        </div>
      </div>

      <ProvenanceStrip job={job} processingSeconds={res.processing_time_seconds} />
      <ObservedHeading module="Member 1 analyze_stripes" />

      {warnings.length > 0 && (
        <div className="space-y-1.5 rounded-control border border-warning/30 bg-warning/10 p-2.5 text-xs">
          {warnings.map((msg, i) => {
            const code = typeof msg === 'string' && msg.includes(':') ? msg.split(':')[0] : 'WARNING'
            return (
              <div key={i} className="flex items-start gap-2">
                <Badge tone="warning">{code}</Badge>
                <span className="text-muted">{msg}</span>
              </div>
            )
          })}
        </div>
      )}

      <div>
        <div className="eyebrow mb-1">Segmentation quality & region</div>
        <StatRows
          rows={[
            ['Segmentation quality score (heuristic)', fmt(q.confidence_score, 4)],
            ['Contrast ratio', fmt(q.contrast_ratio, 4)],
            ['Edge sharpness', fmt(q.edge_sharpness, 2)],
            ['Valid ROI pixels', count(meta.valid_roi_pixels)],
            ['ROI coverage ratio', fmt(meta.roi_coverage_ratio, 4)],
            ['Pixel sample hash', meta.content_hash || 'unavailable'],
          ]}
        />
      </div>

      <div>
        <div className="eyebrow mb-1">Stripe width & spacing (px)</div>
        <StatRows
          rows={[
            ['Width mean ± std', `${fmt(w.mean_px, 2)} ± ${fmt(w.std_px, 2)} px`],
            ['Width median (p10–p90)', `${fmt(w.median_px, 2)} (${fmt(w.p10_px, 2)}–${fmt(w.p90_px, 2)}) px`],
            ['Width min–max (n)', `${fmt(w.min_px, 2)}–${fmt(w.max_px, 2)} px (${count(w.sample_count)})`],
            ['Spacing mean ± std', `${fmt(sp.mean_px, 2)} ± ${fmt(sp.std_px, 2)} px`],
            ['Spacing median (p10–p90)', `${fmt(sp.median_px, 2)} (${fmt(sp.p10_px, 2)}–${fmt(sp.p90_px, 2)}) px`],
            ['Spacing min–max (n)', `${fmt(sp.min_px, 2)}–${fmt(sp.max_px, 2)} px (${count(sp.sample_count)})`],
          ]}
        />
      </div>

      <div>
        <div className="eyebrow mb-1">Orientation (axial 0–180°) & coherence</div>
        <StatRows
          rows={[
            ['Dominant angle', `${fmt(o.dominant_angle_deg, 2)}°`],
            ['Mean angle', `${fmt(o.mean_angle_deg, 2)}°`],
            ['Circular variance', fmt(o.circular_variance, 4)],
            ['Mean coherence', fmt(o.mean_coherence, 4)],
            ['Orientation entropy', fmt(o.orientation_entropy, 4)],
          ]}
        />
      </div>

      <div>
        <div className="eyebrow mb-1">Curvature & branching</div>
        <StatRows
          rows={[
            ['Curvature mean ± std', `${fmt(cv.mean_curvature, 4)} ± ${fmt(cv.std_curvature, 4)} 1/px`],
            ['Curvature median / p90', `${fmt(cv.median_curvature, 4)} / ${fmt(cv.p90_curvature, 4)} 1/px`],
            ['Branches / junctions / endpoints', `${count(br.branch_count)} / ${count(br.junction_count)} / ${count(br.endpoint_count)}`],
            ['Junction density (per kpx)', fmt(br.junction_density_per_kpx, 4)],
          ]}
        />
      </div>

      <div>
        <div className="eyebrow mb-1">Stripe density</div>
        <StatRows
          rows={[
            ['Black stripe fraction', fmt(dens.black_stripe_fraction, 4)],
            ['Width-to-spacing ratio', fmt(dens.width_to_spacing_ratio, 4)],
          ]}
        />
      </div>

      {Object.keys(units).length > 0 && (
        <div className="rounded-control bg-raised/60 p-2 text-[0.6875rem] text-faint space-y-0.5">
          {Object.entries(units).map(([k, v]) => (
            <div key={k}>
              <span className="font-medium text-muted">{k}:</span> {v}
            </div>
          ))}
        </div>
      )}

      <p className="text-[0.6875rem] text-faint">{REGION_ONLY_NOTE}</p>
      <p className="text-[0.6875rem] text-faint">{REGION_ONLY_NOTE}</p>
      <RawJsonToggle data={res} />
    </Card>
  )
}

export function FrequencyResultPanel({ job }) {
  const res = job?.result
  if (!res) return null
  const commit = jobCommit(job) ? shortCommit(jobCommit(job)) : 'commit not recorded'
  const freq = res.frequency || {}
  const meas = res.measurements || {}
  const filter = res.filter || {}
  const opts = job.parameters?.options || {}
  const spec = res.spectrum || {}
  const ctrl = res.negative_control?.spectrum || {}
  const warnings = [...(Array.isArray(res.warnings) ? res.warnings : []), ...(Array.isArray(filter.warnings) ? filter.warnings : [])]

  const radialLabels = (spec.radial_bins_cycles_per_pixel || []).slice(0, -1).map((b, i) => {
    const hi = spec.radial_bins_cycles_per_pixel[i + 1]
    return `${b.toFixed(2)}–${hi?.toFixed(2)}`
  })
  const orientLabels = (spec.orientation_bins_radians || []).slice(0, -1).map((r, i) => {
    const deg1 = Math.round((r * 180) / Math.PI)
    const deg2 = Math.round(((spec.orientation_bins_radians[i + 1] ?? Math.PI) * 180) / Math.PI)
    return `${deg1}–${deg2}°`
  })

  // Reported by Member 2 in result.filter (actual keys); requested options shown separately.
  const applied = describeFrequencyFilter(filter)
  const requested =
    opts.filter_type === 'bandpass'
      ? `bandpass ${opts.band_low_cpp}–${opts.cutoff_cpp} cycles/pixel`
      : opts.filter_type
        ? `${opts.filter_type} ${opts.cutoff_cpp} cycles/pixel`
        : 'unavailable'

  return (
    <Card className="p-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-ink">Spatial frequency (M2)</h3>
        <Badge tone="info">Member 2 · {commit}</Badge>
      </div>

      <ProvenanceStrip job={job} />
      <ObservedHeading module="Member 2 safe_analyze" />

      <div>
        <div className="eyebrow mb-1">Dominant spatial frequency</div>
        <StatRows
          rows={[
            ['Cycles per pixel', fmt(freq.cycles_per_pixel, 5)],
            ['Period (pixels)', fmt(freq.period_pixels, 2)],
            ['FFT peak strength (frequency.confidence)', fmt(freq.confidence, 4)],
          ]}
        />
        {freq.caveat && <p className="mt-1 text-[0.6875rem] text-faint">Member 2 caveat: {freq.caveat}</p>}
        <p className="mt-1 text-[0.6875rem] text-faint">
          FFT peak strength is a relative spectral measure, not a probability, and Member 2 defines no threshold for it. A small
          value means the reported dominant period is only weakly supported by this region; treat the period as indicative.
        </p>
        <p className="mt-1 text-[0.6875rem] text-faint">
          The dominant frequency, spectrum and orientation are computed on the unfiltered ROI. The selected filter only produces the
          “Filtered ROI” image, so the dominant frequency can lie outside a band-pass range.
        </p>
      </div>

      <div>
        <div className="eyebrow mb-1">Filtering & ROI measurements</div>
        <StatRows
          rows={[
            ['Applied filter (result)', applied.type || 'unavailable'],
            ['Applied cutoff (result)', applied.cutoff || 'unavailable'],
            ['Requested options', requested],
            ['Mean intensity', fmt(meas.mean_intensity, 4)],
            ['Intensity std', fmt(meas.intensity_std, 4)],
            ['Dark fraction', fmt(meas.dark_fraction, 4)],
            ['Orientation valid fraction', fmt(meas.orientation_valid_fraction, 4)],
          ]}
        />
      </div>

      <SpectrumBars
        title="Radial energy (cpp)"
        labels={radialLabels}
        signal={spec.radial_energy_fraction}
        control={ctrl.radial_energy_fraction}
      />

      <SpectrumBars
        title="Orientation energy"
        labels={orientLabels}
        signal={spec.orientation_energy_fraction}
        control={ctrl.orientation_energy_fraction}
      />

      {warnings.length > 0 && (
        <div className="rounded-control border border-warning/30 bg-warning/10 p-2.5 space-y-1 text-[0.6875rem] text-muted">
          <div className="font-medium text-warning">Methodological caveats</div>
          <ul className="list-disc pl-4 space-y-0.5">
            {warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      <RawJsonToggle data={res} />
    </Card>
  )
}
