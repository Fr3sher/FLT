import { markdownHeadingId } from '../utils/headingId.js'
import { CORE_GUIDE_ANCHORS } from '../help/guideHosts.js'
import { vastUrl } from '../utils/vastReferral.js'

const NAME = /^[a-z0-9][a-z0-9_.-]*$/
const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key)

export function guideHeadings(markdown) {
  let fenced = false
  const found = []
  for (const line of markdown.replace(/\r\n/g, '\n').split('\n')) {
    if (line.startsWith('```')) fenced = !fenced
    const match = !fenced && line.match(/^#{2,3}\s+(.+)$/)
    if (match) found.push(markdownHeadingId(match[1]))
  }
  return found
}

/** A guide belongs to its installed manifest, including its DOM anchors. */
export function validateGuide(descriptor, registered, ownership) {
  if (descriptor.guide === undefined) return null // SDK 1.6 packages remain valid.
  const guide = descriptor.guide
  if (!guide || typeof guide !== 'object' || Array.isArray(guide) || Object.keys(guide).some(k => !['chapters', 'sections'].includes(k))) return 'Invalid guide content.'
  const { chapters = [], sections = [] } = guide
  if (!Array.isArray(chapters) || !Array.isArray(sections) || chapters.length > 12 || sections.length > 150) return 'Invalid guide chapter/section list.'
  if (!ownership || !Array.isArray(ownership.chapters) || !Array.isArray(ownership.sections)) return 'Guide content requires manifest ownership.'
  const chapterIds = new Set(Object.keys(CORE_GUIDE_ANCHORS))
  const anchors = new Set(Object.entries(CORE_GUIDE_ANCHORS).flatMap(([id, names]) => names.map(n => `${id}#${n}`)))
  for (const other of registered) {
    for (const chapter of other.guide?.chapters || []) chapterIds.add(chapter.id)
    for (const section of other.guide?.sections || []) for (const anchor of guideHeadings(section.markdown)) anchors.add(`${section.chapter}#${anchor}`)
  }
  const allowedChapters = new Set(Object.keys(CORE_GUIDE_ANCHORS))
  for (const chapter of chapters) {
    if (!chapter || typeof chapter.id !== 'string' || !NAME.test(chapter.id) || !chapter.id.startsWith(`${descriptor.id}.`) || typeof chapter.title !== 'string' || !chapter.title.trim() || typeof chapter.description !== 'string') return 'A product guide chapter needs a namespaced id, title and description.'
    if (chapterIds.has(chapter.id)) return `Guide chapter collision: ${chapter.id}`
    chapterIds.add(chapter.id)
    allowedChapters.add(chapter.id)
  }
  const sectionIds = []
  for (const section of sections) {
    if (!section || !allowedChapters.has(section.chapter) || typeof section.anchor !== 'string' || !NAME.test(section.anchor) || typeof section.markdown !== 'string' || !section.markdown.trim() || section.markdown.length > 250000) return 'Invalid owned guide section.'
    if (section.after !== undefined && (!own(CORE_GUIDE_ANCHORS, section.chapter) || !CORE_GUIDE_ANCHORS[section.chapter].includes(section.after))) return 'A guide section may follow only an existing core anchor.'
    const heading = section.markdown.match(/^##\s+(.+)\r?\n/)
    if (!heading || markdownHeadingId(heading[1]) !== section.anchor || (section.markdown.match(/^##\s+/gm) || []).length !== 1) return 'Each guide section needs one matching H2 heading.'
    sectionIds.push(`${section.chapter}#${section.anchor}`)
    for (const anchor of guideHeadings(section.markdown)) {
      const key = `${section.chapter}#${anchor}`
      if (anchors.has(key)) return `Guide anchor collision: ${key}`
      anchors.add(key)
    }
  }
  if (sections.reduce((size, section) => size + section.markdown.length, 0) > 1000000) return 'Guide content is too large.'
  if (chapters.some(chapter => !sections.some(section => section.chapter === chapter.id))) return 'A guide chapter needs content.'
  const same = (a, b) => a.length === b.length && new Set(a).size === a.length && a.every(id => b.includes(id))
  if (!same(chapters.map(c => c.id), ownership.chapters) || !same(sectionIds, ownership.sections)) return 'Guide content differs from its manifest ownership.'
  return null
}

/** Add active product sections to the existing reader; never substitute a core section. */
export function composeGuide(coreChapters, descriptors) {
  const chapters = coreChapters.map(chapter => ({ ...chapter }))
  for (const descriptor of descriptors) for (const chapter of descriptor.guide?.chapters || []) {
    chapters.push({ ...chapter, num: '+', plugin: descriptor.id, source: '' })
  }
  for (const chapter of chapters) {
    const sections = descriptors.flatMap(descriptor => (descriptor.guide?.sections || [])
      .filter(section => section.chapter === chapter.id).map(section => ({ ...section, plugin: descriptor.id })))
    const original = chapter.source.split(/(?=^##\s)/m)
    const added = new Set()
    chapter.source = original.map(part => {
      const match = part.match(/^##\s+(.+)/)
      const anchor = match && markdownHeadingId(match[1])
      const after = sections.filter(s => s.after === anchor)
      for (const section of after) added.add(section)
      return [part.trimEnd(), ...after.map(s => s.markdown.trim())].join('\n\n')
    }).join('\n\n')
    chapter.source += '\n\n' + sections.filter(s => !added.has(s)).map(s => s.markdown.trim()).join('\n\n')
    chapter.source = chapter.source.replace(/lds-guide:vast:(tagged|plain):(\/[a-z0-9/-]*)/g,
      (_match, mode, path) => vastUrl(path, mode === 'plain' ? '' : undefined))
  }
  return chapters
}

export function findGuideChapter(chapters, id) {
  return id ? chapters.find(chapter => chapter.id === id) || null : chapters[0] || null
}
