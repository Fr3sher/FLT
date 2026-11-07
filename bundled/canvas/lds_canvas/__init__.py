"""Canvas workspace: board UI, persisted arrangements and checkpoint generation."""
def register(ctx):
    from .routes import bp
    ctx.register_blueprint(bp, url_prefix='/api')
