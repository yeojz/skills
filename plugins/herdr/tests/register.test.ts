import { expect, test } from 'claude-code/testing'

const USAGE = {
  startedAt: 0,
  context: { tokens: 120_000, window: 1_000_000, percent: 12.4 },
  rateLimits: [
    { kind: 'five_hour', percentUsed: 41.6 },
    { kind: 'seven_day', percentUsed: 104 },
  ],
}

const MEASURE = { context: USAGE.context, rateLimits: USAGE.rateLimits, changed: ['context' as const] }

test('inside Herdr, a measure writes the bar file for that terminal', async ($, on) => {
  const writes: { path: string; text: string }[] = []

  on('env.get', (_, e) => ({ value: { HC_TERMINAL_ID: 't7', HOME: '/home/me' }[e.name] }))
  on('session.model', () => ({ value: 'claude-opus-5-5' }))
  on('session.usage', () => ({ value: USAGE }))
  on('config.list', () => ({ value: [{ key: 'effortLevel', label: 'Effort', value: 'high' }] }))
  on('fs.write', (_, e) => (writes.push(e), { value: undefined }))
  on('session.measure', (_, e) => ({ changed: e.changed }))

  await $.session.measure(MEASURE)
  await $.session.measure(MEASURE)

  // The second, unchanged report is not written again.
  expect(writes.length).toBe(1)
  expect(writes[0]?.path).toBe('/home/me/.local/state/herdr-session-bar/t7.json')
  const info = JSON.parse(writes[0]?.text ?? '{}')
  expect(info.model).toBe('claude-opus-5-5')
  expect(info.effort).toBe('high')
  expect(info.window).toBe(1_000_000)
  expect(info.meters).toEqual([
    { label: 'ctx', percent: 12 },
    { label: '5h', percent: 42 },
    { label: '7d', percent: 100 },
  ])
  expect(typeof info.at).toBe('number')
})

test('outside Herdr, nothing is written', async ($, on) => {
  let writes = 0

  on('env.get', (_, e) => ({ value: e.name === 'HOME' ? '/home/me' : undefined }))
  on('session.model', () => ({ value: 'claude-opus-5-5' }))
  on('session.usage', () => ({ value: USAGE }))
  on('config.list', () => ({ value: [] }))
  on('fs.write', () => (writes++, { value: undefined }))
  on('session.measure', (_, e) => ({ changed: e.changed }))

  await $.session.measure(MEASURE)

  expect(writes).toBe(0)
})

test('a terminal id with a path in it is refused', async ($, on) => {
  let writes = 0

  on('env.get', (_, e) => ({ value: { HC_TERMINAL_ID: '../../evil', HOME: '/home/me' }[e.name] }))
  on('session.model', () => ({ value: 'claude-opus-5-5' }))
  on('session.usage', () => ({ value: USAGE }))
  on('config.list', () => ({ value: [] }))
  on('fs.write', () => (writes++, { value: undefined }))
  on('session.measure', (_, e) => ({ changed: e.changed }))

  await $.session.measure(MEASURE)

  expect(writes).toBe(0)
})
