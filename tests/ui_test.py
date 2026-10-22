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
  page.set_content('<!doctype html><html><head><style>'+style+'</style></head><body><div id="app"></div><script>window.__testStorage={};Object.defineProperty(window,"localStorage",{value:{getItem:k=>window.__testStorage[k]??null,setItem:(k,v)=>window.__testStorage[k]=v,removeItem:k=>delete window.__testStorage[k]},configurable:true});</script><script>'+core+'\n'+tech+'\n'+app+'</script></body></html>',wait_until='load')
 errors=[]
 page.on('pageerror',lambda err:errors.append(str(err)))
 load()
 assert page.get_by_role("heading",name="Compare coding tools, step by step.",exact=False).count()==1
 assert 'RECORDED DATA (UNVERIFIED)' in page.locator('body').inner_text()
 assert '30 pilot records' not in page.locator('body').inner_text()
 page.screenshot(path=str(SCREENSHOTS/'desktop.png'),full_page=True)
 def navigate(section, label=None):
  page.get_by_role('navigation',name='Main navigation').get_by_role('button',name=section,exact=True).click()
  if label:
   page.get_by_role('navigation',name=section+' sections').get_by_role('button',name=label,exact=True).click()
 assert page.get_by_role('navigation',name='Main navigation').get_by_role('button').count()==6
 for section,label,expected in [('Set up',None,'Team context'),('Set up','Requirements','Requirements'),('Set up','Tasks & observations','Tasks & observations'),('Results','Pilot comparison','Pilot comparison'),('Tool catalog',None,'Tool catalog'),('Results','Review quality','Review quality'),('Results','Decision summary','Decision summary')]:
  navigate(section,label)
  assert page.get_by_role('heading',name=expected,exact=True).count()==1,expected
 assert 'No defensible winner yet' in page.locator('body').inner_text()
 navigate('Results','Pilot comparison')
 before=page.locator('input[data-range="org.rate"]').input_value()
 page.locator('input[data-range="org.rate"]').fill('250')
 after=page.locator('input[data-range="org.rate"]').input_value()
 assert before!=after,('cost input did not update',before,after)
 navigate('Set up','Tasks & observations')
 page.get_by_role('button',name='Task',exact=True).click()
 page.locator('.modal input[name="name"]').fill('Browser UI test task')
 page.locator('.modal input[name="acceptance"]').fill('Verified by independent tests')
 page.locator('.modal .primary').click()
 page.get_by_role('button',name='Task library').click()
 assert 'Browser UI test task' in page.locator('body').inner_text()
 navigate('Set up','Requirements')
 page.locator('select[data-gate="claude:retention"]').locator('..').get_by_role('combobox').click()
 page.get_by_role('option',name='Fail',exact=True).click()
 assert page.locator('select[data-gate="claude:retention"]').input_value()=='fail'
 page.evaluate('render()')
 assert page.locator('select[data-gate="claude:retention"]').input_value()=='fail'
 navigate('Set up')
 risk=page.get_by_role('combobox',name='Risk profile',exact=True)
 risk.focus()
 risk.press('ArrowDown')
 risk.press('Home')
 risk.press('ArrowDown')
 risk.press('Enter')
 assert page.locator('select[data-path="org.risk"]').input_value()=='medium'
 assert page.get_by_role('combobox',name='Risk profile',exact=True).inner_text()=='Standard governance'
 risk=page.get_by_role('combobox',name='Risk profile',exact=True)
 risk.click()
 risk.press('Escape')
 assert page.get_by_role('listbox').count()==0
 assert risk.get_attribute('aria-expanded')=='false'
 navigate('Run tests')
 page.evaluate('window.open = (url) => { window.openedURL = url; }')
 page.get_by_role('button',name='Open test workflow ↗',exact=True).click()
 assert 'Enter your GitHub repository' in page.locator('#run-guidance').inner_text()
 page.locator('#evaluation-repo').fill('example/basis')
 page.get_by_role('button',name='Open test workflow ↗',exact=True).click()
 assert page.evaluate('window.openedURL')=='https://github.com/example/basis/actions/workflows/agent-benchmark.yml'
 navigate('Run tests','External benchmarks')
 assert page.locator('#swe-repo').input_value()=='example/basis'
 page.get_by_role('button',name='Open GitHub Actions ↗',exact=True).click()
 assert page.evaluate('window.openedURL')=='https://github.com/example/basis/actions/workflows/swebench-lite.yml'
 with page.expect_download() as download:
  page.get_by_role('button',name='Download run configuration',exact=True).click()
 assert download.value.suggested_filename=='basis-swebench-lite-run.json'
 page.set_viewport_size({'width':390,'height':844})
 page.evaluate('render()')
 page.screenshot(path=str(SCREENSHOTS/'mobile.png'),full_page=True)
 assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')
 page.locator('[data-act="menu"]').first.click()
 page.get_by_role('navigation',name='Main navigation').get_by_role('button',name='Set up',exact=True).click()
 assert page.get_by_role('heading',name='Team context',exact=True).count()==1
 page.get_by_role('combobox',name='Risk profile',exact=True).click()
 assert page.get_by_role('listbox').is_visible()
 page.get_by_role('option',name='Experimental',exact=True).click()
 assert page.locator('select[data-path="org.risk"]').input_value()=='low'
 # Reset clears every evaluation store, but not unrelated origin data.
 page.evaluate("localStorage.setItem('unrelated-setting','keep');localStorage.setItem('basis-latest-agent-result',JSON.stringify({candidate:'codex'}));localStorage.setItem('basis-community-benchmark-imports','[]')")
 page.once('dialog',lambda dialog:dialog.dismiss())
 page.locator('[data-act="menu"]').first.click()
 page.get_by_role('button',name='Reset local evaluation',exact=True).click()
 assert page.evaluate("localStorage.getItem('basis-latest-agent-result')") is not None
 page.once('dialog',lambda dialog:dialog.accept())
 page.get_by_role('button',name='Reset local evaluation',exact=True).click()
 assert page.get_by_role('heading',name='Compare coding tools, step by step.',exact=True).count()==1
 assert page.evaluate("s.tasks.length===0 && s.runs.length===0")
 assert page.evaluate("EVALUATION_KEYS.filter(key=>key!==KEY).every(key=>localStorage.getItem(key)===null)")
 assert page.evaluate("localStorage.getItem('unrelated-setting')")=='keep'
 assert not errors,errors
 browser.close()
print('PLAYWRIGHT UI TESTS PASSED: grouped navigation, workflow handoff, config download, scenario cost, task creation, gate persistence, mobile navigation, zero page errors')
