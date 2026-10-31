// skills-used: a pane listing the skills invoked in this session, and the
// slash command that reopens it and replies with the list.
//
// The engine does not prefix a command a mod registers with the plugin's
// name, as it does a skill or an agent, so the command carries the prefix
// itself to stay clear of any other plugin's `skills-used`.
import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { SkillUse } from '../../types'

const PANE = 'skills-used'
const TITLE = 'Skills used'
const COMMAND = 'jzc-skills-used'
// Change the tag when a use's fields change: it declines what an earlier
// version stored, which outlives a reload.
const uses = atom({ plugin: 'jzc', key: 'skills-used.uses' } as const, [], {
  shape: 'uses-1',
})

const clock = (ms: number) => {
  const d = new Date(ms)
  const pad = (n: number) => String(n).padStart(2, '0')

  return `${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: COMMAND,
      description: 'Show the skills invoked in this session in a pane',
    })
    void $.ui.open({ id: PANE, title: TITLE })

    return next(e)
  })

  on('command.run', { command: COMMAND }, async $ => {
    await $.ui.open({ id: PANE, title: TITLE })
    const list = await read($, uses)

    return {
      text:
        list.length === 0
          ? 'No skills invoked yet in this session.'
          : `Skills used: ${[...new Set(list.map(use => use.skill))].join(', ')}`,
    }
  })

  // Fires for `/name`, the Skill tool and subagent preloads alike.
  on('skill.prompt', async ($, e, next) => {
    const use: SkillUse = {
      skill: e.skill,
      source: e.source,
      pluginName: e.pluginName,
      at: await $.clock.now(),
    }
    await update($, uses, list => [...list, use].slice(-500))

    return next(e)
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const list = await read($, uses)
    const room = Math.max(1, (e.viewport?.rows ?? 24) - 6)

    const counts = new Map<string, { count: number; last: SkillUse }>()
    for (const use of list) {
      const seen = counts.get(use.skill)
      counts.set(use.skill, { count: (seen?.count ?? 0) + 1, last: use })
    }
    const rows = [...counts.values()].sort((a, b) => b.last.at - a.last.at)

    return (
      <Box flexDirection="column">
        {rows.length === 0 && <Text dimColor>No skills invoked yet.</Text>}
        {rows.length > 0 && (
          <Text dimColor>
            {rows.length} skill{rows.length === 1 ? '' : 's'}, {list.length}{' '}
            invocation{list.length === 1 ? '' : 's'}
          </Text>
        )}
        {rows.slice(0, room).map(({ count, last }) => (
          <Text>
            {clock(last.at)} {last.skill}
            {count > 1 ? ` ×${count}` : ''}
            {last.pluginName ? ` (${last.pluginName})` : ` (${last.source})`}
          </Text>
        ))}
      </Box>
    )
  })
}
