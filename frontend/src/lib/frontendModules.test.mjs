import assert from 'node:assert/strict'
import test from 'node:test'
import { buildHistoryPayload, friendlyAssistantError, parseScientificSections } from './assistantFormat.js'

test('parseScientificSections separates Observed Measurements from AI Hypotheses', () => {
  const sample = [
    '**Observed Measurements & Recorded Data**',
    '- Stripe width mean: 11.40 px',
    '- Dominant angle: 82.5° (axial 0–180°)',
    '',
    '**Interpretation & Hypotheses**',
    '- Regular spacing suggests intact mid-flank pattern visibility.',
  ].join('\n')

  const sections = parseScientificSections(sample)
  assert.equal(sections.length, 2)
  assert.equal(sections[0].kind, 'observations')
  assert.equal(sections[0].title, 'Observed Measurements & Recorded Data')
  assert.equal(sections[0].lines.length, 2)
  assert.equal(sections[1].kind, 'hypotheses')
  assert.equal(sections[1].title, 'Interpretation & Hypotheses')
  assert.equal(sections[1].lines.length, 1)
})

test('parseScientificSections handles markdown headings and general prose safely', () => {
  const sample = '### Observed Measurements & Recorded Data\nImage is 120x90 px.\n\n### Interpretation & Hypotheses\nNo analyses run yet.'
  const sections = parseScientificSections(sample)
  assert.equal(sections.length, 2)
  assert.equal(sections[0].kind, 'observations')
  assert.equal(sections[1].kind, 'hypotheses')
})

test('buildHistoryPayload formats multi-turn history and caps at maxTurns', () => {
  const msgs = Array.from({ length: 8 }, (_, i) => ({
    question: `Question ${i}`,
    answer: `Answer ${i}`,
  }))
  const history = buildHistoryPayload(msgs, 12)
  assert.equal(history.length, 12)
  assert.deepEqual(history[0], { role: 'user', text: 'Question 2' })
  assert.deepEqual(history[11], { role: 'model', text: 'Answer 7' })
})

test('friendlyAssistantError maps backend codes and retryability accurately', () => {
  assert.equal(friendlyAssistantError({ code: 'assistant_rate_limited', status: 429 }).retryable, true)
  assert.equal(friendlyAssistantError({ code: 'assistant_timeout', status: 504 }).retryable, true)
  assert.equal(friendlyAssistantError({ code: 'assistant_invalid_api_key', status: 503 }).retryable, false)
  assert.equal(friendlyAssistantError({ code: 'assistant_unavailable', status: 503 }).retryable, false)
  assert.equal(friendlyAssistantError({ code: 'assistant_network_error', status: 502 }).retryable, true)
})
