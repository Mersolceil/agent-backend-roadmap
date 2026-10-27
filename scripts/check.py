#!/usr/bin/env python3
"""Check the published curriculum and reproduce its JSON without changing the checkout."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'dist'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def index_unique(rows, label):
    result = {row['id']: row for row in rows}
    require(len(result) == len(rows), f'duplicate {label} id')
    return result


def check_graph(nodes, name):
    visiting, visited = set(), set()
    def visit(key):
        require(key not in visiting, f'{name}: dependency cycle at {key}')
        if key in visited:
            return
        visiting.add(key)
        for dep in nodes[key].get('deps', []):
            require(dep in nodes, f'{name}: {key} refers to missing {dep}')
            visit(dep)
        visiting.remove(key)
        visited.add(key)
    for key in nodes:
        visit(key)


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for field in ('src', 'href'):
            value = attrs.get(field, '')
            parsed = urlparse(value)
            if value and not parsed.scheme and not value.startswith('#') and parsed.path:
                self.paths.append(unquote(parsed.path))


def main():
    data = json.loads((SITE / 'knowledge.json').read_text(encoding='utf-8'))
    modules = index_unique(data['modules'], 'module')
    domains = index_unique(data['domains'], 'domain')
    gates = index_unique(data['gates'], 'gate')
    sources = index_unique(data['sources'], 'source')
    topics = index_unique([t for m in modules.values() for t in m['topics']], 'topic')
    items = index_unique([i for t in topics.values() for i in t['items']], 'item')
    require(all(data[key] for key in ('domains', 'modules', 'gates', 'sources')), 'empty curriculum')
    check_graph(modules, 'modules')
    for domain in domains.values():
        require(all(key in modules for key in domain['modules']), f"unknown module in {domain['id']}")
    require(sorted(key for d in domains.values() for key in d['modules']) == sorted(modules),
            'each module must appear in exactly one domain')
    for module in modules.values():
        require(module['domain'] in domains, f"unknown domain in {module['id']}")
        require(module['id'] in domains[module['domain']]['modules'], f"domain mismatch in {module['id']}")
        require(all(key in sources for key in module['sources']), f"unknown source in {module['id']}")
        for topic in module['topics']:
            for item in topic['items']:
                require(item['module'] == module['id'] and item['topic'] == topic['id'],
                        f"item association mismatch: {item['id']}")
                require(all(key in sources for key in item.get('sources', [])), f"unknown source in {item['id']}")
    for gate in gates.values():
        require(all(key in items for key in gate['requiredRefs']), f"unknown item in gate {gate['id']}")
        require(all(key in modules or key in gates for key in gate['deps']), f"unknown gate dependency in {gate['id']}")
    route = (SITE / '路线图.md').read_text(encoding='utf-8')
    for item in items.values():
        level = '条件必学' if item.get('conditional') else item['level']
        cells = [item['id'], level, item['name'], item['depth']]
        row = '| ' + ' | '.join(cell.replace('|', '\\|') for cell in cells) + ' |'
        require(row in route, f"downloadable roadmap out of sync: {item['id']}")
    evidence = (SITE / '证据与修订.md').read_text(encoding='utf-8')
    for source in sources.values():
        require('## ' + source['id'] + ' · ' + source['title'] in evidence,
                f"downloadable evidence out of sync: {source['id']}")
    parser = Assets()
    parser.feed((SITE / 'index.html').read_text(encoding='utf-8'))
    for path in parser.paths:
        require((SITE / path).is_file(), f'missing HTML resource: {path}')
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / 'research').mkdir()
        (root / 'dist').mkdir()
        shutil.copy2(ROOT / 'build_curriculum.py', root / 'build_curriculum.py')
        shutil.copy2(ROOT / 'research/knowledge-v1.json', root / 'research/knowledge-v1.json')
        subprocess.run([sys.executable, str(root / 'build_curriculum.py')], cwd=root,
                       check=True, capture_output=True, text=True)
        rebuilt = json.loads((root / 'dist/knowledge.json').read_text(encoding='utf-8'))
        require(data == rebuilt, 'generated knowledge.json differs from committed data')
    print(f"OK: {len(domains)} domains, {len(modules)} modules, {len(topics)} topics, "
          f"{len(items)} learning units, {len(gates)} project gates, {len(sources)} sources")
    print('OK: dependencies, references, downloadable item/source lists, assets and reproducible JSON')


if __name__ == '__main__':
    main()
