import { LocationEditor } from '@lds/plugin-sdk/ui';

export default function CloudStorageLocation({ locationProps }) {
  return (
      <LocationEditor id="cloud-runs-dir" storageKey="cloud_runs"
        label="Cloud run staging" section="paths" field="cloud_runs_dir"
        help="Working files of cloud training runs — the exported dataset copy, the sample images and the logs. This is the folder that grows to tens of gigabytes; cleaning a finished run empties it without ever touching a checkpoint."
        {...locationProps('cloud_runs')} />
  )
}
