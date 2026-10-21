from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1]
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1440,'height':900})
 errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 modules=[]
 for name in ('core.js','technology.js','benchmarks.js'):
  modules.append((root/name).read_text().replace('export const ','const ').replace('export function ','function '))
 modules.append('\n'.join(x for x in (root/'app.js').read_text().splitlines() if not x.startswith('import ')))
 page.set_content('<html><head><style>'+(root/'styles.css').read_text()+'</style></head><body><div id="app"></div></body></html>')
 page.evaluate("""() => {const map=new Map();Object.defineProperty(window,'localStorage',{configurable:true,value:{getItem:k=>map.has(k)?map.get(k):null,setItem:(k,v)=>map.set(k,String(v)),removeItem:k=>map.delete(k),clear:()=>map.clear()}})}""")
 page.add_script_tag(content='\n'.join(modules))
 page.get_by_role('navigation',name='Main navigation').get_by_role('button',name='Run tests',exact=True).click()
 page.get_by_role('navigation',name='Run tests sections').get_by_role('button',name='External benchmarks',exact=True).click()
 assert page.locator('#swe-custom').input_value()=='10'
 assert '30 of 300' in page.locator('#swe-count').inner_text()
 page.get_by_role('button',name='25% · 75').click()
 assert '75 of 300' in page.locator('#swe-count').inner_text()
 page.locator('#swe-seed').fill('777');page.locator('#swe-seed').dispatch_event('change')
 page.get_by_role('button',name='Full · 300').click()
 assert '300 of 300' in page.locator('#swe-count').inner_text()
 page.screenshot(path=str(root/'test-results'/'swe-desktop.png'),full_page=True)
 page.get_by_role('navigation',name='Main navigation').get_by_role('button',name='Home',exact=True).click();page.get_by_role('navigation',name='Main navigation').get_by_role('button',name='Run tests',exact=True).click();page.get_by_role('navigation',name='Run tests sections').get_by_role('button',name='External benchmarks',exact=True).click()
 assert page.locator('#swe-custom').input_value()=='100'
 assert page.locator('#swe-seed').input_value()=='777'
 page.set_viewport_size({'width':390,'height':844})
 assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'mobile overflow'
 page.screenshot(path=str(root/'test-results'/'swe-mobile.png'),full_page=True)
 assert not errors,errors
 browser.close()
print('PASS: SWE-bench UI, presets, persistence, mobile responsive, zero page errors (isolated browser storage)')
