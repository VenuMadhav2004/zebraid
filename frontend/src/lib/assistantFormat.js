/**
 * Pure formatting, multi-turn history serialization, and error helpers for the
 * grounded Gemini scientific assistant. Zero network calls or fake data.
 */

const MAX_HISTORY_TURNS = 12
const MAX_TURN_CHARS = 4000

const OBS_HEADING = /^(?:#{1,4}\s*)?\*{0,2}\s*(?:observed measurements(?:\s*&\s*recorded data)?|recorded data|observed data)\s*\*{0,2}\s*:?\s*$/i
const HYP_HEADING = /^(?:#{1,4}\s*)?\*{0,2}\s*(?:interpretation(?:\s*&\s*hypotheses)?|hypotheses(?:\s*&\s*caveats)?|ai hypotheses)\s*\*{0,2}\s*:?\s*$/i

/**
 * Parse a Gemini response into structured scientific sections so the UI visually
 * separates Observed Measurements from AI Interpretation & Hypotheses.
 *
 * Returns Array<{ kind: 'observations' | 'hypotheses' | 'general', title: string | null, lines: string[] }>.
 */
export function parseScientificSections(text = '') {
  const raw = String(text || '').trim()
  if (!raw) return []

  const sections = []
  let current = { kind: 'general', title: null, lines: [] }

  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim()
    if (OBS_HEADING.test(trimmed)) {
      if (current.lines.some((l) => l.trim())) sections.push(current)
      current = { kind: 'observations', title: 'Observed Measurements & Recorded Data', lines: [] }
      continue
    }
    if (HYP_HEADING.test(trimmed)) {
      if (current.lines.some((l) => l.trim())) sections.push(current)
      current = { kind: 'hypotheses', title: 'Interpretation & Hypotheses', lines: [] }
      continue
    }
    current.lines.push(line)
  }

  if (current.lines.some((l) => l.trim()) || current.title) {
    sections.push(current)
  }

  return sections.map((s) => ({
    ...s,
    lines: s.lines
      .map((l) => l.trimEnd())
      .filter((l, idx, arr) => l.trim() !== '' || (idx > 0 && idx < arr.length - 1 && arr[idx - 1].trim() !== '')),
  }))
}

/**
 * Build Agent 1's exact `history` payload: Array<{ role: 'user' | 'model', text: string }>,
 * bounded to the latest 12 turns and 4000 chars per turn.
 */
export function buildHistoryPayload(messages = [], maxTurns = MAX_HISTORY_TURNS) {
  const turns = []
  for (const m of messages) {
    if (m?.question?.trim()) {
      turns.push({ role: 'user', text: m.question.trim().slice(0, MAX_TURN_CHARS) })
    }
    if (m?.answer?.trim()) {
      turns.push({ role: 'model', text: m.answer.trim().slice(0, MAX_TURN_CHARS) })
    }
  }
  return turns.slice(-maxTurns)
}

/**
 * Map backend assistant error codes into clear researcher messages + retry eligibility.
 */
export function friendlyAssistantError(err) {
  const code = err?.code || ''
  if (code === 'assistant_rate_limited' || err?.status === 429) {
    return { message: err.message || 'Gemini rate limit reached. Wait a moment and retry.', retryable: true }
  }
  if (code === 'assistant_timeout' || err?.status === 504) {
    return { message: err.message || 'Gemini request timed out. Please retry.', retryable: true }
  }
  if (code === 'assistant_invalid_api_key' || code === 'assistant_unavailable') {
    return { message: err.message || 'Gemini assistant is currently unavailable.', retryable: false }
  }
  if (code === 'assistant_network_error' || code === 'assistant_malformed_response' || code === 'assistant_upstream_error' || code === 'network_error') {
    return { message: err.message || 'Could not reach Gemini API. Please retry.', retryable: true }
  }
  return { message: err?.message || 'Assistant request failed.', retryable: true }
}
