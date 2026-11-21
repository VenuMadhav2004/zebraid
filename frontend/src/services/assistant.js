// Grounded Gemini scientific assistant client.
// Talks only to /api/v1/assistant/*; never invents measurements or exposes API keys.
import { apiV1 } from './api.js'

const data = (r) => r.data

export const getAssistantStatus = () => apiV1.get('/assistant/status').then(data)

export function askAssistant({ question, imageId, analysisIds = [], zebraId, runId, history = [] }) {
  const body = { question }
  if (imageId) body.image_id = imageId
  if (analysisIds?.length) body.analysis_ids = analysisIds
  if (zebraId) body.zebra_id = zebraId
  if (runId) body.run_id = runId
  if (history?.length) body.history = history
  return apiV1.post('/assistant/ask', body, { timeout: 60000 }).then(data)
}
