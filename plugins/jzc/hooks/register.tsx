// A plugin loads one hooks module, so this entry registers every mod under
// hooks/mods/. Each mod exports its own `register`; add a line here per mod.
import type { Register } from 'claude-code'

import { register as skillsUsed } from './mods/skills-used'

export const register: Register = (on, options) => {
  skillsUsed(on, options)
}
