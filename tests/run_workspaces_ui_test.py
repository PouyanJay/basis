"""Real HTTP/browser workspace lifecycle; simulated executor and model catalog, no paid calls."""
import functools
import http.server
import json
import pathlib
import tempfile
import threading
import time
from unittest.mock import patch
from playwright.sync_api import sync_playwright
from test_run_workspaces import Vault
from credential_companion import Handler, Runner
import credential_companion as bridge
import model_discovery
ROOT=pathlib.Path(__file__).resolve().parents[1]
class TestRunner(Runner):
 def command(self,*args,**kwargs):return 0
 def container(self,work,checks,args,timeout,key=None,value=None):
  time.sleep(.1)
  if key:(work/'solution.py').write_text('answer = 42')
  return 0
with tempfile.TemporaryDirectory() as tmp,patch.object(bridge,'vault',return_value=Vault()),patch.object(bridge,'docker_ready',return_value=True),patch.object(model_discovery,'request_json',return_value={'data':[{'id':'test-model','display_name':'Test model'}]}),sync_playwright() as p:
 runner=TestRunner(pathlib.Path(tmp)/'state')
 source=pathlib.Path(tmp)/'source';source.mkdir();(source/'original.py').write_text('before = True')
 server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,token='workspace-test',runner=runner));threading.Thread(target=server.serve_forever,daemon=True).start()
 browser=p.chromium.launch();context=browser.new_context(viewport={'width':1440,'height':1000});page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(f'http://127.0.0.1:{server.server_port}/')
 page.get_by_role('button',name='New run',exact=True).click()
 page.get_by_label('Run name',exact=True).fill('Shipping calculator');page.get_by_label('Run name',exact=True).press('Tab')
 for name in ['Codex','Cursor','Devin','OpenCode']:page.get_by_role('button',name='Remove '+name+' from evaluation',exact=True).click()
 page.get_by_role('combobox',name='Claude Code model',exact=True).click();page.get_by_role('option',name='Test model · test-model',exact=True).click()
 page.get_by_role('button',name='Continue to team context',exact=True).click()
 page.get_by_role('button',name='Continue to tasks & benchmarks',exact=True).click()
 page.get_by_role('button',name='Add task',exact=True).click();page.locator('.modal [name=name]').fill('Calculate shipping');page.locator('.modal [name=acceptance]').fill('Return the correct shipping charge');page.locator('.modal [name=sourcePath]').fill(str(source));page.locator('.modal').get_by_role('button',name='Save',exact=True).click()
 page.get_by_text('Saved',exact=True).wait_for()
 first=page.evaluate("localStorage.getItem('basis-active-run')")
 page.reload();page.get_by_role('heading',name='Calculate shipping',exact=True).wait_for()
 assert runner.workspaces.get(first)['setup']['tasks'][0]['name']=='Calculate shipping'
 page.get_by_role('button',name='Continue to evaluation',exact=True).click()
 page.locator('#evaluation-consent').check();page.locator('#start-evaluation:not([disabled])').wait_for();page.locator('#start-evaluation').click()
 page.get_by_role('button',name='Clone run',exact=True).wait_for()
 page.wait_for_function("document.querySelector('.workspace-run-header .workspace-status')?.textContent.includes('Completed')")
 assert page.locator('#start-evaluation').is_hidden()
 page.get_by_role('navigation',name='Main navigation').get_by_role('button',name='Results',exact=True).click()
 assert page.get_by_role('heading',name='Shipping calculator',exact=True).is_visible()
 original=(runner.folder/'evaluations'/first/'result.json').read_bytes()
 out=ROOT/'test-results/workspaces';out.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(out/'completed.png'),full_page=True)
 page.get_by_role('navigation',name='Main navigation').get_by_role('button',name='Set up',exact=True).click()
 assert page.locator('[data-act="toggle-service"]').first.is_disabled()
 page.get_by_role('button',name='Clone run',exact=True).click();page.get_by_label('Run name',exact=True).wait_for()
 second=page.evaluate("localStorage.getItem('basis-active-run')");assert second!=first
 assert not (runner.folder/'evaluations'/second/'result.json').exists()
 page.get_by_label('Run name',exact=True).fill('Shipping calculator v2');page.get_by_label('Run name',exact=True).press('Tab')
 page.get_by_text('Saved',exact=True).wait_for();page.screenshot(path=str(out/'draft.png'),full_page=True)
 (source/'original.py').write_text('after = True')
 page.get_by_role('button',name='Continue to team context',exact=True).click();page.get_by_role('button',name='Continue to tasks & benchmarks',exact=True).click();page.get_by_role('button',name='Continue to evaluation',exact=True).click()
 page.locator('#evaluation-consent').check();page.locator('#start-evaluation:not([disabled])').wait_for();page.locator('#start-evaluation').click()
 page.wait_for_function("document.querySelector('.workspace-run-header .workspace-status')?.textContent.includes('Completed')")
 assert (runner.folder/'evaluations'/second/'inputs/0/source/original.py').read_text()=='before = True'
 assert (runner.folder/'evaluations'/first/'result.json').read_bytes()==original
 page.get_by_role('button',name='All runs',exact=True).click();page.locator('.runs-table tbody tr').nth(1).wait_for();assert page.locator('.runs-table tbody tr').count()==2
 page.screenshot(path=str(out/'library.png'),full_page=True)
 page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(300);page.screenshot(path=str(out/'library-mobile.png'),full_page=True);assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),page.evaluate('Array.from(document.querySelectorAll("*")).filter(e=>e.getBoundingClientRect().right>innerWidth+1).map(e=>[e.tagName,e.className,e.getBoundingClientRect().width]).slice(0,20)')
 page.set_viewport_size({'width':1440,'height':1000});page.get_by_role('button',name='Shipping calculator',exact=True).click();page.get_by_role('heading',name='Shipping calculator',exact=True).wait_for()
 page.reload();page.get_by_role('heading',name='Shipping calculator',exact=True).wait_for();assert page.evaluate("localStorage.getItem('basis-active-run')")==first
 # A stale tab must preserve its edits without overwriting a newer saved draft.
 page.get_by_role('button',name='Clone run',exact=True).click();page.get_by_label('Run name',exact=True).wait_for()
 draft=page.evaluate("localStorage.getItem('basis-active-run')")
 stale=page.context.new_page();stale.goto(f'http://127.0.0.1:{server.server_port}/');stale.get_by_label('Run name',exact=True).wait_for()
 page.get_by_label('Run name',exact=True).fill('Saved by first tab');page.get_by_label('Run name',exact=True).press('Tab');page.get_by_text('Saved',exact=True).wait_for()
 stale.get_by_label('Run name',exact=True).fill('Recovered edits');stale.get_by_label('Run name',exact=True).press('Tab');stale.get_by_role('button',name='Save edits as a new draft',exact=True).wait_for()
 assert runner.workspaces.get(draft)['name']=='Saved by first tab'
 stale.get_by_role('button',name='Save edits as a new draft',exact=True).click();stale.get_by_text('Saved',exact=True).wait_for()
 recovered=stale.evaluate("localStorage.getItem('basis-active-run')");assert recovered!=draft
 assert runner.workspaces.get(recovered)['name']=='Recovered edits'
 assert runner.workspaces.get(draft)['name']=='Saved by first tab'
 stale.close()
 page.get_by_role('button',name='All runs',exact=True).click()
 page.locator(f'[data-delete-workspace="{first}"]').click()
 page.get_by_role('dialog').get_by_role('button',name='Cancel',exact=True).click()
 assert (runner.folder/'evaluations'/first).exists()
 page.locator(f'[data-delete-workspace="{first}"]').click()
 page.screenshot(path=str(out/'delete-confirmation.png'))
 page.get_by_role('dialog').get_by_role('button',name='Delete run',exact=True).click()
 page.locator(f'[data-delete-workspace="{first}"]').wait_for(state='detached')
 assert not (runner.folder/'evaluations'/first).exists()
 assert (runner.folder/'evaluations'/second/'result.json').exists()
 page.reload();page.get_by_role('heading',name='Runs',exact=True).wait_for()
 assert page.locator(f'[data-open-workspace="{first}"]').count()==0
 assert not errors,errors
 print('PASS durable autosave/reload, locked setup, clone with pinned inputs, two executions without reset, run switching, independent results, mobile, conflicting-tab recovery, permanent deletion and cancellation; no paid calls')
 browser.close();server.shutdown()
