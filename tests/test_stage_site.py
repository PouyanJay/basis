import re
import tempfile
import unittest
from pathlib import Path
from scripts.stage_site import ASSETS, stage_site


class StageSiteTest(unittest.TestCase):
    def test_assets_are_allowlisted_and_versioned_together(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source'
            destination = Path(directory) / 'site'
            source.mkdir()
            for name in ASSETS:
                (source / name).write_text('/* fixture */')
            (source / 'app.js').write_text("import {value} from './core.js';")
            (source / 'index.html').write_text('<link href="styles.css"><script src="app.js"></script>')
            (source / '.env').write_text('DO_NOT_PUBLISH=secret')
            version = stage_site(source, destination)
            first = {p.name for p in destination.iterdir()}
            self.assertEqual(len(first), len(ASSETS) + 1)
            self.assertFalse((destination / '.env').exists())
            self.assertIn(f'./core.{version}.js', (destination / f'app.{version}.js').read_text())
            for ref in re.findall(r'(?:src|href)="([^"]+)"', (destination / 'index.html').read_text()):
                self.assertTrue((destination / ref).exists())
            (source / 'styles.css').write_text('body { color: violet; }')
            updated = stage_site(source, destination)
            self.assertNotEqual(version, updated)
            self.assertEqual(first & {p.name for p in destination.iterdir()}, {'index.html'})
            self.assertIn(f'app.{updated}.js', (destination / 'index.html').read_text())


if __name__ == '__main__':
    unittest.main()
