"""Real Chromium checks for mobile, reduced motion, keyboard and review handoff."""
import base64
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from test_day1_brief import NOW, cards, snapshot
from vortex.day1_brief import build_brief, render_brief


class BriefBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.driver=sync_playwright().start()
        executable=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium')
        cls.browser=cls.driver.chromium.launch(headless=True,
            **({'executable_path':executable} if executable else {}),args=['--no-sandbox'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.driver.stop()

    def page(self, width=1920, height=1080, reduced=False, **kwargs):
        context=self.browser.new_context(viewport=dict(width=width,height=height),
            reduced_motion='reduce' if reduced else 'no-preference')
        self.addCleanup(context.close)
        page=context.new_page()
        page.set_content(render_brief(build_brief(snapshot(),next_gw=10,now=NOW),cards=cards(),**kwargs))
        return page

    def test_desktop_and_mobile_have_no_overflow_or_clipped_agenda(self):
        for width,height in ((3840,2160),(1920,1080),(390,844),(320,740)):
            with self.subTest(width=width):
                page=self.page(width,height)
                self.assertEqual(page.locator('.agenda-card').count(),5)
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width)
                screenshots=os.environ.get('DAY1_BRIEF_SCREENSHOT_DIR')
                if screenshots:
                    folder=Path(screenshots);folder.mkdir(parents=True,exist_ok=True)
                    page.screenshot(path=str(folder/f'brief-{width}.png'),full_page=True)
                for card in page.locator('.agenda-card').all():
                    box=card.bounding_box()
                    self.assertGreaterEqual(box['x'],0)
                    self.assertLessEqual(box['x']+box['width'],width)
                    self.assertTrue(card.evaluate('(e)=>e.scrollWidth<=e.clientWidth'))

    def test_keyboard_agenda_goes_to_real_review_and_no_motion_autoplays(self):
        page=self.page(390,844,reduced=True)
        page.keyboard.press('Tab');page.keyboard.press('Enter')
        self.assertEqual(page.evaluate('document.activeElement.id'),'gameweek-review')
        self.assertIn('16',page.locator('.score-grid').inner_text())
        self.assertFalse(page.evaluate('document.body.classList.contains("video")'))
        page.locator('#play').click()
        self.assertFalse(page.evaluate('document.body.classList.contains("video")'))

    def test_timed_handoff_is_ready_and_same_origin(self):
        timeline=dict(hook=0,brand=4,title=9,cards=[14,17,20,23,26],transition=33,end=38)
        child='<html><body id="actual-review">Verified review<script>window.__ready=true;window.__seek=t=>{document.body.dataset.seek=t}</script></body></html>'
        uri='data:text/html;base64,'+base64.b64encode(child.encode()).decode()
        page=self.page(timeline=timeline,review_uri=uri)
        page.wait_for_function('window.__ready===true')
        page.evaluate('(t)=>window.__setBriefTimeline(t,[])',timeline)
        page.evaluate('window.__seek(0)')
        self.assertEqual(page.locator('.brand').evaluate('(e)=>getComputedStyle(e).opacity'),'0')
        page.evaluate('window.__seek(37.9)')
        self.assertEqual(page.locator('.handoff').evaluate('(e)=>getComputedStyle(e).opacity'),'1')
        self.assertEqual(page.evaluate('document.querySelector("iframe").contentDocument.body.dataset.seek'),'0')
        self.assertEqual(page.locator('.agenda-card.active').inner_text().splitlines()[1],'CAPTAINCY AND FINAL XI')


if __name__=='__main__':unittest.main()
