"""Optional workspace telemetry and its complete readout."""


def register(ctx):
    from .routes import bp
    ctx.register_blueprint(bp, url_prefix='/api/system')
