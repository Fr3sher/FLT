// Compatibility entry point for the bundled Canvas tests. Publish the real
// application host before their modules load; no SDK service is substituted.
import { after } from 'node:test'
import { installRuntimeHost } from './support/runtimeHost.mjs'

installRuntimeHost({ after })
