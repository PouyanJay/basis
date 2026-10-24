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
    return {'data':[{'id':catalog_id,'display_name':'Provider model'},{'id':'second-model','display_name':'Second model'},{'id':'third-model','display_name':'Third model'}]}
class TestVault:
    values={}
    def get_password(self, service, name): return self.values.get(name)
    def set_password(self, service, name, value): self.values[name]=value
class TestRunner(bridge.Runner):
    def command(self, *args, **kwargs): return 0
    def grade_lite(self, task, work, timeout):
        return {'checkPassed':True, 'checkExitCode':0}
    def container(self, work, checks, args, timeout, key=None, value=None):
        time.sleep(.05)
        if key:
            (work/'solution.py').write_text("print('hello')")
            if args[1]=='claude':
                self.output(json.dumps({'type':'result','subtype':'success','total_cost_usd':.001234,'modelUsage':{args[2]:{'inputTokens':100,'outputTokens':20,'cacheReadInputTokens':40,'cacheCreationInputTokens':10}}}))
        return 0

temporary=tempfile.TemporaryDirectory()
runner=TestRunner(pathlib.Path(temporary.name)/'runs')
checks=pathlib.Path(temporary.name)/'checks';checks.mkdir();(checks/'check.py').write_text('assert True')
pack=pathlib.Path(temporary.name)/'pack.json'
pack.write_text(json.dumps({'schemaVersion':1,'name':'UI test benchmark','revision':'test-v1','tasks':[{'name':'External case','acceptance':'Return hello','checksPath':str(checks),'checkCommand':'python3 /checks/check.py'}]}))

