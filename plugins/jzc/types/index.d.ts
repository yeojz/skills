// The jzc plugin's state contract. Each mod keeps its values under keys
// prefixed with the mod's name, so two mods never share a key.
export type SkillUse = {
  skill: string
  source: string
  pluginName?: string
  at: number
}

declare module 'claude-code' {
  interface PluginState {
    jzc: { 'skills-used.uses': Shaped<SkillUse[]> }
  }
}
