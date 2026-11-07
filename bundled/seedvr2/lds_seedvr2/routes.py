from flask import Blueprint, current_app, jsonify
from lds_sdk.lifecycle import is_available

bp = Blueprint('seedvr2', __name__)

@bp.before_request
def active_product():
    if not is_available('seedvr2'):
        return jsonify({'error': 'Enable SeedVR2 and restart LDS.'}), 409

@bp.get('/seedvr2/models')
def seedvr2_models_list():
    """The SeedVR2 DiT builds actually PRESENT in this install's SEEDVR2 folder(s),
    plus the catalog of builds the app can talk about.

    ``{installed: [name], catalog: [{file, label, size_gb, vram_gb, recommended,
    installed}], resolved: name|null, vae: name|null,
    vae_choices: [{file, likely_vae}]}``.

    ``vae_choices`` covers the WHOLE folder, each entry flagged with whether its
    name looks like a VAE: the automatic path already handles every install
    where it does, so the pin exists for the one where it does not, and a picker
    that hid those files could not express that install.

    Only installed builds are offered as a pin: the pack's loader nodes download
    an unknown name on first use, so a picker listing everything would turn a
    dropdown into a silent multi-gigabyte download. The catalog is still returned
    so the card can SHOW what else exists (with its size and VRAM guidance) and
    say it has to be placed in the folder — informing is not fetching.

    Degrades to empty lists rather than an error when ComfyUI is unconfigured."""
    from . import seedvr2_helper as svr
    try:
        installed = svr.installed_dit_models()
        resolved = svr.resolve_seedvr2_dit()
        vae = svr.resolve_seedvr2_vae()
        vae_choices = svr.vae_choices()
    except Exception:
        current_app.logger.exception('seedvr2 model scan failed')
        installed, resolved, vae, vae_choices = [], None, None, []
    catalog = [{**v, 'installed': v['file'] in installed} for v in svr.DIT_VARIANTS]
    return jsonify({'installed': installed, 'catalog': catalog,
                    'resolved': resolved, 'vae': vae,
                    'vae_choices': vae_choices})
