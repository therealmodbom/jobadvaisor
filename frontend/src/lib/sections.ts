/** The address of the settings page; a section adds `/<section>`. */
export const SETTINGS_HASH = '#/einstellungen'

/** The sections of the settings page, in order; the first is the default for an unknown name. */
export const SECTIONS = [
  { id: 'scoren', label: 'Scoren' },
  { id: 'postfach', label: 'Postfach' },
] as const

export type SectionId = (typeof SECTIONS)[number]['id']

/** The address of a section (`#/einstellungen/<id>`). */
export const sectionHash = (id: SectionId) => `${SETTINGS_HASH}/${id}`
