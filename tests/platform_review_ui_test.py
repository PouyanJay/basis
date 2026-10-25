"""Cross-provider organization review through real HTTP, with deterministic unpaid sources/judge."""
import functools
import http.server
import pathlib
import json
import tempfile
import threading
from playwright.sync_api import sync_playwright
from test_platform_review import review_fixture, request, QUOTE, RUN
from credential_companion import Handler
from test_recommendations import fake_request
from recommendations import Recommendations
ROOT=pathlib.Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
 runner,manager,job=review_fixture(tmp);release=threading.Event()
 def delayed(*args):
  release.wait(15)
  return request(*args)
 manager.request=delayed
 server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,token='test-token',runner=runner))
 threading.Thread(target=server.serve_forever,daemon=True).start()
 browser=p.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(f'http://127.0.0.1:{server.server_port}/')
 # Keep a valid full study while changing only selected provider models.
 page.evaluate('''async () => {const {demo}=await import('/core.js');const s=structuredClone(demo);s.platforms.forEach(p=>{p.enabled=['claude','codex'].includes(p.id);p.models=p.id==='claude'?['haiku','sonnet']:p.id==='codex'?['model-a']:[]});localStorage.setItem('basis-iris-production-v1',JSON.stringify(s))}''')
 page.reload()
 page.get_by_role('button',name='Continue',exact=True).click()
 nav=page.get_by_role('navigation',name='Main navigation')
 nav.get_by_role('button',name='Set up',exact=True).click()
 page.get_by_role('navigation',name='Set up sections').get_by_role('button',name='Team context',exact=True).click()
 page.get_by_role('heading',name='Organization requirements',exact=True).wait_for()
 page.get_by_label('Data retention requirement',exact=True).fill('At most 30 days')
 page.get_by_label('Data retention requirement',exact=True).press('Tab')
 page.get_by_role('tab',name='Product & workflow',exact=True).click()
 page.get_by_role('tab',name='Security & data',exact=True).click()
 assert page.get_by_label('Data retention requirement',exact=True).input_value()=='At most 30 days'
 out=ROOT/'test-results/platform-review';out.mkdir(parents=True,exist_ok=True)
 page.screenshot(path=str(out/'setup-desktop.png'),full_page=True)
 nav.get_by_role('button',name='Run evaluation',exact=True).click()
 assert page.locator('.evaluation-scope').is_visible()
 page.screenshot(path=str(out/'run-desktop.png'),full_page=True)
 page.get_by_role('button',name='All runs',exact=True).click()
 page.locator('[data-open-workspace="'+RUN+'"]').first.click()
 nav.get_by_role('button',name='Results',exact=True).click()
 page.get_by_role('tab',name='Organization fit',exact=True).click()
 page.get_by_role('button',name='Research platforms',exact=True).click()
 page.get_by_text('Reviewing official sources',exact=True).wait_for()
 page.screenshot(path=str(out/'researching-desktop.png'),full_page=True)
 # Let initial rendering settle; completion must arrive through the polling loop.
 page.wait_for_timeout(3000)
 release.set()
 page.get_by_text('Research complete',exact=True).wait_for()
 assert page.locator('.fit-cell .meets').count()==2
 assert len(manager.status(RUN)['calls'])==2
 page.locator('.fit-cell').first.click()
 assert page.get_by_text(QUOTE,exact=True).is_visible()
 page.screenshot(path=str(out/'matrix-desktop.png'),full_page=True)
 page.set_viewport_size({'width':390,'height':844})
 page.wait_for_timeout(300)
 assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
 page.screenshot(path=str(out/'matrix-mobile.png'),full_page=True)
 page.set_viewport_size({'width':1440,'height':1000})
 page.get_by_role('tab',name='Recommendation',exact=True).click()
 assert page.locator('.rec-platform-fit').is_visible()
 def combined_judge(*args):
  response=fake_request(*args)
  if 'headline' in args[5]['properties']:
   report=json.loads(response['output'][0]['content'][0]['text'])
   report['reasons'][0]={'text':'Official policy supports the training requirement.','evidence':['platform:claude-anthropic:training']}
   response['output'][0]['content'][0]['text']=json.dumps(report)
  return response
 runner.recommendations=Recommendations(runner,runner.judge_settings,combined_judge)
 page.get_by_role('button',name='Generate recommendation',exact=True).click()
 page.get_by_text('Official policy supports the training requirement.',exact=True).wait_for()
 page.locator('[data-rec-evidence="platform:claude-anthropic:training"]').first.click()
 assert page.get_by_role('tab',name='Organization fit',exact=True).get_attribute('aria-selected')=='true'
 assert page.get_by_text(QUOTE,exact=True).is_visible()

 # Same-provider selection removes new setup/scope while historical results retain their review.
 page.get_by_role('button',name='All runs',exact=True).click()
 page.get_by_role('button',name='Continue',exact=True).click()
 page.get_by_role('navigation',name='Set up sections').get_by_role('button',name='Services',exact=True).click()
 page.get_by_role('button',name='Remove Codex from evaluation',exact=True).click()
 page.get_by_role('button',name='Continue to team context',exact=True).click()
 assert page.get_by_role('heading',name='Organization requirements',exact=True).count()==0
 nav.get_by_role('button',name='Run evaluation',exact=True).click()
 assert page.locator('.evaluation-scope').count()==0
 assert not errors,errors
 print('PASS cross-provider setup, scope, live research, citations, costs, recommendation integration, mobile and same-provider gating; no paid calls')
 browser.close();server.shutdown()
