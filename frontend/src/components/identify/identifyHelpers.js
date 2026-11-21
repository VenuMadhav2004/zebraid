import { useResource } from '../../hooks/useResource.js'
import { getImageUrl, getZebra } from '../../services/identification.js'

export const RUN_TONE = { completed: 'success', failed: 'danger', running: 'info', pending: 'warning' }
export const DECISION_TONE = { confirmed: 'success', rejected: 'danger', unknown: 'warning' }
export const DECISION_LABEL = { confirmed: 'Confirmed', rejected: 'Rejected', unknown: 'Marked unknown' }

export const useImageUrl = (imageId) => useResource(imageId ? ['img-url', imageId] : null, () => getImageUrl(imageId))
export const useZebra = (zebraId) => useResource(zebraId ? ['zebra', zebraId] : null, () => getZebra(zebraId))

/**
 * Raw model similarity. Not a probability: no percent sign, no "confidence".
 * Range and direction depend on score_type, which is shown verbatim when supplied.
 */
export function formatSimilarity(score) {
  if (typeof score !== 'number' || !Number.isFinite(score)) return '—'
  return Math.abs(score) >= 100 ? score.toFixed(1) : score.toFixed(4)
}
