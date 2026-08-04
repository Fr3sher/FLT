def register_blueprints(app, csrf):
    from importlib import import_module
    for name in ('settings', 'datasets', 'training', 'studio', 'bench', 'setup', 'setup_state',
                 'scrape', 'ollama', 'backup', 'bank', 'system', 'tools'):
        try:
            mod = import_module(f'app.routes.{name}')
        except ImportError:
            continue  # blueprint not built yet (earlier phases)
        app.register_blueprint(mod.bp)
