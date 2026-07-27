"""Honest diagnosis of a LOCAL training run that died.

Two pure helpers — no GPU, no ai-toolkit, no filesystem — so both are testable
with plain strings and simulated probe payloads:

* `extract_error_excerpt` picks the part of a training log that EXPLAINS the
  failure (the last traceback, else the last real error line) instead of the
  raw tail. ai-toolkit's very first lines are usually a harmless
  `FutureWarning` from huggingface_hub, and a run that dies before writing
  anything else made the panel show that warning in red as if it were the
  cause. When nothing in the log looks like an error we say so, in plain
  words, instead of dressing the last lines up as one.

* `torch_arch_verdict` turns a torch/GPU probe into a verdict on whether the
  installed PyTorch actually ships kernels for this GPU. The RTX 50 trap:
  Blackwell is compute capability 12.0 (`sm_120`) while stable PyTorch wheels
  only carry kernels up to `sm_90`. `torch.cuda.is_available()` still returns
  True, the GPU is named correctly, buckets and datasets are built — then the
  FIRST real kernel launch dies with "no kernel image is available for
  execution on the device" and ai-toolkit exits 1 with nothing useful said.

Both return "I don't know" (kind `none` / `None`) rather than guessing: the
absence of information is never reported as a diagnosis.

Surfaced by the failure block in TrainingPanel and by the training preflight.
The Blackwell trap was reported by wannadecryptor (Discord, RTX 5070).
"""
import re

from ..utils.redact import redact_tokens, redact_user_paths

# How many lines of the log the excerpt may show. Small enough to stay readable
# on a phone, big enough for a real traceback.
MAX_EXCERPT_LINES = 14

_TRACEBACK_MARK = 'traceback (most recent call last)'

# What "something actually went wrong" looks like in a training log. Ordered
# from most to least specific; any hit makes a line a candidate cause.
_ERROR_RE = re.compile(r"""(?xi)
    \bno\s+kernel\s+image\b                 # the Blackwell / wrong-arch death
  | \bout\s+of\s+memory\b
  | \b[A-Za-z_][\w.]*Error\b                # RuntimeError, OSError, torch.cuda.OutOfMemoryError
  | \b[A-Za-z_][\w.]*Exception\b
  | \berror\b\s*[:=]                        # "CUDA error: ...", "error: ..."
  | \btraceback\b
  | \bassert(?:ion)?\s+(?:failed|error)\b
  | \b(?:killed|aborted|segmentation\s+fault)\b
  | \bfailed\b
""")

# A line that is merely a warning is NEVER a candidate cause, whatever error-ish
# words it happens to contain — that is the whole point of this module.
_WARNING_RE = re.compile(r'\b\w*Warning\b|\bwarnings?\.warn\b|^\s*warn(?:ing)?\b', re.IGNORECASE)


def _clean_lines(log_text):
    """Log text -> non-empty, path-redacted lines. tqdm rewrites its progress bar
    with \\r, so carriage returns are treated as line breaks: only the last state
    of a bar survives, instead of one mile-long line."""
    if not log_text:
        return []
    text = redact_tokens(redact_user_paths(str(log_text)))
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    return [line.rstrip() for line in text.split('\n') if line.strip()]


def _cap(lines, max_lines):
    """Keep an excerpt readable: first line + tail, with an explicit marker for
    what was dropped (never a silent truncation)."""
    if len(lines) <= max_lines:
        return list(lines)
    # `max(1, …)`: at max_lines 2 the naive `- 2` gives 0, and `lines[-0:]` is the
    # WHOLE list — a silent no-op cap. Small callers must still get a real cap.
    tail = max(1, max_lines - 2)
    omitted = len(lines) - 1 - tail
    return lines[:1] + [f'... ({omitted} more lines — open training.log for the full run) ...'] \
        + lines[-tail:]


