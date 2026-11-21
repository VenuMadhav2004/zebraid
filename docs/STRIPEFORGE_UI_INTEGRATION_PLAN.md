# STRIPEFORGE UI integration plan (Stripe Explorer)

Status: design, 2026-11-21. Builds on the existing `/stripes` page (Phase 4) and the contract in
`STRIPEFORGE_DATA_CONTRACT.md`. No React code was changed for this plan.

## 1. What exists today (keep)

| File | Current behaviour |
|---|---|
| `src/pages/explorer/StripeExplorerPage.jsx` | Open local file or library image (`?image=<id>`), zoom/pan/fit/1:1, ROI tool, save to library, save region as crop |
| `src/components/explorer/ImageViewport.jsx` | Integer ROI `{x,y,width,height}` in decoded-image pixels (browser-oriented) |
| `src/components/explorer/Panels.jsx` | `ImageInfoPanel` (recorded), `SpatialPanel` (computed geometry), `AnalysisPanel` ×2 ("Unavailable"), `AnalyzeButton` (disabled) |
| `src/services/stripeAnalysis.js` | `getAnalysisCapability()` → always unavailable; `analyzeRegion()` throws `AnalysisUnavailableError` |

Unchanged pages: Overview, Identify (no identities or scores come from these analyses), Zebra Gallery, Sightings.

## 2. Adapter: `src/services/stripeAnalysis.js` (rewrite behind the same exports)

| Function | Calls |
|---|---|
| `getAnalysisCapability()` | `GET /api/v1/analyses/capabilities` (cached; network error ⇒ unavailable with reason) |
| `submitMorphology(imageId, roi, config)` | `POST /api/v1/analyses/stripe-morphology` |
| `submitFrequency(imageId, roi, options)` | `POST /api/v1/analyses/spatial-frequency` |
| `getAnalysis(id)` / `listAnalyses({image_id, kind, limit, offset})` | GET endpoints |
| `waitForAnalysis(id, {signal, onUpdate})` | polls `GET /analyses/{id}`: 1 s, then ×1.5 up to 5 s; stops on `completed`/`failed`, on abort, or after `limits.timeout_seconds + 30 s` |
| `getArtifactUrl(id, name)` | `GET …/artifacts/{name}/url?expires_in=600` (refetch on image error / expiry) |
| `deleteAnalysis(id)` | DELETE |

Errors keep the normalised `ApiError` from `api.js`; `analysis_busy` and `analysis_limit_exceeded` get specific
UI messages. `analyzeRegion()` is removed once callers move to the two submit functions.

## 3. Explorer changes

1. **Analysis drawer** (replaces the single "Analyse region" button), enabled only for library images
   (local files: existing "Save to image library" first, as for crops):
   - Tabs: **Stripe morphology** (Member 1) · **Spatial frequency** (Member 2).
   - ROI: current ROI or "whole image"; shows pixel count against `limits.max_pixels`; if exceeded, disables
     submit and offers the existing "Save region as crop".
   - Morphology form: the five `config` fields with Member 1 defaults, "Reset to defaults"; only changed fields are sent.
   - Frequency form: `filter_type` select; `cutoff_cpp`; `band_low_cpp` shown only for band-pass with
     inline `low < high` check; ROI ≥ 16×16 check.
   - Submit → job card with status `pending/running` (spinner + elapsed time), cancel-polling button (job
     continues server-side), result when done.
2. **History list** for the image: `listAnalyses({image_id})` — kind, status, time, ROI, source commit; select to
   load; delete.
3. **Result panels** (typed renderers instead of raw JSON; raw JSON stays available behind a toggle):
   - *Stripe characteristics* (Member 1): tables for width, spacing (px), orientation (dominant angle, circular
     variance, coherence, entropy; "axial 0–180°"), curvature (1/px), branching counts and density per kpx,
     stripe density ratios. Units from `measurement_units` shown verbatim. `segmentation_status` badge; each
     warning code as a badge with its text. `quality_metrics.confidence_score` labelled **"Segmentation quality
     score (heuristic)"**; `content_hash` labelled "Pixel sample hash".
   - *Spatial information* (Member 2): `frequency.cycles_per_pixel` / `period_pixels` with `caveat`;
     `frequency.confidence` labelled **"FFT peak strength"**; measurements table; filter parameters; radial and
     orientation energy bar charts **with the negative-control series side by side**; the four result
     `warnings` and `filter.warnings` always visible (not collapsible).
   - Existing *Spatial information* geometry panel keeps its "Computed geometry" badge; analysis panels carry
     "Computed by Member 1 · 127b563" / "Member 2 · 96a69a4" provenance badges.
   - No panel shows a percentage, "confidence" for identity, physical units, or any value not in the stored result.
4. **Artifact gallery** (`components/explorer/ArtifactGallery.jsx`, new): thumbnails via signed URLs, click to
   open in the viewport as an overlay layer with opacity slider:
   - Member 1 maps are full-image size → overlay at (0,0) with the same transform as the photo.
   - Member 2 maps are ROI size → overlay at (roi.x, roi.y); `spectrum` is shown only in the side panel (not spatial).
5. **Comparison** (optional, last): two completed jobs of the same kind side by side (numbers only), with a notice
   when ROI, parameters or source commit differ.

## 4. Mobile

Drawer becomes a bottom sheet; panels stack under the viewport (current layout already stacks below `xl`);
charts scroll horizontally inside their card; polling pauses when the tab is hidden (`visibilitychange`).
Acceptance: no horizontal page overflow at 390 px (existing test helper).

## 5. States

| Situation | UI |
|---|---|
| Capability unavailable | Existing "Unavailable" panels + reason from capabilities; submit hidden |
| Local file | "Save to image library to analyse" |
| Over pixel limit | Disabled submit, pixel count vs limit, "Save region as crop" |
| Queue full (503 `analysis_busy`) | Toast "Analysis queue is full — try again shortly" |
| Job failed | Error code + message from the job (sanitised server-side), retry button (new job) |
| Artifact URL expired | Silent refetch once, then "Image unavailable" in the frame |

## 6. Tests (browser, existing Playwright harness)

Submit both kinds on a real library photo; poll to completion; numbers equal a direct Python call on the same
stored bytes and ROI; artifacts load; warnings visible; limit and busy states; deletion; mobile overflow; no text
"confidence" outside the two relabelled fields; no `/tmp`, bucket path or `analysis.json` in any response
(network assertion).
