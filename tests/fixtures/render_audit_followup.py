"""Reuse display fixtures with the actual NewBook JSON decoding method."""

import ast
import os
from pathlib import Path

os.environ['FLASK_ENV'] = 'testing'
root = Path(__file__).resolve().parents[2]
fixture = root / 'tests/fixtures/render_ux_round3.py'
tree = ast.parse(fixture.read_text(encoding='utf8'), filename=str(fixture))
model_tree = ast.parse((root / 'app/models/new_book.py').read_text(encoding='utf8'))
method = next(
    node for node in ast.walk(model_tree) if isinstance(node, ast.FunctionDef) and node.name == 'get_buy_links'
)
book_class = next(node for node in ast.walk(tree) if isinstance(node, ast.ClassDef) and node.name == 'Book')
existing = next(node for node in book_class.body if isinstance(node, ast.FunctionDef) and node.name == 'get_buy_links')
book_class.body[book_class.body.index(existing)] = method
# No application factory, SQLAlchemy model import, database or background jobs.
exec(compile(ast.fix_missing_locations(tree), str(fixture), 'exec'), {'__name__': '__main__'})
