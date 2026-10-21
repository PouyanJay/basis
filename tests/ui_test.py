from playwright.sync_api import sync_playwright
import json, os
ROOT='https://basis.local/'
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
SCREENSHOTS=BASE/'test-results'/'ui'
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1440,'height':900},device_scale_factor=1)
 def load():
  core=(BASE/'core.js').read_text().replace('export const ','const ').replace('export function ','function ')
  app='\n'.join(line for line in (BASE/'app.js').read_text().splitlines() if not line.startswith('import '))
  tech=(BASE/'technology.js').read_text().replace('export const ','const ').replace('export function ','function ') + '\n' + (BASE/'benchmarks.js').read_text().replace('export const ','const ').replace('export function ','function ')
  style=(BASE/'styles.css').read_text().split('\n',1)[1]
  page.set_content('<!doctype html><html><head><style>'+style+'</style></head><body><div id="app"></div><script>window.__testStorage={};Object.defineProperty(window,"localStorage",{value:{getItem:k=>window.__testStorage[k]??null,setItem:(k,v)=>window.__testStorage[k]=v},configurable:true});</script><script>'+core+'\n'+tech+'\n'+app+'</script></body></html>',wait_until='load')
 errors=[]
 page.on('pageerror',lambda err:errors.append(str(err)))
 load()
 assert page.get_by_role("heading",name="Evaluation overview",exact=False).count()==1
 assert 'RECORDED DATA (UNVERIFIED)' in page.locator('body').inner_text()
 assert '30 pilot records' not in page.locator('body').inner_text()
 page.screenshot(path=str(SCREENSHOTS/'desktop.png'),full_page=True)
 for nav,expected in [('Engineering DNA','Engineering DNA'),('Governance','Governance gates'),('Pilot studio','Pilot studio'),('Compare','Comparison lab'),('Technology intel','Technology intelligence'),('Judge integrity','Judge integrity'),('Decision room','Decision room')]:
  page.get_by_role('button',name=nav,exact=True).first.click()
  assert expected in page.locator('body').inner_text(),nav
 assert 'No defensible winner yet' in page.locator('body').inner_text()
 page.get_by_role('button',name='Compare',exact=True).first.click()
 before=page.locator('input[data-range="org.rate"]').input_value()
 page.locator('input[data-range="org.rate"]').fill('250')
 after=page.locator('input[data-range="org.rate"]').input_value()
 assert before!=after,('cost input did not update',before,after)
 page.get_by_role('button',name='Pilot studio',exact=True).first.click()
 page.get_by_role('button',name='Task',exact=True).click()
 page.locator('.modal input[name="name"]').fill('Browser UI test task')
 page.locator('.modal input[name="acceptance"]').fill('Verified by independent tests')
 page.locator('.modal .primary').click()
 page.get_by_role('button',name='Task library').click()
 assert 'Browser UI test task' in page.locator('body').inner_text()
 page.get_by_role('button',name='Governance',exact=True).first.click()
 page.locator('select[data-gate="claude:retention"]').select_option('fail')
 assert page.locator('select[data-gate="claude:retention"]').input_value()=='fail'
 page.evaluate('render()')
 assert page.locator('select[data-gate="claude:retention"]').input_value()=='fail'
 page.set_viewport_size({'width':390,'height':844})
 page.evaluate('render()')
 page.screenshot(path=str(SCREENSHOTS/'mobile.png'),full_page=True)
 assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')
 page.locator('[data-act="menu"]').first.click()
 page.get_by_role('button',name='Engineering DNA').click()
 assert 'Engineering DNA' in page.locator('body').inner_text()
 assert not errors,errors
 browser.close()
print('PLAYWRIGHT UI TESTS PASSED: navigation, scenario cost, task creation, gate persistence, mobile overflow, responsive navigation, zero page errors')
