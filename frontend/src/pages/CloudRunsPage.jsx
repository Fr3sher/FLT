import PluginSlot from '../plugins/PluginSlot.jsx';
import { RunsHub } from '../components/runs/RunsHub.jsx';

// The route and local/history shell survive removal of the cloud package.
export default function CloudRunsPage() {
  return <PluginSlot slot="runs.hub" surface="runs" fallback={<RunsHub />} />;
}