def extract_error_excerpt(log_text, max_lines=MAX_EXCERPT_LINES) -> dict:
    """What of this log explains the failure.

    Returns {'kind', 'text', 'headline'} where `kind` is:
      * 'traceback' — the last Python traceback in the log (the strongest signal);
      * 'error'     — the last non-warning line that reads like an error, with a
                      couple of lines of context around it;
      * 'none'      — nothing in the log looks like an error. `text` is then the
                      plain tail, and the caller MUST present it as context, not
                      as a cause (see `headline`: empty).
    `headline` is the one-line summary (the exception line / the error line),
    empty when kind is 'none'. Everything is already path-redacted."""
    lines = _clean_lines(log_text)
    if not lines:
        return {'kind': 'none', 'text': '', 'headline': ''}

    # 1) The LAST traceback wins: a run can survive an earlier caught one.
    start = None
    for i, line in enumerate(lines):
        if _TRACEBACK_MARK in line.lower():
            start = i
    if start is not None:
        block = lines[start:]
        return {'kind': 'traceback', 'text': '\n'.join(_cap(block, max_lines)),
                'headline': block[-1].strip()}

    # 2) Otherwise the last error-looking line that is NOT a warning.
    idx = None
    for i, line in enumerate(lines):
        if _WARNING_RE.search(line):
            continue
        if _ERROR_RE.search(line):
            idx = i
    if idx is not None:
        block = lines[max(0, idx - 2):idx + 3]
        return {'kind': 'error', 'text': '\n'.join(_cap(block, max_lines)),
                'headline': lines[idx].strip()}

    # 3) Nothing. Say nothing — the caller shows the tail as context only.
    return {'kind': 'none', 'text': '\n'.join(lines[-max_lines:]), 'headline': ''}


# --- gated Hugging Face repo: 401 is NOT 403 -----------------------------------
# Every family with a license-gated base (Krea 2, FLUX.1-dev, FLUX.2 Klein) dies
# the same way when the download is refused, and huggingface_hub prints ONE
# sentence for both cases: "You must have access to it and be authenticated to
# access it". Those are two different problems with two opposite fixes, and
# reading the sentence instead of the status code has already produced a wrong
# public answer (reported by SurpassHR on GitHub, training on Krea 2):
#
#   401 Unauthorized -> the request carried NO valid token. Hugging Face cannot
#                       even tell who is asking. Fix: give the app a token.
#   403 Forbidden    -> the token IS valid; that account has not accepted the
#                       licence / is not on the authorized list. Fix: accept the
#                       licence on the model page. Another token changes nothing.
_GATED_MARK_RE = re.compile(
    r'gatedrepoerror|cannot access gated repo|is restricted|'
    r'must have access to it and be authenticated', re.IGNORECASE)
_HTTP_STATUS_RE = re.compile(r'\b(401|403)\b[^\n]{0,40}?client\s*error', re.IGNORECASE)
# "Access to model krea/Krea-2-Turbo is restricted" — the most reliable shape.
_REPO_TEXT_RE = re.compile(
    r'access to (?:model|repo(?:sitory)?)\s+([\w.\-]+/[\w.\-]+)', re.IGNORECASE)
# Fallback: the resolve URL. `settings`/`docs`/... are site pages, not repos.
_REPO_URL_RE = re.compile(r'huggingface\.co/([\w.\-]+/[\w.\-]+)', re.IGNORECASE)
_NOT_A_REPO_OWNER = {'settings', 'docs', 'api', 'join', 'login', 'pricing', 'blog'}

GATED_401_TITLE = 'Hugging Face saw no valid token — this is not a licence problem'
GATED_403_TITLE = 'Your token works — the licence has not been accepted yet'


def gated_repo_verdict(log_text, token_configured=None) -> dict | None:
    """Did this run die on a gated Hugging Face repo, and WHY exactly?

    Returns None when the log shows no gated-repo refusal (never a guess).
    Otherwise {'status': 401|403, 'repo', 'url', 'title', 'message'} — already
    path-redacted and token-redacted, and never echoing a token itself.

    `token_configured` (optional) is whether the app HAS a Hugging Face token
    saved: with one, a 401 means the token was rejected (expired/revoked/typo),
    which is a different sentence from "you have no token".
    """
    lines = _clean_lines(log_text)
    if not lines:
        return None
    text = '\n'.join(lines)
    if not _GATED_MARK_RE.search(text):
        return None
    m = _HTTP_STATUS_RE.search(text)
    if not m:
        return None
    status = int(m.group(1))

    repo = ''
    hit = _REPO_TEXT_RE.search(text)
    if hit:
        repo = hit.group(1)
    else:
        for cand in _REPO_URL_RE.findall(text):
            if cand.split('/', 1)[0].lower() not in _NOT_A_REPO_OWNER:
                repo = cand
                break
    name = repo or 'the base model'
    url = f'https://huggingface.co/{repo}' if repo else 'the model page on huggingface.co'

    if status == 403:
        return {
            'status': 403, 'repo': repo, 'url': url, 'title': GATED_403_TITLE,
            'message': (
                f'Hugging Face recognised the token but that account has not been granted '
                f'access to {name} (HTTP 403 Forbidden). Adding another token will not help. '
                f'Open {url} while signed in with the SAME account the token belongs to, '
                f'accept the model licence, wait for it to show as granted, then train again.'),
        }
    if token_configured:
        detail = ('A Hugging Face token IS saved in Settings ▸ API keys, so that token was '
                  'rejected — typically expired, revoked, or missing read access. Create a '
                  'fresh read token at https://huggingface.co/settings/tokens, paste it over '
                  'the old one, then train again.')
    else:
        detail = ('No Hugging Face token is saved in Settings ▸ API keys. Create a read token '
                  'at https://huggingface.co/settings/tokens and paste it there, then train '
                  'again. (A token from `hf auth login` is picked up too, but only when the '
                  'CLI ran as the same user as this app.)')
    return {
        'status': 401, 'repo': repo, 'url': url, 'title': GATED_401_TITLE,
        'message': (
            f'The download of {name} was refused as NOT AUTHENTICATED (HTTP 401). Hugging Face '
            f'could not tell who was asking, so this says nothing about whether you have been '
            f'granted access — asking for access again will not fix it. {detail}'),
    }


