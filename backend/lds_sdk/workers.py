"""Launch/probe environments must agree on borrowed-interpreter isolation."""


def worker_env(python=None, base=None, **extra):
    from app.services import infer_env
    return infer_env.worker_env(python, base=base, **extra)


def worker_argv(python, *args):
    from app.services import infer_env
    return infer_env.worker_argv(python, *args)


def isolated_worker_argv(python, *args):
    """API 1.15: ignore ambient Python paths, user site and cwd for any interpreter.

    Script-local imports must use explicit paths owned by that script. This
    policy also applies when an explicit override equals the app interpreter.
    """
    return [str(python), '-I', *map(str, args)]


def isolated_worker_env(python=None, base=None, **extra):
    """API 1.15: remove ambient path/base injection, including caller overrides.

    Keep transport settings and unrelated variables. The fresh result protects
    child processes too; argv isolation remains required for the current child.
    """
    env = worker_env(python, base=base, **extra)
    env = {key: value for key, value in env.items()
           if key.upper() not in ('PYTHONHOME', 'PYTHONPATH', 'PYTHONNOUSERSITE')}
    env['PYTHONNOUSERSITE'] = '1'
    return env


__all__ = ['isolated_worker_argv', 'isolated_worker_env', 'worker_argv', 'worker_env']
