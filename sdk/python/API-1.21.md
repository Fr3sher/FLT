# API 1.21 — protect active work during memory release

Plugins with automatic local rendering can register
`system.free_memory_blockers` to protect their work when the user selects
**Free memory**. This includes the gaps between queued jobs in a continuous
channel. The core asks the active plugin instead of importing its runtime.

```python
def memory_blockers(reasons):
    if channel_is_active():
        return list(reasons) + [
            'Stop the channel and let its current clips finish before freeing memory.'
        ]
    return reasons


def register(ctx):
    ctx.register_hook('system.free_memory_blockers', memory_blockers)
```

`channel_is_active()` represents the plugin's own state check; it is not an SDK
function. Return the previous list plus a short instruction when local work
would be interrupted. Preserve reasons supplied by other plugins. The callback
checks state only: it does not stop jobs, release memory or contact a provider.

The core uses the first reason and refuses interruption. Callback errors are
handled as a failed safety check, so the action cannot proceed unchecked.
Disabled plugins do not register the callback. A plugin must separately protect
its own disable operation with `plugin.disable_blockers` when active work would
otherwise be left unattended.

Declare `"compatibility": {"api": ">=1.21,<2"}` alongside the other required
compatibility fields in the manifest. This prevents installation on a host that
does not support the memory guard. The public Live package uses this hook for
its starting, running and stopping local channels.
