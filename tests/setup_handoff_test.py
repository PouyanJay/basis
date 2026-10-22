"""Two-origin browser test; uses an in-memory local API, never the real credential store."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
HOSTED='https://pouyanjay.github.io'
LOCAL='http://127.0.0.1:8765'
keys={};requests=[]
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 context=browser.new_context(viewport={'width':1440,'height':1000})
 def serve(route):
  request=route.request;requests.append(request.url)
  from urllib.parse import urlsplit
  path=urlsplit(request.url).path
  if '/api/' in path:
   assert request.url.startswith(LOCAL)
   data=request.post_data_json if request.method=='POST' else {}
   if path=='/api/health':result={'service':'basis-local-companion','token':'test-only'}
   elif path=='/api/local/status':result={'configured':{name:True for name in keys},'credentialError':'','dockerReady':True,'job':None}
   elif path=='/api/local/models':result={'models':[{'id':'test-returned-model','name':'Returned model'}],'source':'test-only'}
   elif path=='/api/local/credentials':keys[data['secret']]=data['value'];result={'saved':True}
   else:result={'evaluations':[],'job':None}
   route.fulfill(json=result);return
  name=path.removeprefix('/basis/').lstrip('/') or 'index.html'
  file=ROOT/name
  if file.is_file() and name in ['index.html','app.js','core.js','technology.js','benchmarks.js','styles.css','brand.svg']:
   route.fulfill(path=str(file),content_type='text/javascript' if name.endswith('.js') else 'text/css' if name.endswith('.css') else 'image/svg+xml' if name.endswith('.svg') else 'text/html')
  else:route.fulfill(status=404,body='')
 context.route(HOSTED+'/**',serve);context.route(LOCAL+'/**',serve)
 page=context.new_page();errors=[];context.on('page',lambda page:page.on('pageerror',lambda error:errors.append(str(error))))
 page.on('pageerror',lambda error:errors.append(str(error)))
 page.goto(HOSTED+'/basis/')
 def nav(page,label):
  page.get_by_role('navigation',name='Main navigation').get_by_role('button',name='Set up',exact=True).click()
  page.get_by_role('navigation',name='Set up sections').get_by_role('button',name=label,exact=True).click()
 nav(page,'Services & criteria')
 for name in ['Cursor','Devin','OpenCode']:page.get_by_role('button',name=f'Remove {name} from evaluation',exact=True).click()
 assert page.get_by_role('combobox',name='Codex model',exact=True).is_disabled()
 page.get_by_label('Codex API key',exact=True).fill('test-only-handoff-openai')
 assert page.locator('[data-config-service="codex"] [data-save-local]').count()==0
 assert 'test-only-handoff-openai' not in page.evaluate('JSON.stringify(localStorage)')
 nav(page,'Tasks')
 page.get_by_role('button',name='Add task',exact=True).click()
 page.locator('.modal [name="name"]').fill('Transferred task')
 page.locator('.modal [name="acceptance"]').fill('Meets acceptance criteria')
 page.locator('.modal').get_by_role('button',name='Save',exact=True).click()
 nav(page,'Services & criteria')
 assert page.locator('[data-config-service="codex"] [data-key-status]').text_content()=='Ready to transfer'
 # An unsaved visible entry also goes with the explicit handoff.
 page.get_by_label('Claude Code API key',exact=True).fill('test-only-handoff-anthropic')
 with context.expect_page() as new_page:page.get_by_role('button',name='Continue locally',exact=True).click()
 local=new_page.value
 local.get_by_role('heading',name='Services & criteria',exact=True).wait_for()
 local.wait_for_function('document.querySelectorAll("[data-key-status].pass").length === 2')
 local.get_by_role('combobox',name='Codex model',exact=True).click()
 local.get_by_role('option',name='Returned model · test-returned-model',exact=True).click()
 assert local.locator('[data-service-model="codex"]').input_value()=='test-returned-model'
 assert keys=={'OPENAI_API_KEY':'test-only-handoff-openai','ANTHROPIC_API_KEY':'test-only-handoff-anthropic'}
 assert 'test-only-handoff' not in local.evaluate('JSON.stringify(localStorage)')
 assert 'test-only-handoff' not in page.evaluate('JSON.stringify(localStorage)')
 assert all('test-only-handoff' not in url for url in requests)
 page.get_by_text('Setup transferred. Continue in the local app.',exact=True).wait_for()
 nav(local,'Tasks');assert local.get_by_text('Transferred task',exact=True).is_visible()
 # A second transfer must ask before replacing populated local setup.
 with context.expect_page() as another:page.get_by_role('button',name='Continue locally',exact=True).click()
 replacement=another.value
 replacement.get_by_role('dialog').get_by_role('button',name='Cancel',exact=True).click()
 page.get_by_text('Transfer was not completed. Your setup is still here.',exact=True).wait_for()
 assert not errors,errors
 browser.close()
print('PASS hosted → local handoff: selected services/models/tasks, transient keys, no secrets in storage/URLs, existing setup confirmation, cancellation')
