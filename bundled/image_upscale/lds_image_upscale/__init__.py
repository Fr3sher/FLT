"""Klein improvement, independently installed from restoration engines."""
def register(ctx):
    from . import klein_improve, finishing
    ctx.register_restore_engine('klein', preflight=klein_improve.preflight,
                                enqueue=klein_improve.enqueue,
                                error_response=lambda error: None,
                                profile=klein_improve.profile, instruction=klein_improve.instruction,
                                preset_rows=klein_improve.preset_rows, finishing=finishing.profile)
