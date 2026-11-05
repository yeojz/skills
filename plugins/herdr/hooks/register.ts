// Reports the session's model, effort, context window and usage meters to
// Herdr's session-bar mod, which reads them from
// ~/.local/state/herdr-session-bar/<terminal>.json. Herdr sets HC_TERMINAL_ID in
// every terminal it starts; outside Herdr the variable is unset and nothing is
// written.
//
// The file format follows the session-bar mod in cybertron288/herdr-mods
// (MIT, Copyright (c) 2026 cybertron288), so that mod reads it unchanged.
import type { EngineInterface, Register } from 'claude-code'

type Meter = { label: string; percent: number }

type Info = {
  model: string
  effort: string | null
  window: number | null
  meters: Meter[]
}

// `five_hour` reads as `5h`, `seven_day` as `7d`; any other kind keeps its name.
const limitLabel = (kind: string): string => {
  const name = kind.toLowerCase()

  if (name.includes('five')) return '5h'
  if (name.includes('seven') || name.includes('week')) return '7d'

  return name.replace(/_/g, ' ')
}

const clamp = (percent: number): number => Math.max(0, Math.min(100, Math.round(percent)))

// The file to write, or null outside a Herdr terminal. Looked up once per load.
let target: Promise<string | null> | null = null

function targetPath($: EngineInterface): Promise<string | null> {
  target ??= Promise.all([$.env.get('HC_TERMINAL_ID'), $.env.get('HOME')])
    .then(([terminal, home]) =>
      terminal && home && /^[\w.-]+$/.test(terminal) ? `${home}/.local/state/herdr-session-bar/${terminal}.json` : null,
    )
    .catch(() => null)

  return target
}

// The effort of the latest main-loop model request; null before the first.
let effort: string | null = null

// Before the first request, the effort row of /config, if it has one.
async function configuredEffort($: EngineInterface): Promise<string | null> {
  const rows = await $.config.list().catch(() => [])
  const row = rows.find(r => /effort/i.test(r.key) || /effort/i.test(r.label))

  return row?.value === null || row?.value === undefined || row.value === '' ? null : String(row.value)
}

// What was last written, so an unchanged report is not written again.
let last: string | null = null

async function refresh($: EngineInterface): Promise<void> {
  const path = await targetPath($)

  if (path === null) return

  const [model, usage] = await Promise.all([$.session.model(), $.session.usage()])
  const meters: Meter[] = [
    ...(usage.context.percent == null ? [] : [{ label: 'ctx', percent: clamp(usage.context.percent) }]),
    ...usage.rateLimits.map(limit => ({ label: limitLabel(limit.kind), percent: clamp(limit.percentUsed) })),
  ]
  const info: Info = {
    model,
    effort: effort ?? (await configuredEffort($)),
    window: usage.context.window || null,
    meters,
  }
  const text = JSON.stringify(info)

  if (text === last) return

  last = text
  await $.fs.write(path, JSON.stringify({ ...info, at: Date.now() })).catch(() => {
    last = null
  })
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const result = await next(e)
    await refresh($)

    return result
  })

  on('turn.step', async function* ($, e, next) {
    if (e.agentId === undefined && e.effort !== undefined) {
      effort = String(e.effort)
    }

    return yield* next(e)
  })

  on('turn.complete', async ($, e, next) => {
    const result = await next(e)
    await refresh($)

    return result
  })

  on('session.measure', async ($, e, next) => {
    const result = await next(e)
    await refresh($)

    return result
  })
}
