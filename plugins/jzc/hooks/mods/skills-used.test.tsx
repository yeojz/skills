import { expect, test } from 'claude-code/testing'

const PANE = {
  plugin: 'jzc',
  component: 'Pane',
  requestId: 'skills-used',
  props: {
    title: 'Skills used',
    isFocused: false,
    bodyColumns: 40,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 20 },
    view: {},
  },
} as const

test('the pane lists invoked skills with counts, on every surface', async ($, on) => {
  on('command.register', () => ({ value: { command: 'jzc-skills-used' } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('skill.prompt', (_, e) => ({ text: e.text }))
  on('clock.now', () => ({ value: 0 }))

  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  await $.skill.prompt({ skill: 'commit', text: 'x', source: 'plugin', pluginName: 'jz' })
  await $.skill.prompt({ skill: 'commit', text: 'x', source: 'plugin', pluginName: 'jz' })
  await $.skill.prompt({ skill: 'simplify', text: 'y' })

  for (const surface of ['terminal', 'desktop', 'vscode', 'mobile'] as const) {
    const ui = await $.ui.mount({ ...PANE, surface })
    expect((await ui.find({ type: 'Text', text: /commit/ }))?.text).toMatch(/commit ×2 \(jz\)$/)
    expect((await ui.find({ type: 'Text', text: /simplify/ }))?.text).toMatch(/simplify \(built-in\)$/)
    expect((await ui.find({ type: 'Text', text: /invocations/ }))?.text).toBe('2 skills, 3 invocations')
    await ui.unmount()
  }
})

// The engine stamps origin and presentation on a run; a test states them.
const RUN = {
  command: 'jzc-skills-used',
  args: '',
  origin: { kind: 'sdk' },
  presentation: { isFullscreen: false, columns: 80 },
} as const

test('the command replies with the distinct skills and reopens the pane', async ($, on) => {
  let opened = 0
  on('command.register', () => ({ value: { command: 'jzc-skills-used' } }))
  on('ui.open', () => {
    opened += 1

    return { value: { isPlaced: true } }
  })
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('skill.prompt', (_, e) => ({ text: e.text }))
  on('clock.now', () => ({ value: 0 }))

  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  expect((await $.command.run(RUN)).text).toBe('No skills invoked yet in this session.')

  await $.skill.prompt({ skill: 'verify', text: 'x', source: 'plugin', pluginName: 'jz' })
  await $.skill.prompt({ skill: 'verify', text: 'x', source: 'plugin', pluginName: 'jz' })
  await $.skill.prompt({ skill: 'pr', text: 'y', source: 'plugin', pluginName: 'jz' })
  expect((await $.command.run(RUN)).text).toBe('Skills used: verify, pr')
  expect(opened).toBe(3)
})

test('the pane says so when nothing was invoked', async $ => {
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect((await ui.find({ type: 'Text' }))?.text).toBe('No skills invoked yet.')
  await ui.unmount()
})

test('a value an earlier version stored is declined', async ($, on) => {
  on('state.get', () => ({
    value: { value: [{ skill: 'verify' }], version: 1 },
  }))

  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect((await ui.find({ type: 'Text' }))?.text).toBe('No skills invoked yet.')
  await ui.unmount()
})
