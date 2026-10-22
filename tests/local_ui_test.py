"""Real local HTTP/UI flow with an in-memory test vault and simulated runner; no provider calls."""
import functools
import http.server
import importlib.util
import json
import pathlib
import threading
from unittest.mock import patch
from playwright.sync_api import sync_playwright

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('local_bridge',ROOT/'scripts/credential_companion.py')
bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
class TestVault:
    values={}
    def get_password(self, service, name): return self.values.get(name)
    def set_password(self, service, name, value): self.values[name]=value
class TestRunner:
    job=None
    def snapshot(self): return self.job
    def start(self, agents, consent):
        assert consent is True
        assert [e['agent'] for e in agents]==['claude','codex']
        self.job={'id':'test-only','status':'completed','message':'Simulated test completion','results':[{'candidate':e['agent'],'model':'test-only','automatedTestsPass':True,'elapsedSeconds':1} for e in agents]}
        return self.job

server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(bridge.Handler,token='test-only-token',runner=TestRunner()))
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
  nav('Settings')
  page.locator('[data-local-key="OPENAI_API_KEY"]').fill('test-only-key-never-real')
  page.locator('[data-save-local="OPENAI_API_KEY"]').click()
  page.wait_for_function('document.querySelector(\'[data-key-status="OPENAI_API_KEY"]\').textContent==="Configured"')
  assert page.locator('[data-local-key="OPENAI_API_KEY"]').input_value()==''
  assert 'test-only-key-never-real' not in page.evaluate('JSON.stringify(localStorage)')
  nav('Set up','Credentials')
  page.wait_for_function('document.querySelector(\'[data-key-status="OPENAI_API_KEY"]\').textContent==="Configured"')
  nav('Run tests')
  page.locator('#local-consent').check();assert page.locator('#start-local-run').is_disabled()
  nav('Set up','Credentials')
  page.locator('[data-local-key="ANTHROPIC_API_KEY"]').fill('test-only-second-key')
  page.locator('[data-save-local="ANTHROPIC_API_KEY"]').click()
  page.wait_for_function('document.querySelector(\'[data-key-status="ANTHROPIC_API_KEY"]\').textContent==="Configured"')
  nav('Run tests');page.locator('#local-consent').check()
  page.get_by_role('button',name='Run selected services',exact=True).click()
  page.locator('.local-result').first.wait_for()
  assert page.locator('.local-result').count()==2
  nav('Results');page.locator('.local-result').first.wait_for()
  assert page.locator('.local-result').count()==2
  assert not page.get_by_role('heading',name='No results yet',exact=True).is_visible()
  nav('Settings');page.reload();nav('Settings')
  page.wait_for_function('document.querySelector(\'[data-key-status="OPENAI_API_KEY"]\').textContent==="Configured"')
  out=ROOT/'test-results/local';out.mkdir(parents=True,exist_ok=True)
  page.screenshot(path=str(out/'settings-desktop.png'),full_page=True)
  nav('Run tests');page.locator('.local-result').first.wait_for()
  page.screenshot(path=str(out/'run-desktop.png'),full_page=True)
  page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(400)
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
  page.screenshot(path=str(out/'run-mobile.png'),full_page=True)
  assert not errors,errors
  browser.close()
finally:
 server.shutdown();server.server_close()
print('PASS local UI: shared saved-key detection, missing-key gate, consent, automatic results, reload, mobile; no paid calls')
