from pathlib import Path
from playwright.sync_api import sync_playwright
BASE=Path(__file__).resolve().parents[1]
def read_mod(name):
 return (BASE/name).read_text().replace('export const ','const ').replace('export function ','function ')
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1400,'height':850})
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 app='\n'.join(x for x in (BASE/'app.js').read_text().splitlines() if not x.startswith('import '))
 script='\n'.join([read_mod('core.js'),read_mod('technology.js'),read_mod('benchmarks.js'),app])
 page.set_content('<html><head><style>'+(BASE/'styles.css').read_text()+'</style></head><body><div id="app"></div><script>'+script+'</script></body></html>')
 page.get_by_role('button',name='Benchmark library').click()
 assert page.get_by_role('heading',name='Benchmark library').count()==1
 assert page.get_by_text('SWE-bench Lite').count()>=1
 assert page.get_by_text('Terminal-Bench 2.1').count()>=1
 assert page.get_by_text('No benchmark results imported yet').count()==1
 assert page.get_by_text('No fabricated scores are shown').count()==1
 page.screenshot(path='/mnt/data/basis-benchmark-desktop.png',full_page=True)
 page.set_viewport_size({'width':390,'height':844})
 assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), 'horizontal overflow'
 page.screenshot(path='/mnt/data/basis-benchmark-mobile.png',full_page=True)
 assert not errors,errors
 browser.close()
print('PASS benchmark UI desktop/mobile, catalog navigation, no fabricated results, no console page errors')