source=pathlib.Path(temporary.name)/'lite-source';source.mkdir();(source/'README.md').write_text('Fixture source')
instance=pathlib.Path(temporary.name)/'instance.json';instance.write_text('{}')
runner.lite.selection=lambda count:{'id':'swebench-lite','name':'SWE-bench Lite','revision':'a'*40,'harness':'3.0.15','tasks':[{'id':'test__repo-1','name':'Repository issue','acceptance':'Fix greeting','sourcePath':str(source),'grader':'swebench-lite','instancePath':str(instance),'imageTag':'fixture','imageDigest':'fixture'}]}

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
  nav('Set up','Services')
  for name in ['Cursor','Devin','OpenCode']:page.get_by_role('button',name=f'Remove {name} from evaluation',exact=True).click()
  assert page.get_by_role('navigation',name='Set up sections').get_by_role('button',name='Credentials',exact=True).count()==0
  assert page.get_by_role('combobox',name='Codex model',exact=True).is_disabled()
  assert page.get_by_role('combobox',name='Claude Code model',exact=True).is_disabled()
  nav('Set up','Services')
  page.locator('[data-local-key="OPENAI_API_KEY"]').fill('test-only-key-never-real')
  page.locator('[data-save-local="OPENAI_API_KEY"]').click()
  page.wait_for_function('document.querySelector(\'[data-key-status="OPENAI_API_KEY"]\').textContent==="Configured"')
  assert page.locator('[data-local-key="OPENAI_API_KEY"]').input_value()==''
  assert 'test-only-key-never-real' not in page.evaluate('JSON.stringify(localStorage)')
  nav('Set up','Services')
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
  page.get_by_role('button',name='Remove returned-model-v1 from Codex',exact=True).click()
  catalog_id='returned-model-v1'
  page.get_by_role('button',name='Remove returned-model-v2 from Codex',exact=True).click()
  page.get_by_role('button',name='Refresh Codex models',exact=True).click()
  page.get_by_role('combobox',name='Codex model',exact=True).click()
  page.get_by_role('option',name='Provider model · returned-model-v1',exact=True).click()
  nav('Run evaluation')
  assert page.locator('.stage-navigation,.connection-strip').count()==0
  if page.locator('#platform-review-scope').count():
   page.locator('.evaluation-scope summary').click()
   page.locator('#platform-review-scope').uncheck()
  page.locator('#evaluation-consent').check();assert page.locator('#start-evaluation').is_disabled()
  nav('Set up','Services')
  page.locator('[data-local-key="ANTHROPIC_API_KEY"]').fill('test-only-second-key')
  page.locator('[data-save-local="ANTHROPIC_API_KEY"]').click()
  page.wait_for_function('document.querySelector(\'[data-key-status="ANTHROPIC_API_KEY"]\').textContent==="Configured"')
  page.get_by_role('combobox',name='Claude Code model',exact=True).click()
  page.get_by_role('option',name='Provider model · returned-model-v1',exact=True).click()
  page.get_by_role('combobox',name='Claude Code model',exact=True).click()
  page.get_by_role('option',name='Second model · second-model',exact=True).click()
  assert page.locator('[data-model-control=claude] .selected-model').count()==2
  page.get_by_role('button',name='Remove second-model from Claude Code',exact=True).click()
  assert page.locator('[data-model-control=claude] .selected-model').count()==1
  page.get_by_role('combobox',name='Claude Code model',exact=True).click()
  page.get_by_role('option',name='Second model · second-model',exact=True).click()
  page.get_by_role('combobox',name='Claude Code model',exact=True).click()
  page.get_by_role('option',name='Third model · third-model',exact=True).click()
  assert page.get_by_role('combobox',name='Claude Code model',exact=True).is_disabled()
  page.get_by_role('button',name='Remove third-model from Claude Code',exact=True).click()
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
  nav('Set up','Tasks & Benchmarks')
  page.get_by_role('button',name='Add task',exact=True).click()
  page.locator('.modal [name="name"]').fill('Team greeting')
  page.locator('.modal [name="acceptance"]').fill('Return hello')
  page.locator('.modal').get_by_role('button',name='Save',exact=True).click()
  assert page.get_by_role('heading',name='Tasks & Benchmarks',exact=True).is_visible()
  panel=page.locator('.benchmark-panel')
  assert 'leaderboard' not in panel.inner_text()
  page.evaluate('window.scrollTo(0,0)')
  page.wait_for_timeout(250)
  page.screenshot(path=str(out/'benchmarks-desktop.png'),full_page=True)
  help_button=page.get_by_role('button',name='About SWE-bench Lite',exact=True)
  help_button.hover()
  tooltip=page.get_by_role('tooltip');tooltip.wait_for()
  assert tooltip.locator('strong').inner_text()=='SWE-bench Lite'
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
  page.get_by_role('button',name='About SWE-bench Lite',exact=True).click()
  tooltip=page.get_by_role('tooltip');tooltip.wait_for()
  box=tooltip.bounding_box()
  assert box['x']>=0 and box['x']+box['width']<=390
  assert box['y']>=0 and box['y']+box['height']<=844
  page.screenshot(path=str(out/'benchmark-help-mobile.png'))
  page.locator('#swebench-count').click()
  assert page.get_by_role('tooltip').count()==0
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
  page.set_viewport_size({'width':1440,'height':1000})
  assert page.get_by_role('button',name='Unavailable',exact=True).count()==5
  assert page.locator('[data-nav="benchmarks"]').count()==0
  # Simulate asynchronous preparation, failure, retry, cancellation, and ready.
  prep={'status':'idle'}
  page.route('**/api/local/swebench-status',lambda route:route.fulfill(json={'benchmark':prep}))
  def prepare(route):
   prep.update(status='checking',count=1,message='Checking this computer',completed=0)
   route.fulfill(json={'benchmark':prep})
  page.route('**/api/local/prepare-swebench',prepare)
  page.locator('#swebench-count').fill('1')
  page.locator('#add-swebench').click()
  page.locator('#cancel-swebench').wait_for()
  assert page.locator('.benchmark-preparation .is-active').count()==1
  meter=page.get_by_role('progressbar',name='Benchmark preparation')
  assert meter.get_attribute('aria-valuenow') is None
  prep.update(status='preparing',count=10,completed=1,message='Preparing task 2 of 10')
  page.wait_for_function("document.querySelector('.benchmark-progress')?.getAttribute('aria-valuenow') === '1'")
  assert meter.get_attribute('aria-valuemax')=='10'
  assert page.locator('.benchmark-progress-fill').evaluate('(el)=>el.style.width')=='10%'
  assert page.locator('.benchmark-progress-activity').evaluate('(el)=>getComputedStyle(el).animationName')=='benchmark-sweep'
  page.screenshot(path=str(out/'benchmark-preparing.png'),full_page=True)
  def cancel(route):
   prep.update(status='cancelled',message='Preparation cancelled')
   route.fulfill(json={'benchmark':prep})
  page.route('**/api/local/cancel-swebench',cancel)
  page.locator('#cancel-swebench').click()
  page.locator('#add-swebench').wait_for()
  page.locator('#swebench-count').fill('1')
  page.locator('#add-swebench').click()
  page.locator('#cancel-swebench').wait_for()
  prep.update(status='error',message='Start Docker, then retry.')
  page.get_by_role('button',name='Retry',exact=True).wait_for()
  assert page.get_by_text('Start Docker, then retry.',exact=True).is_visible()
  page.get_by_role('button',name='Retry',exact=True).click()
  page.locator('#cancel-swebench').wait_for()
  prep.update(status='ready',count=1,message='Ready',completed=1)
  page.get_by_role('button',name='Remove SWE-bench Lite',exact=True).wait_for()
  assert page.locator('#swebench-count').is_disabled()
  page.reload()
  nav('Set up','Tasks & Benchmarks')
  page.get_by_role('button',name='Remove SWE-bench Lite',exact=True).wait_for()
  page.get_by_role('button',name='Remove SWE-bench Lite',exact=True).click()
  assert page.locator('#add-swebench').is_visible()
  page.locator('#swebench-count').fill('1')
  page.locator('#add-swebench').click()
  page.locator('#cancel-swebench').wait_for()
  prep.update(status='ready',count=1,message='Ready',completed=1)
  page.get_by_role('button',name='Remove SWE-bench Lite',exact=True).wait_for()
  report={'type':'basis-community-benchmark-report','schemaVersion':1,'benchmarkId':'swebench-lite','datasetRevision':'a'*40,'harnessRevision':'b'*40,'agent':'Fixture agent','model':'fixture-model','executionMode':'CLI','runId':'test-import','provenance':'external-official-harness','verified':False,'humanAccepted':False,'tasks':[{'id':'repo__issue-1','status':'resolved','durationSeconds':1}]}
  page.locator('#lite-report-file').set_input_files({'name':'report.json','mimeType':'application/json','buffer':json.dumps(report).encode()})
  page.get_by_text('1 imported · unverified',exact=True).wait_for()
  page.locator('.benchmark-imported summary').click()
  assert page.get_by_text('Fixture agent · fixture-model',exact=True).is_visible()
  page.get_by_role('button',name='Continue to evaluation',exact=True).click()
  assert page.locator('.benchmark-panel').count()==0
  if page.locator('#platform-review-scope').count():
   page.locator('.evaluation-scope summary').click()
   page.locator('#platform-review-scope').uncheck()
  page.locator('#evaluation-consent').check()
  page.wait_for_function('!document.querySelector("#start-evaluation").disabled')
  page.locator('#start-evaluation').click()
  page.wait_for_function('document.querySelector("#evaluation-progress").textContent.includes("6 of 6")')
  nav('Results');page.wait_for_function('id=>document.querySelector("#evaluation-history")?.value===id && document.querySelector(".results-header .result-status")?.textContent.includes("completed")',arg=runner.snapshot()['id'])
  assert len({r['folder'] for r in runner.snapshot()['results']})==6
  usage=runner.snapshot()['usageSummary']
  assert usage['candidates']['estimatedCostUsd']['value']==.004936
  assert usage['candidates']['estimatedCostUsd']['recorded']==4
  assert usage['candidates']['estimatedCostUsd']['total']==6
  assert usage['judge']['attempts']==0
  assert '$0.0049' in page.locator('.usage-overview summary').inner_text()
  assert 'partial' in page.locator('.usage-overview summary').inner_text()
  page.locator('.usage-overview summary').click()
  assert '400' in page.locator('.usage-breakdown').inner_text()
  assert 'No judge calls' in page.locator('.judge-usage').inner_text()

  assert page.get_by_role('cell',name='second-model Claude Code',exact=False).count()==2
  assert page.locator('.attempt-row').count()==6
  assert 'unverified' in page.locator('body').inner_text()
  page.locator('.results-benchmark-filter summary').click()
  page.locator('[data-include-suite]').uncheck()
  assert page.locator('.attempt-row').count()==3
  page.locator('.results-benchmark-filter summary').click()
  page.locator('[data-include-suite]').check()
  assert page.locator('.attempt-row').count()==6
  page.locator('[data-review-attempt]').first.click()
  page.locator('.modal [name="notes"]').fill('Checked generated source and acceptance')
  page.locator('.modal').get_by_role('button',name='Save',exact=True).click()
  page.get_by_text('Human rejected',exact=False).first.wait_for()
  assert runner.snapshot()['plan']['setup']['tasks'][0]['name']=='Team greeting'
  page.get_by_role('tab',name='JSON',exact=True).click()
  assert page.locator('.json-lines').is_visible()
  with page.expect_download() as downloaded:
    page.locator('#download-setup-json').click()
  assert downloaded.value.suggested_filename=='setup.json'
  page.get_by_role('tab',name='Requirements',exact=False).click()
  assert page.locator('#setup-panel-requirements').is_visible()
  page.get_by_role('tab',name='Overview',exact=True).click()
  page.locator('[data-artifacts]').first.click()
  page.locator('[data-file="workspace/solution.py"]').click()
  page.wait_for_function('document.querySelector(".artifact-preview").textContent.includes("hello")')
  with page.expect_download() as downloaded:
    page.locator('[data-artifact-download]').click()
  assert downloaded.value.suggested_filename=='solution.py'
  page.get_by_role('button',name='Close',exact=True).click()
  page.locator('[data-review-attempt]').first.click()
  assert page.locator('.modal [name="notes"]').input_value()=='Checked generated source and acceptance'
  page.route('**/api/local/review',lambda route: route.fulfill(status=400,content_type='application/json',body='{"error":"Review save unavailable"}'))
  page.locator('.modal').get_by_role('button',name='Save',exact=True).click()
  page.locator('.modal [role="alert"]').wait_for()
  assert page.locator('.modal [name="notes"]').input_value()=='Checked generated source and acceptance'
  page.unroute('**/api/local/review')
  page.locator('.modal').get_by_role('button',name='Save',exact=True).click()
  page.locator('.modal').wait_for(state='detached')

  out=ROOT/'test-results/local';out.mkdir(parents=True,exist_ok=True)
  page.screenshot(path=str(out/'results-desktop.png'),full_page=True)
  page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(200)
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
  page.screenshot(path=str(out/'results-mobile.png'),full_page=True)
  page.set_viewport_size({'width':1440,'height':1000})
  nav('Set up','Services');page.reload();nav('Set up','Services')
  page.wait_for_function('document.querySelector(\'[data-key-status="OPENAI_API_KEY"]\').textContent==="Configured"')
  out=ROOT/'test-results/local';out.mkdir(parents=True,exist_ok=True)
  page.screenshot(path=str(out/'settings-desktop.png'),full_page=True)
  nav('Run evaluation');page.locator('#evaluation-progress').wait_for()
  assert page.locator('.run-phases .done').count()==4
  assert page.locator('.run-phases .current').count()==0
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
  # Completed execution remains green even when models fail checks or time out.
  outcomes=[{**r,'status':'completed','checkPassed':False} for r in finished['results']]
  outcomes[0]={**outcomes[0],'status':'timeout','checkPassed':None}
  page.locator('h1').click()
  runner.update(status='partial',results=outcomes,total=len(outcomes))
  page.wait_for_timeout(2800)
  assert page.locator('.run-heading h2').inner_text()=='Evaluation complete'
  assert page.locator('.run-phases .done').count()==4
  assert 'timed out' in page.locator('.run-meter').inner_text()
  runner.update(**finished)
  for status,phase,message in [('preparing','prepare','Downloading agent tools'),('running','agent','Running Claude Code'),('running','check','Checking Claude Code'),('failed','check','Runner failed')]:
   runner.update(status=status,phase=phase,message=message,finishedAt=None if status in ('preparing','running') else time.time(),currentAgent='claude',currentTask=0,results=[])
   page.locator('h1').click()
   page.wait_for_timeout(2800)
   assert page.locator('#evaluation-progress .run-heading').inner_text().find(message)>=0 or status=='failed'
   if status in ('preparing','running'):
    assert page.locator('#evaluation-progress .status-led.is-active').count()>0
    assert page.locator('.run-phases [aria-current=step]').count()==1
    if phase=='agent':
     timing="document.querySelector('#evaluation-progress').getAnimations({subtree:true}).filter(a=>a.effect.target.closest('.run-heading,.run-phases') && ['phase-spin','run-led'].includes(a.animationName)).map(a=>({name:a.animationName,start:a.startTime}))"
     before=page.evaluate(timing)
     assert any(a['name']=='phase-spin' for a in before)
     page.wait_for_timeout(2800)
     after=page.evaluate(timing)
     assert before==after, f'Polling restarted animations: {before} -> {after}'
   else:
    assert page.locator('.run-phases .current').count()==0
    assert page.locator('.run-phases .warning').count()>0
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
  touch.get_by_role('navigation',name='Main navigation').get_by_role('button',name='Set up',exact=True).tap()
  touch.get_by_role('navigation',name='Set up sections').get_by_role('button',name='Tasks & Benchmarks',exact=True).tap()
  touch.get_by_role('button',name='About SWE-bench Lite',exact=True).tap()
  assert touch.get_by_role('tooltip').is_visible()
  touch.locator('#swebench-count').tap()
  assert touch.get_by_role('tooltip').count()==0
  assert not errors,errors
  browser.close()
finally:
 server.shutdown();server.server_close();temporary.cleanup()
print('PASS local UI: shared saved-key detection, missing-key gate, consent, automatic results, reload, mobile; no paid calls')
