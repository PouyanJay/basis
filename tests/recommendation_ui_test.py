"""Approved recommendation canvases driven through real HTTP endpoints; fake judge only."""
import functools
import http.server
import json
import pathlib
import tempfile
import threading
from unittest.mock import patch
from playwright.sync_api import sync_playwright
from test_recommendations import fixture, fake_request, RUN
from credential_companion import Handler
from recommendations import Recommendations
ROOT=pathlib.Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
 runner=fixture(tmp);quality=threading.Event();writing=threading.Event()
 def request(*args):
  (writing if 'headline' in args[5]['properties'] else quality).wait(20)
  return fake_request(*args)
 runner.recommendations=Recommendations(runner,runner.judge_settings,request)
 server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,token='test-token',runner=runner))
 threading.Thread(target=server.serve_forever,daemon=True).start()
 browser=p.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1040});errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(f'http://127.0.0.1:{server.server_port}/')
 page.get_by_role('navigation',name='Main navigation').get_by_role('button',name='Results',exact=True).click()
 page.get_by_role('tab',name='Recommendation',exact=True).click()
 page.get_by_role('button',name='Generate recommendation',exact=True).click()
 page.locator('.rec-comparison tbody tr').first.wait_for()
 page.wait_for_function('document.querySelector(".rec-stages .current")?.textContent.includes("Comparison")')
 out=ROOT/'test-results/recommendation';out.mkdir(parents=True,exist_ok=True)
 page.screenshot(path=str(out/'generating-desktop.png'),full_page=True)
 assert page.locator('.rec-comparison tbody tr').count()==5
 before=page.locator('#rec-elapsed').inner_text()
 page.wait_for_timeout(2100)
 assert page.locator('#rec-elapsed').inner_text()!=before
 quality.set()
 page.wait_for_function('document.querySelector(".rec-stages .current")?.textContent.includes("Recommendation")')
 assert page.locator('.rec-quality section').count()==5
 assert page.get_by_text('Model comparison completed',exact=True).is_visible()
 writing.set()
 page.get_by_text('Continue with a controlled pilot.',exact=True).wait_for()
 assert page.locator('.rec-preferred').count()==1
 assert page.locator('.rec-comparison tbody tr').count()==5
 page.screenshot(path=str(out/'completed-desktop.png'),full_page=True)
 page.get_by_text('Detailed comparison',exact=False).first.click()
 assert page.get_by_text('Tradeoffs',exact=True).is_visible()
 page.get_by_role('tab',name='Method',exact=True).click()
 assert page.get_by_text('basis-judge-v3',exact=True).is_visible()
 assert page.locator('.rec-evidence-tabs [aria-selected=true]').count()==1
 page.locator('#rec-evidence').screenshot(path=str(out/'evidence-method.png'),animations='disabled')
 page.get_by_role('tab',name='Usage',exact=True).click()
 assert page.locator('.rec-call-table tbody tr').count()==4
 page.locator('#rec-evidence').screenshot(path=str(out/'evidence-usage.png'),animations='disabled')
 page.get_by_role('tab',name='Sources',exact=True).click()
 assert page.get_by_text('15 included',exact=True).is_visible()
 assert page.locator('.rec-judge-name').count()==0
 assert not page.locator('.results-run-meta').is_visible()
 assert page.get_by_text('Judge settings',exact=True).count()==0
 with page.expect_download() as download:
  page.get_by_role('button',name='Export',exact=True).last.click()
 assert 'controlled pilot' in pathlib.Path(download.value.path()).read_text()
 # Poll must preserve disclosures when no data changed.
 page.wait_for_timeout(2500)
 assert page.get_by_text('Tradeoffs',exact=True).is_visible()
 page.locator('.rec-details[open] summary').evaluate_all('(els)=>els.forEach(el=>el.click())')
 page.set_viewport_size({'width':390,'height':844})
 page.wait_for_timeout(300)
 assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
 page.screenshot(path=str(out/'completed-mobile.png'),full_page=True)
 page.set_viewport_size({'width':1440,'height':1040})
 runner.review(RUN,'0:claude-0',{'accepted':True,'notes':'Human reviewed'})
 page.get_by_text('Evidence or selected suites changed. This assessment is out of date; regenerate before using it.',exact=True).wait_for()
 assert page.locator('.rec-preferred').count()==0
 # No implicit paid reruns on refresh, tab changes or review changes.
 assert len(runner.recommendations.status(RUN)['judgeRuns'])==4
 page.reload()
 page.get_by_role('navigation',name='Main navigation').get_by_role('button',name='Results',exact=True).click()
 assert page.get_by_role('tab',name='Results',exact=True).get_attribute('aria-selected')=='true'
 page.get_by_role('tab',name='Recommendation',exact=True).click()
 page.get_by_text('Continue with a controlled pilot.',exact=True).wait_for()
 # Provider failure stays inline; Retry is explicit and Stop prevents synthesis.
 def fail(*args):raise RuntimeError('Judge rate limit reached. Wait, then retry.')
 runner.recommendations.request=fail
 page.get_by_role('button',name='Regenerate recommendation',exact=True).click()
 page.get_by_role('button',name='Retry recommendation',exact=True).wait_for()
 assert 'rate limit' in page.locator('.rec-notice').first.inner_text()
 quality.clear();writing.clear();runner.recommendations.request=request
 page.get_by_role('button',name='Retry recommendation',exact=True).click()
 page.locator('.rec-comparison tbody tr').first.wait_for()
 page.wait_for_function('document.querySelector(".rec-stages .current")?.textContent.includes("Comparison")')
 page.get_by_role('button',name='Stop',exact=True).click()
 page.get_by_text('Stopping after current request',exact=True).wait_for()
 quality.set()
 page.get_by_text('Stopped',exact=True).wait_for()
 assert len(runner.recommendations.status(RUN)['judgeRuns'])==6
 assert not errors,errors
 print('PASS generating/final 5-model canvases, stages, export, responsive layout, stale review, reload; no paid calls')
 browser.close();server.shutdown()
