#!/usr/bin/env python3
"""Stage the public app with content-versioned asset URLs for GitHub Pages."""
import argparse
import hashlib
from pathlib import Path

ASSETS = ('app.js', 'core.js', 'technology.js', 'benchmarks.js', 'styles.css', 'brand.svg')


def stage_site(source, destination):
    source, destination = Path(source), Path(destination)
    contents = {name: (source / name).read_text() for name in ('index.html', *ASSETS)}
    digest = hashlib.sha256()
    for name, content in contents.items():
        digest.update(name.encode())
        digest.update(content.encode())
    version = digest.hexdigest()[:16]
    names = {name: f'{Path(name).stem}.{version}{Path(name).suffix}' for name in ASSETS}
    destination.mkdir(parents=True, exist_ok=True)
    # Only replace generated files, never copy arbitrary repository contents.
    for old in destination.iterdir():
        if old.name == 'index.html' or old.name in ASSETS or any(
            old.name.startswith(Path(name).stem + '.') and old.suffix == Path(name).suffix
            for name in ASSETS
        ):
            if old.is_file():
                old.unlink()
    for name in ASSETS:
        content = contents[name]
        if name.endswith('.js'):
            for original, versioned in names.items():
                content = content.replace(f"'./{original}'", f"'./{versioned}'")
                content = content.replace(f'"./{original}"', f'"./{versioned}"')
        (destination / names[name]).write_text(content)
    html = contents['index.html']
    for original, versioned in names.items():
        html = html.replace(f'"{original}"', f'"{versioned}"')
    (destination / 'index.html').write_text(html)
    return version


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default='dist/site')
    args = parser.parse_args()
    version = stage_site(Path(__file__).resolve().parents[1], args.out)
    print(f'Staged public application {version} in {args.out}')
