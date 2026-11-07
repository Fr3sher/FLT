import SystemStatsReadout from './SystemStatsReadout'
import { HEADER_MACHINE_LOAD_PREF_KEY, MACHINE_LOAD_PREF_KEY } from '../lib/systemStats'

export default function Readout({ surface }) {
  const canvas = surface === 'canvas'
  return <SystemStatsReadout
    prefKey={canvas ? MACHINE_LOAD_PREF_KEY : HEADER_MACHINE_LOAD_PREF_KEY}
    defaultEnabled={canvas}
    testId={canvas ? 'canvas-system-stats' : 'header-system-stats'}
    helpTopic="canvas-machine-load" />
}
