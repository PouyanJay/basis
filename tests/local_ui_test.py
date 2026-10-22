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
 with patch.object(bridge,'vault',return_value=TestVault()),patch.object(bridge,'docker_ready',return_value=True),sync_playwright() as p:
  browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
  page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(f'http://127.0.0.1:{server.server_port}/')
  def nav(section,label=None):
   page.get_by_role('navigation',name='Main navigation').get_by_role('button',name=section,exact=True).click()
   if label:page.get_by_role('navigation',name=section+' sections').get_by_role('button',name=label,exact=True).click()
  nav('Set up','Requirements')
  for name in ['Cursor','Devin','OpenCode']:page.get_by_role('button',name=f'Remove {name} from evaluation',exact=True).click()
  assert page.get_by_role('navigation',name='Set up sections').get_by_role('button',name='Credentials',exact=True).count()==0
  nav('Settings')
  page.locator('[data-local-key="OPENAI_API_KEY"]').fill('test-only-key-never-real')
  page.locator('[data-save-local="OPENAI_API_KEY"]').click()
  page.wait_for_function('document.querySelector(\'[data-key-status="OPENAI_API_KEY"]\').textContent==="Configured"')
  assert page.locator('[data-local-key="OPENAI_API_KEY"]').input_value()==''
  assert 'test-only-key-never-real' not in page.evaluate('JSON.stringify(localStorage)')
  nav('Set up','Requirements')
  page.wait_for_function('document.querySelector(\'[data-key-status="OPENAI_API_KEY"]\').textContent==="Configured"')
  nav('Run evaluation')
  page.locator('#evaluation-consent').check();assert page.locator('#start-evaluation').is_disabled()
  nav('Set up','Requirements')
  page.locator('[data-local-key="ANTHROPIC_API_KEY"]').fill('test-only-second-key')
  page.locator('[data-save-local="ANTHROPIC_API_KEY"]').click()
  page.wait_for_function('document.querySelector(\'[data-key-status="ANTHROPIC_API_KEY"]\').textContent==="Configured"')
  nav('Set up','Tasks')
  page.get_by_role('button',name='Add task',exact=True).click()
  page.locator('.modal [name="name"]').fill('Team greeting')
  page.locator('.modal [name="acceptance"]').fill('Return hello')
  page.locator('.modal').get_by_role('button',name='Save',exact=True).click()
  nav('Run evaluation')
  page.locator('#benchmark-pack-path').fill(str(pack))
  page.locator('#add-benchmark-pack').click()
  page.locator('[data-remove-pack]').wait_for()
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
  nav('Run evaluation');page.locator('#evaluation-progress').wait_for()
  page.screenshot(path=str(out/'run-desktop.png'),full_page=True)
  page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(400)
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
  page.screenshot(path=str(out/'run-mobile.png'),full_page=True)
  assert not errors,errors
  browser.close()
finally:
 server.shutdown();server.server_close();temporary.cleanup()
print('PASS local UI: shared saved-key detection, missing-key gate, consent, automatic results, reload, mobile; no paid calls')
