"""Real local HTTP/UI flow with an in-memory test vault and simulated runner; no provider calls."""
import functools
import http.server
import importlib.util
import json
import pathlib
import threading
import tempfile
import time
from unittest.mock import patch
from playwright.sync_api import sync_playwright

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('local_bridge',ROOT/'scripts/credential_companion.py')
bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
import model_discovery
catalog_id="returned-model-v1"
def provider_response(url,headers):
    key=headers.get('Authorization',headers.get('x-api-key',''))
    if 'rejected-key' in key:raise RuntimeError('The provider rejected this key.')
    if 'empty-key' in key:return {'data':[]}
    return {'data':[{'id':catalog_id,'display_name':'Provider model'}]}
class TestVault:
    values={}
    def get_password(self, service, name): return self.values.get(name)
    def set_password(self, service, name, value): self.values[name]=value
class TestRunner(bridge.Runner):
    def command(self, *args, **kwargs): return 0
    def container(self, work, checks, args, timeout, key=None, value=None):
        time.sleep(.05)
        if key: (work/'solution.py').write_text("print('hello')")
        return 0

temporary=tempfile.TemporaryDirectory()
runner=TestRunner(pathlib.Path(temporary.name)/'runs')
checks=pathlib.Path(temporary.name)/'checks';checks.mkdir();(checks/'check.py').write_text('assert True')
pack=pathlib.Path(temporary.name)/'pack.json'
pack.write_text(json.dumps({'schemaVersion':1,'name':'UI test benchmark','revision':'test-v1','tasks':[{'name':'External case','acceptance':'Return hello','checksPath':str(checks),'checkCommand':'python3 /checks/check.py'}]}))