# --- torch build vs GPU architecture -------------------------------------------
# `sm_120` -> (12, 0); `sm_86` -> (8, 6). CUDA cubins are binary-compatible
# INSIDE a major version (an sm_86 kernel runs on an sm_89 RTX 4090, which is
# why stable wheels ship no sm_89 and the 4090 works anyway) but never across
# majors — an sm_90 build has nothing to run on Blackwell (major 12).
# `compute_XX` (PTX) entries are deliberately ignored: forward JIT across a major
# generation is not what stable wheels actually deliver, and every field report
# of an RTX 50 on a stable build is the same hard "no kernel image" failure.
_SM_RE = re.compile(r'^sm_(\d+)(\d)[a-z]*$', re.IGNORECASE)

# The first architecture whose only remedy is the cu128 wheel index (Blackwell,
# RTX 50-series). Below that we describe the mismatch but invent no command.
BLACKWELL_MAJOR = 12
CU128_INDEX_URL = 'https://download.pytorch.org/whl/cu128'


def torch_arch_verdict(info, venv_python=None) -> dict | None:
    """Does the installed torch ship kernels this GPU can run?

    `info` is the raw probe payload (see capabilities.aitoolkit_torch_info):
    {'torch', 'cuda', 'capability': [major, minor], 'arch_list': [...],
     'device_name'}. Returns None whenever the answer is UNKNOWN — probe absent,
     no GPU, unparseable arch list. None is never a claim of incompatibility.

    Returns {'supported', 'sm', 'gpu', 'torch', 'built_up_to', 'blackwell',
    'message', 'command'} otherwise. `command` is '' when we have no remedy we
    can honestly name."""
    if not isinstance(info, dict) or info.get('error'):
        return None
    cap = info.get('capability')
    if not (isinstance(cap, (list, tuple)) and len(cap) == 2):
        return None
    try:
        major, minor = int(cap[0]), int(cap[1])
    except (TypeError, ValueError):
        return None
    built = []
    for arch in (info.get('arch_list') or []):
        m = _SM_RE.match(str(arch).strip())
        if m:
            built.append((int(m.group(1)), int(m.group(2))))
    if not built:
        return None

    sm = f'sm_{major}{minor}'
    supported = any(bmaj == major and bmin <= minor for bmaj, bmin in built)
    top = max(built)
    gpu = (info.get('device_name') or '').strip() or 'this GPU'
    torch_version = (info.get('torch') or '').strip() or 'the installed PyTorch'
    verdict = {'supported': supported, 'sm': sm, 'gpu': gpu, 'torch': torch_version,
               'built_up_to': f'sm_{top[0]}{top[1]}',
               'blackwell': major >= BLACKWELL_MAJOR, 'message': '', 'command': ''}
    if supported:
        verdict['message'] = (f'{gpu} is compute capability {major}.{minor} ({sm}) and '
                              f'PyTorch {torch_version} ships kernels for it.')
        return verdict

    verdict['message'] = (
        f'{gpu} is compute capability {major}.{minor} ({sm}), but the PyTorch installed in '
        f'the ai-toolkit venv ({torch_version}) only ships GPU kernels up to '
        f'sm_{top[0]}{top[1]}. CUDA still reports the card as available and training starts '
        'normally, then dies at the first real GPU computation with "no kernel image is '
        'available for execution on the device".')
    if major >= BLACKWELL_MAJOR:
        python = redact_user_paths(str(venv_python).strip()) if venv_python else ''
        exe = f'"{python}"' if python else '<ai-toolkit venv python>'
        verdict['command'] = (f'{exe} -m pip install --force-reinstall torch torchvision '
                              f'--index-url {CU128_INDEX_URL}')
    return verdict
