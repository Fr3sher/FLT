"""DLSS 5: standalone video finishing, with optional Video integrations."""


def register(ctx):
    from . import jobs, neural_render, routes, runtime, video_routes
    runtime.register(ctx)
    ctx.register_blueprint(routes.bp, url_prefix='/api/dlss5')
    ctx.register_blueprint(video_routes.bp, url_prefix='/api')
    ctx.register_request_limit('dlss5.upload', jobs.MAX_UPLOAD + 1024 * 1024)
    ctx.register_probe('dlss5nr', neural_render.status)
    ctx.register_install_action('dlss5nr_bridge', label='DLSS 5 neural rendering bridge',
                                run=lambda log: neural_render.install_bridge(log=log))
    ctx.register_boot_hook(jobs.recover)