server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(bridge.Handler,token='test-only-token',runner=runner))
threading.Thread(target=server.serve_forever,daemon=True).start()
try:
 with patch.object(bridge,'vault',return_value=TestVault()),patch.object(bridge,'docker_ready',return_value=True),patch.object(model_discovery,'request_json',side_effect=provider_response),sync_playwright() as p:
  browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
  page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(f'http://127.0.0.1:{server.server_port}/')
  def nav(section,label=None):
   page.get_by_role('navigation',name='Main navigation').get_by_role('button',name=section,exact=True).click()
   if label:page.get_by_role('navigation',name=section+' sections').get_by_role('button',name=label,exact=True).click()
  nav('Set up','Services & criteria')
  for name in ['Cursor','Devin','OpenCode']:page.get_by_role('button',name=f'Remove {name} from evaluation',exact=True).click()
  assert page.get_by_role('navigation',name='Set up sections').get_by_role('button',name='Credentials',exact=True).count()==0
  assert page.get_by_role('combobox',name='Codex model',exact=True).is_disabled()
  assert page.get_by_role('combobox',name='Claude Code model',exact=True).is_disabled()
  nav('Settings')
  page.locator('[data-local-key="OPENAI_API_KEY"]').fill('test-only-key-never-real')
  page.locator('[data-save-local="OPENAI_API_KEY"]').click()
  page.wait_for_function('document.querySelector(\'[data-key-status="OPENAI_API_KEY"]\').textContent==="Configured"')
  assert page.locator('[data-local-key="OPENAI_API_KEY"]').input_value()==''
  assert 'test-only-key-never-real' not in page.evaluate('JSON.stringify(localStorage)')
  nav('Set up','Services & criteria')
  page.wait_for_function('document.querySelector(\'[data-key-status="OPENAI_API_KEY"]\').textContent==="Configured"')
  # Saved keys unlock a real discovery request; rejected/empty catalogs cannot be selected.
  for key,message in [('rejected-key-test','Models unavailable'),('empty-key-test','No models returned')]:
   page.get_by_label('Codex API key',exact=True).fill(key)
   page.locator('[data-save-local="OPENAI_API_KEY"]').click()
   page.get_by_role('combobox',name='Codex model',exact=True).get_by_text(message,exact=True).wait_for()
   assert page.get_by_role('combobox',name='Codex model',exact=True).is_disabled()
  page.get_by_label('Codex API key',exact=True).fill('test-only-key-never-real')
  page.locator('[data-save-local="OPENAI_API_KEY"]').click()
  page.get_by_role('combobox',name='Codex model',exact=True).click()
  page.get_by_role('option',name='Provider model · returned-model-v1',exact=True).click()
  catalog_id='returned-model-v2'
  page.get_by_role('button',name='Refresh Codex models',exact=True).click()
  page.get_by_text('Previous selection is unavailable. Choose a returned model.',exact=True).wait_for()
  page.get_by_role('combobox',name='Codex model',exact=True).click()
  assert page.get_by_role('option',name='Provider model · returned-model-v1',exact=True).count()==0
  page.get_by_role('option',name='Provider model · returned-model-v2',exact=True).click()
  catalog_id='returned-model-v1'
  page.get_by_role('button',name='Refresh Codex models',exact=True).click()
  page.get_by_role('combobox',name='Codex model',exact=True).click()
  page.get_by_role('option',name='Provider model · returned-model-v1',exact=True).click()
  nav('Run evaluation')
  page.get_by_role('tab',name='Benchmarks',exact=True).click()
  assert page.locator('.stage-navigation,.connection-strip').count()==0
  page.get_by_role('tab',name='Run evaluation',exact=True).click()
  page.locator('#evaluation-consent').check();assert page.locator('#start-evaluation').is_disabled()
  nav('Set up','Services & criteria')
  page.locator('[data-local-key="ANTHROPIC_API_KEY"]').fill('test-only-second-key')
  page.locator('[data-save-local="ANTHROPIC_API_KEY"]').click()
  page.wait_for_function('document.querySelector(\'[data-key-status="ANTHROPIC_API_KEY"]\').textContent==="Configured"')
  page.get_by_role('combobox',name='Claude Code model',exact=True).click()
  page.get_by_role('option',name='Provider model · returned-model-v1',exact=True).click()
  page.get_by_role('button',name='Refresh Claude Code models',exact=True).click()
  page.get_by_role('combobox',name='Claude Code model',exact=True).click()
  out=ROOT/'test-results/local';out.mkdir(parents=True,exist_ok=True)
  page.screenshot(path=str(out/'discovered-models-desktop.png'))
  page.keyboard.press('Escape')
  page.set_viewport_size({'width':390,'height':844})
  page.get_by_role('combobox',name='Claude Code model',exact=True).click()
  page.wait_for_timeout(100)
  menu=page.get_by_role('listbox').bounding_box()
  assert menu and menu['x']>=0 and menu['x']+menu['width']<=390
  assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
  page.screenshot(path=str(out/'discovered-models-mobile.png'))
  page.keyboard.press('Escape');page.set_viewport_size({'width':1440,'height':1000})
  nav('Set up','Tasks')
  page.get_by_role('button',name='Add task',exact=True).click()
  page.locator('.modal [name="name"]').fill('Team greeting')
  page.locator('.modal [name="acceptance"]').fill('Return hello')
  page.locator('.modal').get_by_role('button',name='Save',exact=True).click()
  nav('Run evaluation')
  page.get_by_role('tab',name='Benchmarks',exact=True).click()
  assert page.locator('.stage-navigation,.connection-strip').count()==0
  # Details stay out of the form, but remain accessible by pointer, keyboard, and tap.
  assert page.get_by_role('tab',name='Benchmarks',exact=True).get_attribute('aria-selected')=='true'
  panel=page.locator('.benchmark-panel')
  assert 'leaderboard' not in panel.inner_text()
  page.evaluate('window.scrollTo(0,0)')
  page.wait_for_timeout(250)
  page.screenshot(path=str(out/'benchmarks-desktop.png'),full_page=True)
  help_button=page.get_by_role('button',name='About HumanEval',exact=True)
  help_button.hover()
  tooltip=page.get_by_role('tooltip');tooltip.wait_for()
  assert tooltip.locator('strong').inner_text()=='HumanEval'
  assert tooltip.locator('li').count()==2
  tooltip.hover();page.wait_for_timeout(200);assert tooltip.is_visible()
  page.screenshot(path=str(out/'benchmark-help-desktop.png'))
  page.keyboard.press('Escape');assert page.get_by_role('tooltip').count()==0
  help_button.focus();assert page.get_by_role('tooltip').is_visible()
  page.keyboard.press('Escape');assert page.get_by_role('tooltip').count()==0
  page.set_viewport_size({'width':390,'height':844})
  page.wait_for_timeout(350)
  page.evaluate("window.scrollTo(0,document.querySelector('.benchmark-panel').getBoundingClientRect().top+scrollY-24)")
  page.screenshot(path=str(out/'benchmarks-mobile.png'))
  page.get_by_role('button',name='About local benchmark packs',exact=True).click()
  tooltip=page.get_by_role('tooltip');tooltip.wait_for()
  box=tooltip.bounding_box()
  assert box['x']>=0 and box['x']+box['width']<=390
  assert box['y']>=0 and box['y']+box['height']<=844
  page.screenshot(path=str(out/'benchmark-help-mobile.png'))
  page.get_by_role('button',name='Choose pack',exact=True).click()
  page.locator('#benchmark-pack-path').click()
  assert page.get_by_role('tooltip').count()==0
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
  page.set_viewport_size({'width':1440,'height':1000})
  page.locator('[data-benchmark-details="swebench-lite"]').click()
  assert page.locator('#details-swebench-lite').is_visible()
  assert page.locator('#details-swebench-lite').get_by_role('link',name='Setup guide',exact=False).get_attribute('href').startswith('https://github.com/')
  page.locator('[data-benchmark-details="swebench-lite"]').click()
  page.get_by_role('tab',name='Benchmarks',exact=True).focus()
  page.keyboard.press('ArrowRight')
  assert page.locator('#evaluation-tabpanel-benchmarks').is_hidden()
  page.keyboard.press('ArrowLeft')
  assert page.locator('#evaluation-tabpanel-benchmarks').is_visible()
  # A prepared dataset response; no network download or provider usage.
  page.route('**/api/local/prepare-humaneval',lambda route:route.fulfill(json={'path':str(pathlib.Path(temporary.name)/'human-eval-test/pack.json'),'benchmark':{'name':'HumanEval (Basis adapter)','tasks':[{}]*5}}))
  page.locator('#add-humaneval').click()
  page.get_by_role('button',name='Remove HumanEval',exact=True).wait_for()
  assert page.locator('#humaneval-count').is_disabled()
  assert page.locator('#humaneval-count').input_value()=='5'
  page.get_by_role('button',name='Remove HumanEval',exact=True).click()
  assert page.locator('#add-humaneval').is_visible()
  page.locator('#benchmark-pack-path').fill(str(pack))
  page.locator('#add-benchmark-pack').click()
  page.locator('[data-remove-pack]').wait_for()
  assert page.locator('.selected-packs li').count()==1
  page.locator('#clear-benchmarks').click()
  assert page.locator('[data-remove-pack]').count()==0
  page.locator('#benchmark-pack-path').fill(str(pack))
  page.locator('#add-benchmark-pack').click()
  page.locator('[data-remove-pack]').wait_for()
  page.get_by_role('button',name='Continue to run',exact=True).click()
  assert page.locator('#evaluation-tabpanel-benchmarks').is_hidden()
  page.locator('#evaluation-consent').check()
  page.wait_for_function('!document.querySelector("#start-evaluation").disabled')
  page.locator('#start-evaluation').click()
  page.wait_for_function('document.querySelector("#evaluation-progress").textContent.includes("4 of 4")')
  nav('Results');page.locator('.attempt-row').first.wait_for()
  assert page.locator('.attempt-row').count()==4
  assert 'unverified' in page.locator('body').inner_text()
  page.locator('[data-include-suite]').uncheck()
  assert page.locator('.attempt-row').count()==2
  page.locator('[data-include-suite]').check()
  assert page.locator('.attempt-row').count()==4
  page.locator('[data-review-attempt]').first.click()
  page.locator('.modal [name="notes"]').fill('Checked generated source and acceptance')
  page.locator('.modal').get_by_role('button',name='Save',exact=True).click()
  page.get_by_text('Human rejected',exact=False).first.wait_for()
  assert runner.snapshot()['plan']['setup']['tasks'][0]['name']=='Team greeting'
  out=ROOT/'test-results/local';out.mkdir(parents=True,exist_ok=True)
  page.screenshot(path=str(out/'results-desktop.png'),full_page=True)
  page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(200)
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
  page.screenshot(path=str(out/'results-mobile.png'),full_page=True)
  page.set_viewport_size({'width':1440,'height':1000})
  nav('Settings');page.reload();nav('Settings')
  page.wait_for_function('document.querySelector(\'[data-key-status="OPENAI_API_KEY"]\').textContent==="Configured"')
  out=ROOT/'test-results/local';out.mkdir(parents=True,exist_ok=True)
  page.screenshot(path=str(out/'settings-desktop.png'),full_page=True)
  nav('Run evaluation');page.get_by_role('tab',name='Run evaluation',exact=True).click();page.locator('#evaluation-progress').wait_for()
  assert page.locator('.run-phases .current').inner_text().endswith('Finish')
  console=page.locator('[data-console]').filter(has_text='Claude Code').first
  console.locator('summary').click()
  page.wait_for_timeout(2800)
  assert console.get_attribute('open') is not None
  assert 'Starting task' in console.locator('pre').inner_text()
  console.locator('[data-follow]').uncheck()
  with page.expect_download() as downloaded:
   console.locator('[data-download-log]').click()
  assert downloaded.value.suggested_filename=='basis-activity.txt'
  page.screenshot(path=str(out/'run-desktop.png'),full_page=True)
  finished=runner.snapshot()
  for status,phase,message in [('preparing','prepare','Downloading agent tools'),('running','agent','Running Claude Code'),('running','check','Checking Claude Code'),('failed','check','Runner failed')]:
   runner.update(status=status,phase=phase,message=message,finishedAt=None if status in ('preparing','running') else time.time(),currentAgent='claude',currentTask=0,results=[])
   page.locator('h1').click()
   page.wait_for_timeout(2800)
   assert page.locator('#evaluation-progress .run-heading').inner_text().find(message)>=0 or status=='failed'
   if status in ('preparing','running'):
    assert page.locator('#evaluation-progress .status-led.is-active').count()>0
   page.screenshot(path=str(out/f'progress-{phase}-{status}.png'),full_page=True)
  runner.update(**finished)
  page.wait_for_timeout(2800)

  page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(400)
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
  page.screenshot(path=str(out/'run-mobile.png'),full_page=True)
  touch=browser.new_page(viewport={'width':390,'height':844},has_touch=True,is_mobile=True)
  touch.on('pageerror',lambda e:errors.append(str(e)))
  touch.goto(f'http://127.0.0.1:{server.server_port}/')
  touch.get_by_role('button',name='Toggle menu',exact=True).tap()
  touch.get_by_role('navigation',name='Main navigation').get_by_role('button',name='Run evaluation',exact=True).tap()
  touch.get_by_role('tab',name='Benchmarks',exact=True).tap()
  touch.get_by_role('button',name='About HumanEval',exact=True).tap()
  assert touch.get_by_role('tooltip').is_visible()
  touch.locator('#humaneval-count').tap()
  assert touch.get_by_role('tooltip').count()==0
  assert not errors,errors
  browser.close()
finally:
 server.shutdown();server.server_close();temporary.cleanup()
print('PASS local UI: shared saved-key detection, missing-key gate, consent, automatic results, reload, mobile; no paid calls')
