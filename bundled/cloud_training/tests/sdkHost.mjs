// Test-only links to the public host. No production SDK closure is implied.
import { registerHooks } from 'node:module';
import net from 'node:net';
import childProcess from 'node:child_process';

const blocked = () => { throw new Error('Cloud projection tests are offline'); };
globalThis.fetch = blocked;
net.Socket.prototype.connect = blocked;
childProcess.spawn = blocked;
childProcess.exec = blocked;
childProcess.execFile = blocked;

const publicUrls = new URL('../../../frontend/src/components/videobank/videoBankApi.js', import.meta.url).href;
const source = `export { videoDatasetCloudUrl, videoDatasetUrl } from ${JSON.stringify(publicUrls)};`;
const bridge = `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`;

registerHooks({
  resolve(specifier, context, nextResolve) {
    return nextResolve(specifier === '@lds/plugin-sdk/cloud-host' ? bridge : specifier, context);
  },
});
