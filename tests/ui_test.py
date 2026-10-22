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
 for section,label,expected in [('Set up',None,'Team context'),('Set up','Services & criteria','Services & criteria'),('Set up','Tasks','Tasks'),('Tool catalog',None,'Tool catalog')]:
  navigate(section,label)
  assert page.get_by_role('heading',name=expected,exact=True).count()==1,expected
 navigate('Set up','Tasks')
 page.get_by_role('button',name='Add task',exact=True).click()
 page.locator('.modal input[name="name"]').fill('Browser UI test task')
 page.locator('.modal input[name="acceptance"]').fill('Verified by independent tests')
 page.locator('.modal .primary').click()
 assert 'Browser UI test task' in page.locator('body').inner_text()
 page.get_by_role('button',name='Edit task',exact=True).click()
 assert page.locator('.modal input[name="name"]').input_value()=='Browser UI test task'
 page.locator('.modal input[name="sourcePath"]').fill('/tmp/example-source')
 page.locator('.modal .primary').click()
 assert '/tmp/example-source' in page.locator('body').inner_text()
 assert page.locator('[data-act="add-run"]').count()==0
 page.get_by_role('button',name='Fair testing guide',exact=True).click()
 assert page.get_by_role('dialog').get_by_role('heading',name='Fair testing guide').is_visible()
 page.get_by_role('dialog').get_by_role('button',name='Got it').click()
 navigate('Run evaluation')
 assert page.locator('#start-evaluation').is_disabled()
 navigate('Set up','Tasks')
 assert page.locator('.tabs').count()==0
 assert 'Browser UI test task' in page.locator('body').inner_text()

 navigate('Set up','Services & criteria')
 # Model choices use the shared dropdown, preserve older studies, and select the correct key.
 assert page.locator('input[data-service-model]').count()==0
 page.get_by_role('combobox',name='OpenCode model',exact=True).click()
 page.get_by_role('option',name='Anthropic · Sonnet 5.5',exact=True).click()
 assert page.locator('[data-service-key="opencode"] input').get_attribute('data-local-key')=='ANTHROPIC_API_KEY'
 page.get_by_role('combobox',name='OpenCode model',exact=True).click()
 page.get_by_role('option',name='OpenAI · GPT-6.1 Sol',exact=True).click()
 assert page.locator('[data-service-key="opencode"] input').get_attribute('data-local-key')=='OPENAI_API_KEY'
 page.get_by_label('Codex API key',exact=True).fill('test-only-unsaved')
 page.get_by_role('combobox',name='Codex model',exact=True).focus()
 page.keyboard.press('ArrowDown');page.keyboard.press('ArrowDown');page.keyboard.press('Enter')
 assert page.locator('[data-service-model="codex"]').input_value()=='gpt-6.1-sol'
 assert page.get_by_label('Codex API key',exact=True).input_value()=='test-only-unsaved'
 page.evaluate("s.platforms.find(p=>p.id==='codex').model='previous-custom-model';save();render()")
 assert page.get_by_role('combobox',name='Codex model',exact=True).inner_text()=='previous-custom-model (saved selection)'
 page.get_by_role('combobox',name='Codex model',exact=True).click()
 page.get_by_role('option',name='Use service default',exact=True).click()
 page.get_by_role('combobox',name='Claude Code model',exact=True).click()
 page.screenshot(path=str(SCREENSHOTS/'model-selector-desktop.png'))
 page.keyboard.press('Escape')
 page.set_viewport_size({'width':390,'height':844})
 page.get_by_role('combobox',name='OpenCode model',exact=True).click()
 assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
 page.wait_for_timeout(150)
 menu=page.get_by_role('listbox').bounding_box()
 assert menu and menu['x']>=0 and menu['x']+menu['width']<=390
 page.screenshot(path=str(SCREENSHOTS/'model-selector-mobile.png'))
 page.keyboard.press('Escape')
 page.set_viewport_size({'width':1440,'height':900})
 page.locator('select[data-gate="claude:retention"]').locator('..').get_by_role('combobox').click()
 page.get_by_role('option',name='Fail',exact=True).click()
 assert page.locator('select[data-gate="claude:retention"]').input_value()=='fail'
 page.get_by_role('button',name='Remove Claude Code from evaluation',exact=True).click()
 assert page.locator('select[data-gate="claude:retention"]').count()==0
 page.get_by_role('button',name='Include Claude Code in evaluation',exact=True).click()
 assert page.locator('select[data-gate="claude:retention"]').input_value()=='fail'
 page.get_by_role('button',name='Add custom service',exact=True).click()
 page.locator('.modal [name="name"]').fill('Team custom tool')
 page.locator('.modal [name="provider"]').fill('Internal')
 page.locator('.modal [name="mode"]').fill('CLI')
 page.locator('.modal').get_by_role('button',name='Save',exact=True).click()
 assert page.get_by_role('combobox',name='Team custom tool: Data retention and training restrictions',exact=True).inner_text()=='Unverified'
 page.get_by_role('button',name='Remove Team custom tool from evaluation',exact=True).click()
 page.evaluate('render()')
 assert page.locator('select[data-gate="claude:retention"]').input_value()=='fail'
 navigate('Set up')
 page.get_by_role('button',name='Increase Engineers',exact=True).click()
 assert page.locator('[data-path="org.developers"]').input_value()=='1'
 page.get_by_role('button',name='Decrease Engineers',exact=True).click()
 assert page.locator('[data-path="org.developers"]').input_value()=='1'
 risk=page.get_by_role('combobox',name='Risk profile',exact=True)
 risk.focus()
 risk.press('ArrowDown')
 risk.press('Home')
 risk.press('ArrowDown')
 risk.press('ArrowDown')
 risk.press('Enter')
 assert page.locator('select[data-path="org.risk"]').input_value()=='medium'
 assert page.get_by_role('combobox',name='Risk profile',exact=True).inner_text()=='Standard governance'
 risk=page.get_by_role('combobox',name='Risk profile',exact=True)
 risk.click()
 risk.press('Escape')
 assert page.get_by_role('listbox').count()==0
 assert risk.get_attribute('aria-expanded')=='false'
 navigate('Run evaluation')
 assert page.locator('#start-evaluation').is_disabled()
 assert page.locator('[data-act="open-fixture-actions"]').count()==0
 navigate('Set up','Services & criteria')
 assert page.get_by_role('heading',name='Services & criteria',exact=True).is_visible()
 assert page.locator('[data-local-key]').count()>=1
 navigate('Results')
 page.get_by_role('button',name='Imported benchmark reports',exact=True).click()
 assert page.get_by_role('heading',name='External benchmarks',exact=True).is_visible()
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
 page.locator('[data-act="menu"]').first.click()
 page.get_by_role('button',name='Reset local evaluation',exact=True).click()
 page.get_by_role('dialog').get_by_role('button',name='Cancel',exact=True).click()
 assert page.evaluate("localStorage.getItem('basis-latest-agent-result')") is not None
 page.get_by_role('button',name='Reset local evaluation',exact=True).click()
 page.get_by_role('dialog').get_by_role('button',name='Reset evaluation',exact=True).click()
 page.get_by_role('heading',name='Compare coding tools, step by step.',exact=True).wait_for()
 assert page.get_by_role('heading',name='Compare coding tools, step by step.',exact=True).count()==1
 assert page.evaluate("s.tasks.length===0 && s.runs.length===0")
 assert page.evaluate("EVALUATION_KEYS.filter(key=>key!==KEY).every(key=>localStorage.getItem(key)===null)")
 assert page.evaluate("localStorage.getItem('unrelated-setting')")=='keep'
 assert not errors,errors
 browser.close()
print('PLAYWRIGHT UI TESTS PASSED: grouped navigation, local-run prerequisites, credential navigation, scenario cost, task creation, gate persistence, mobile navigation, zero page errors')
