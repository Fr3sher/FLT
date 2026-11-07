"""The one supported isolated-script import bootstrap: its own directory."""
import ast


def local_bootstrap_nodes(tree, *, shared_imports=()):
    patterns = [
        'sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))',
    ]
    stores = [n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == '_HERE' and isinstance(n.ctx, ast.Store)]
    assignment = ast.parse('_HERE = os.path.dirname(os.path.abspath(__file__))').body[0]
    if len(stores) == 1 and any(ast.dump(node) == ast.dump(assignment) for node in tree.body):
        patterns.append('if _HERE not in sys.path:\n    sys.path.insert(0, _HERE)')
    templates = {ast.dump(ast.parse(pattern).body[0]) for pattern in patterns}
    allowed = set()
    for statement in tree.body:
        if ast.dump(statement) in templates:
            allowed.update(ast.walk(statement))
    # A worker launched with -I may temporarily expose its own stdlib-only
    # helper. Recognize the complete scope, not arbitrary path assignments.
    save = ast.parse('_import_path = list(sys.path)').body[0]
    insert = ast.parse(patterns[0]).body[0]
    restore = ast.parse('sys.path[:] = _import_path').body[0]
    references = [n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == '_import_path']
    shadowed = any(isinstance(n, ast.alias) and (n.asname or n.name) == '_import_path'
                   for n in ast.walk(tree))
    if shadowed or len(references) != 2 or sum(isinstance(n.ctx, ast.Store) for n in references) != 1:
        return allowed
    for index in range(len(tree.body) - 2):
        before, setup, scope = tree.body[index:index + 3]
        if ast.dump(before) != ast.dump(save) or ast.dump(setup) != ast.dump(insert):
            continue
        if (not isinstance(scope, ast.Try) or scope.handlers or scope.orelse
                or len(scope.finalbody) != 1 or ast.dump(scope.finalbody[0]) != ast.dump(restore)
                or not scope.body or any(not isinstance(node, ast.ImportFrom)
                    or node.level or node.module not in shared_imports
                    or any(alias.name == '*' or (alias.asname or alias.name) == 'sys'
                           for alias in node.names) for node in scope.body)):
            continue
        allowed.update(ast.walk(before))
        allowed.update(ast.walk(scope.finalbody[0]))
    return allowed
