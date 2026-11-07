"""Public LAION aesthetic head; no Image Bank inference policy."""
import os
from _harness import _log

_AESTHETIC_URL = ('https://github.com/christophschuhmann/improved-aesthetic-predictor/'
                  'raw/main/sac+logos+ava1-l14-linearMSE.pth')
_AESTHETIC_FILE = 'sac+logos+ava1-l14-linearMSE.pth'

def _aesthetic_mlp():
    """The improved-aesthetic-predictor MLP (768→1) as an nn.Module."""
    import torch.nn as nn

    class _MLP(nn.Module):
        def __init__(self):
            super().__init__()
            self.layers = nn.Sequential(
                nn.Linear(768, 1024), nn.Dropout(0.2),
                nn.Linear(1024, 128), nn.Dropout(0.2),
                nn.Linear(128, 64), nn.Dropout(0.1),
                nn.Linear(64, 16), nn.Linear(16, 1))

        def forward(self, x):
            return self.layers(x)

    return _MLP()

def _load_aesthetic_head(models_root, device):
    """(module, ok, reason). Downloads the LAION head weights once (cached under
    models_root or the default HF hub cache), returns (None, False, why) on any
    failure so the pass still yields nsfw + style. `why` is a one-line
    "<ExcType>: <message>" the parent puts in front of the user: this fetch is the
    first network call of a pass, so on a machine with no egress it is also the
    reason every score comes back empty — and "unavailable" alone left the user
    with a completed pass, no scores, and nothing to act on."""
    import torch
    try:
        cache_dir = os.path.join(models_root or _default_cache(), 'bank_scoring')
        os.makedirs(cache_dir, exist_ok=True)
        dest = os.path.join(cache_dir, _AESTHETIC_FILE)
        if not os.path.isfile(dest):
            _log('[score] fetching aesthetic head weights (once)…')
            import urllib.request
            urllib.request.urlretrieve(_AESTHETIC_URL, dest + '.part')
            os.replace(dest + '.part', dest)
        head = _aesthetic_mlp()
        # weights_only: the head is a plain tensor state_dict — never unpickle
        # arbitrary objects from a downloaded file.
        state = torch.load(dest, map_location='cpu', weights_only=True)
        head.load_state_dict(state)
        head.to(device).eval()
        return head, True, None
    except Exception as e:  # noqa: BLE001
        reason = _reason(e)
        _log(f'[score] aesthetic head unavailable ({reason}) — '
             'aesthetic scores skipped')
        return None, False, reason

def _reason(exc) -> str:
    """One short "<ExcType>: <message>" line, safe to show in the UI. Trimmed
    because some hub/urllib errors carry a multi-line body with a URL and a
    traceback hint, and this ends up inside a one-line activity sentence."""
    msg = ' '.join(str(exc).split())
    if len(msg) > 160:
        msg = msg[:157] + '…'
    return f'{type(exc).__name__}: {msg}' if msg else type(exc).__name__

def _default_cache():
    from pathlib import Path
    return str(Path.home() / '.cache' / 'lds')
