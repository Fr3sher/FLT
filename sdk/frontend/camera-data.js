// Version 1 stored camera-pose vocabulary. Historical rows keep these identifiers.
/** Where the camera stands. `degrees` is what the dial draws; 0° is the
 *  reference photo's own viewpoint, not a compass bearing. */
export const AZIMUTHS = [
  { id: 'front', degrees: 0, token: 'front view', label: 'Front' },
  { id: 'front_right', degrees: 45, token: 'front-right quarter view', label: 'Front-right' },
  { id: 'right', degrees: 90, token: 'right side view', label: 'Right side' },
  { id: 'back_right', degrees: 135, token: 'back-right quarter view', label: 'Back-right' },
  { id: 'back', degrees: 180, token: 'back view', label: 'Back' },
  { id: 'back_left', degrees: 225, token: 'back-left quarter view', label: 'Back-left' },
  { id: 'left', degrees: 270, token: 'left side view', label: 'Left side' },
  { id: 'front_left', degrees: 315, token: 'front-left quarter view', label: 'Front-left' },
]

/** How high the camera is. Ordered low → high, the way the ladder is drawn. */
export const ELEVATIONS = [
  { id: 'low', degrees: -30, token: 'low-angle shot', label: 'Low', hint: 'from below' },
  { id: 'eye', degrees: 0, token: 'eye-level shot', label: 'Eye level', hint: 'level with the subject' },
  { id: 'elevated', degrees: 30, token: 'elevated shot', label: 'Elevated', hint: 'slightly above' },
  { id: 'high', degrees: 60, token: 'high-angle shot', label: 'High', hint: 'looking down' },
]

/** How far the camera is. ⚠️ The loose axis — see DISTANCE_CAVEAT. */
export const DISTANCES = [
  { id: 'close', factor: 0.6, token: 'close-up', label: 'Close-up' },
  { id: 'medium', factor: 1.0, token: 'medium shot', label: 'Medium' },
  { id: 'wide', factor: 1.8, token: 'wide shot', label: 'Wide' },
]

/** What the picture is assumed to already be. The dial lights this ring as
 *  "you are here"; picking it is allowed (it is the control that proves the
 *  lane works) and simply says what it is. */
export const REFERENCE_POSE = 'front/eye/medium'

/** Every pose that exists: 8 azimuths × 4 heights × 3 distances. */
export const POSE_COUNT = 96

export const CAMERA_ANGLE = 'camera_angle'

/** True when this row IS a camera view produced by the lane. */
export const isCameraView = (img) => img?.derivation_kind === CAMERA_ANGLE

export const poseId = (azimuth, elevation, distance) => `${azimuth}/${elevation}/${distance}`

const byId = (list) => Object.fromEntries(list.map((e) => [e.id, e]))
const AZ = byId(AZIMUTHS)
const EL = byId(ELEVATIONS)
const DI = byId(DISTANCES)

/** `'right/low/medium'` → `{azimuth, elevation, distance}`, or null.
 *  Null rather than a throw for anything malformed: this parses values that
 *  arrive from the server and from old rows, and a tile with an unreadable
 *  pose should render without a label, not crash the grid. */
export function parsePose(value) {
  if (typeof value !== 'string') return null
  const parts = value.split('/')
  // Exactly three, like the Python side: destructuring alone would accept
  // 'right/low/wide/extra' and quietly label a row from a string the server
  // would have refused.
  if (parts.length !== 3) return null
  const [a, e, d] = parts
  if (!AZ[a] || !EL[e] || !DI[d]) return null
  return { azimuth: a, elevation: e, distance: d }
}

/** The label a tile shows under a camera view. Null when unreadable. */
export function poseLabel(value) {
  const p = parsePose(value)
  if (!p) return null
  return `${AZ[p.azimuth].label} · ${EL[p.elevation].label} · ${DI[p.distance].label}`
}
