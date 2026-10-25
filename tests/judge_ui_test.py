"""Judge configuration and requirement review through the real local HTTP server; no paid calls."""
import functools
import http.server
import importlib.util
import pathlib
import tempfile
import threading
from unittest.mock import patch
from playwright.sync_api import sync_playwright
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('bridge',ROOT/'scripts/credential_companion.py');bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
import model_discovery
class Vault:
    values={('basis-local','OPENAI_API_KEY'):'candidate-secret'}
    def get_password(self,scope,key):return self.values.get((scope,key))
    def set_password(self,scope,key,value):self.values[(scope,key)]=value
vault=Vault()
def response(url,headers):
    if 'bad-secret' in str(headers):raise RuntimeError('The provider rejected this key.')
    return {'data':[{'id':'judge-test-v1','display_name':'Judge test model'}]}
with tempfile.TemporaryDirectory() as tmp,patch.object(bridge,'vault',return_value=vault),patch.object(bridge,'docker_ready',return_value=False),patch.object(model_discovery,'request_json',side_effect=response),sync_playwright() as p:
 runner=bridge.Runner(pathlib.Path(tmp))
 server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(bridge.Handler,token='test-token',runner=runner))
 threading.Thread(target=server.serve_forever,daemon=True).start()
 browser=p.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(f'http://127.0.0.1:{server.server_port}/')
 page.get_by_role('button',name='New run',exact=True).click()
 def nav(main,sub=None):
    page.get_by_role('navigation',name='Main navigation').get_by_role('button',name=main,exact=True).click()
    if sub:page.get_by_role('navigation',name=main+' sections').get_by_role('button',name=sub,exact=True).click()
 nav('Settings')
 page.locator('#judge-key').fill('bad-secret')
 page.get_by_role('button',name='Test connection',exact=True).click()
 page.get_by_text('The provider rejected this key.',exact=True).wait_for()
 page.locator('#judge-key').fill('judge-secret-test')
 page.get_by_role('button',name='Test connection',exact=True).click()
 page.get_by_text('Connected. Select a model and save.',exact=True).wait_for()
 page.get_by_role('combobox',name='Model',exact=True).click()
 page.get_by_role('option',name='Judge test model',exact=True).click()
 page.get_by_role('button',name='Save judge',exact=True).click()
 page.get_by_text('Judge saved.',exact=True).wait_for()
 assert vault.get_password('basis-local','OPENAI_API_KEY')=='candidate-secret'
 assert vault.get_password('basis-judge','openai')=='judge-secret-test'
 assert 'judge-secret-test' not in page.evaluate('JSON.stringify(localStorage)')
 page.reload();nav('Settings')
 page.wait_for_function('document.querySelector("#judge-model").value==="judge-test-v1"')
 out=ROOT/'test-results/judge';out.mkdir(parents=True,exist_ok=True)
 page.screenshot(path=str(out/'settings-desktop.png'),full_page=True)
 nav('Set up','Services')
 page.get_by_role('navigation',name='Set up sections').get_by_role('button',name='Team context',exact=True).click()
 page.locator('[data-requirement="retention"]').click()
 page.get_by_role('combobox',name='Status',exact=True).click()
 page.get_by_role('option',name='Verified',exact=True).click()
 page.get_by_role('button',name='Save review',exact=True).click()
 assert 'Add an evidence' in page.locator('#requirement-feedback').inner_text()
 page.locator('[name="url"]').fill('https://example.com/policy')
 page.locator('[name="notes"]').fill('Checked policy and account settings against our requirements.')
 page.locator('[name="reviewer"]').fill('Alex')
 page.get_by_role('button',name='Save review',exact=True).click()
 page.get_by_text('Review saved.',exact=True).wait_for()
 assert 'Verified' in page.locator('[data-requirement="retention"]').inner_text()
 page.screenshot(path=str(out/'requirements-desktop.png'),full_page=True)
 page.reload();nav('Set up','Services');page.get_by_role('navigation',name='Set up sections').get_by_role('button',name='Team context',exact=True).click()
 page.locator('[data-requirement="retention"]').click()
 assert page.locator('[name="reviewer"]').input_value()=='Alex'
 assert page.locator('[name="url"]').input_value()=='https://example.com/policy'
 page.set_viewport_size({'width':390,'height':844})
 assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
 page.screenshot(path=str(out/'requirements-mobile.png'),full_page=True)
 assert not errors,errors
 print('PASS judge configuration, key isolation, catalog selection, review evidence validation, persistence, responsive layout; no paid calls')
 browser.close();server.shutdown()
