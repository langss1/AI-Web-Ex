"""
=============================================================
ACTION LAYER — Selenium WebDriver (PRIMARY) + HTTP (Auth only)
=============================================================
ALL web interactions go through Selenium WebDriver so the user
can see every request, injection, and server response in Chrome.

HTTP requests session is used ONLY for:
  - Login (getting PHPSESSID cookie)
  - Setting security cookie

The actual injection and response reading ALWAYS goes through
the visible Selenium browser.

Architecture:
  execute(action_type, url, vuln_type, payload)
    ├─ HTTP_INJECT    → Selenium browser GET with payload
    ├─ SELENIUM_INJECT → Selenium browser GET with payload (same)
    └─ CLI_EXEC       → subprocess.run(payload)
=============================================================
"""

import logging
import time
import urllib.parse
import subprocess
from bs4 import BeautifulSoup
import requests

# Selenium imports
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    UnexpectedAlertPresentException,
    TimeoutException,
    NoAlertPresentException,
    WebDriverException,
)

log = logging.getLogger(__name__)

# ── Signal tiers ───────────────────────────────────────────
# TIER 1 — Exploitation CONFIRMED: actual data extracted or JS executed.
# Only these trigger a "success" in the orchestrator.
EXPLOIT_CONFIRMED = {
    "sqli": [
        "First name:",   # DVWA output label when rows returned
        "Surname:",      # DVWA output label when rows returned
        "gordonb",       # known DVWA username — confirms data extracted
        "1337",          # smithy user_id in DVWA
        "0xdeadbeef",   # pablo user_id
    ],
    "xss": [
        # XSS success is detected via alert popup, not DOM text.
        # Add reflected payload markers here if needed.
        "xss_confirmed",
    ]
}

# TIER 2 — Vulnerability DETECTED: error or partial indicator visible.
# Noted in PCB (informs AI) but NOT counted as exploitation success.
VULN_DETECTED = {
    "sqli": [
        "you have an error in your sql syntax",
        "mysql_fetch_array()",
        "supplied argument is not a valid mysql",
        "uncaught mysqli_sql_exception",
        "fatal error",
        "first_name",   # column name exposed in error
        "user_id",
    ],
    "xss": [
        "alert(",
        "onerror=",
        "onload=",
        "onmouseover=",
        "<script",
        "javascript:",
    ]
}



class ActionLayer:
    def __init__(self, base_url: str):
        self.base_url    = base_url
        self.driver      = None
        self.http_session = requests.Session()

    # ── Selenium init ────────────────────────────────────────
    def _init_driver(self):
        if not self.driver:
            log.info("Memulai Selenium WebDriver (Chrome)...")
            options = webdriver.ChromeOptions()
            options.add_experimental_option("excludeSwitches", ["enable-logging"])
            self.driver = webdriver.Chrome(options=options)
            self.driver.implicitly_wait(3)

    # ── Login ────────────────────────────────────────────────
    def login(self, login_url: str, security_level: str = "low"):
        """Login via Selenium browser (visible). Sets security level via form."""
        self._init_driver()
        try:
            log.info(f"Browser → navigating to login: {login_url}")
            self.driver.get(login_url)
            time.sleep(0.8)

            self.driver.find_element(By.NAME, "username").clear()
            self.driver.find_element(By.NAME, "username").send_keys("admin")
            self.driver.find_element(By.NAME, "password").clear()
            self.driver.find_element(By.NAME, "password").send_keys("password")
            self.driver.find_element(By.NAME, "password").send_keys(Keys.RETURN)
            time.sleep(1)

            if "login.php" not in self.driver.current_url:
                log.info("✅ DVWA login successful via Selenium.")
            else:
                log.warning("⚠️  Login may have failed — still on login.php")

            # Set security level via form (browser visible)
            sec_url = self.base_url + "/security.php"
            log.info(f"Browser → setting security level to '{security_level}'")
            self.driver.get(sec_url)
            time.sleep(0.5)
            select_elem = self.driver.find_element(By.NAME, "security")
            for option in select_elem.find_elements(By.TAG_NAME, "option"):
                if option.get_attribute("value") == security_level:
                    option.click()
                    break
            self.driver.find_element(By.NAME, "seclev_submit").click()
            time.sleep(0.5)
            log.info(f"Security level set to: {security_level}")

        except WebDriverException as e:
            log.error(f"❌ WebDriver error during login: {e}")
        except Exception as e:
            log.error(f"Login error: {e}")
        return self.driver

    # ── Scout environment ────────────────────────────────────
    def scout_environment(self, login_url: str, security_level: str = "low"):
        """
        Scout phase:
          1. HTTP session login (background) — fast cookie acquisition
          2. Selenium browser login (visible) — user sees it happen
          3. Return environment profile
        """
        log.info("Scouting environment and auto-logging in via HTTP...")
        try:
            r = self.http_session.get(login_url)
            soup = BeautifulSoup(r.text, "html.parser")
            token_tag = soup.find("input", {"name": "user_token"})
            token_val = token_tag["value"] if token_tag else ""
            data = {
                "username"   : "admin",
                "password"   : "password",
                "Login"      : "Login",
                "user_token" : token_val,
            }
            self.http_session.post(login_url, data=data)
            self.http_session.cookies.set("security", security_level,
                                          domain="localhost", path="/")
            log.info(f"Scout Phase: HTTP Session logged in, security={security_level}")
        except Exception as e:
            log.error(f"Scout Phase Error (HTTP): {e}")

        # Selenium login — user watches this in browser
        self.login(login_url, security_level)

        return {
            "dvwa_security_level"  : security_level,
            "available_modules"    : ["sqli", "xss_r", "sqli_blind", "xss_s"],
            "current_form_context" : "Target parameters: id for sqli, name for xss",
        }

    # ── Main execution router ────────────────────────────────
    def execute(self, action_type: str, target_url: str,
                vuln_type: str, payload: str) -> dict:
        """
        Route injection to the correct tool.
        HTTP_INJECT and SELENIUM_INJECT both go through the Selenium
        browser so the user can see every request and response in Chrome.
        CLI_EXEC uses subprocess for external tools.
        """
        if action_type == "CLI_EXEC":
            return self._inject_subprocess(payload)
        else:
            # Both HTTP_INJECT and SELENIUM_INJECT → Selenium browser
            return self._inject_via_browser(target_url, vuln_type, payload)

    # ── Core browser injection ───────────────────────────────
    def _inject_via_browser(self, target_url: str,
                            vuln_type: str, payload: str) -> dict:
        """
        Inject payload by driving the Selenium browser to the target URL.
        The user sees the full DVWA page response in Chrome in real-time.
        """
        if not self.driver:
            log.warning("Selenium driver not initialized — cannot inject via browser.")
            return self._empty_obs()

        try:
            encoded = urllib.parse.quote(payload)

            if vuln_type == "sqli":
                full_url = f"{target_url}?id={encoded}&Submit=Submit"
            elif vuln_type == "xss":
                full_url = f"{target_url}?name={encoded}"
            else:
                full_url = f"{target_url}?payload={encoded}"

            log.info(f"Browser → navigating to: {full_url}")
            try:
                self.driver.get(full_url)
            except UnexpectedAlertPresentException:
                pass  # XSS alert fired during navigation — caught below

            time.sleep(0.4)  # let page render

            # ── XSS alert detection ──────────────────────────
            if vuln_type == "xss":
                return self._check_xss_alert(full_url)

            # ── SQLi / default: parse page source ───────────
            return self._parse_browser_page(vuln_type)

        except WebDriverException as e:
            log.warning(f"Selenium session lost: {e}")
            self.driver = None
            return self._empty_obs()
        except Exception as e:
            log.error(f"Browser injection error: {e}")
            return self._empty_obs()

    def _check_xss_alert(self, full_url: str) -> dict:
        """Check for XSS alert popup after browser navigation."""
        alert_triggered = False
        try:
            WebDriverWait(self.driver, 2).until(EC.alert_is_present())
            alert = self.driver.switch_to.alert
            log.info(f"\U0001f6a8 XSS Alert popup caught! Content: '{alert.text}'")
            alert.accept()
            alert_triggered = True
        except TimeoutException:
            pass
        except Exception:
            pass

        if alert_triggered:
            return {
                "status"      : 200,
                "dom_signal"  : True,   # TIER 1 — alert is confirmed exploitation
                "vuln_signal" : True,
                "triggered_by": "alert_popup",
                "raw_response": "Alert triggered successfully.",
                "response_len": 0,
            }
        return self._parse_browser_page("xss")

    def _parse_browser_page(self, vuln_type: str) -> dict:
        """Read browser page source. Check TIER 1 and TIER 2 signals."""
        raw         = ""
        dom_signal  = False   # TIER 1: real exploitation confirmed
        vuln_signal = False   # TIER 2: vulnerability detected
        triggered_by = ""
        try:
            # Handle late alert
            try:
                alert = self.driver.switch_to.alert
                log.info(f"\U0001f6a8 Late XSS alert caught: '{alert.text}'")
                alert.accept()
                return {
                    "status"      : 200,
                    "dom_signal"  : True,
                    "vuln_signal" : True,
                    "triggered_by": "alert_popup_late",
                    "raw_response": "Late alert triggered.",
                    "response_len": 0,
                }
            except NoAlertPresentException:
                pass

            raw         = self.driver.page_source
            search_text = raw.lower()

            # Check TIER 1 first
            for signal in EXPLOIT_CONFIRMED.get(vuln_type, []):
                if signal.lower() in search_text:
                    dom_signal   = True
                    vuln_signal  = True
                    triggered_by = signal
                    log.info(f"\u2705 EXPLOIT CONFIRMED — signal: '{signal}'")
                    break

            # Check TIER 2 (only if TIER 1 not found)
            if not dom_signal:
                for signal in VULN_DETECTED.get(vuln_type, []):
                    if signal.lower() in search_text:
                        vuln_signal  = True
                        triggered_by = f"[vuln_detected] {signal}"
                        log.info(f"\u26a0\ufe0f  Vulnerability detected (not full exploit): '{signal}'")
                        break

        except UnexpectedAlertPresentException:
            try:
                alert = self.driver.switch_to.alert
                alert.accept()
                dom_signal   = True
                vuln_signal  = True
                triggered_by = "alert_popup_unexpected"
            except Exception:
                pass
        except Exception as e:
            log.error(f"Error reading browser page: {e}")

        return {
            "status"      : 200,
            "dom_signal"  : dom_signal,
            "vuln_signal" : vuln_signal,
            "triggered_by": triggered_by,
            "raw_response": raw[:800],
            "response_len": len(raw),
        }


    # ── Subprocess (CLI_EXEC) ────────────────────────────────
    def _inject_subprocess(self, payload: str) -> dict:
        log.info(f"CLI_EXEC: {payload}")
        try:
            result = subprocess.run(
                payload, shell=True, capture_output=True,
                text=True, timeout=15
            )
            output = result.stdout + result.stderr
            return {
                "status"       : result.returncode,
                "dom_signal"   : "vulnerable" in output.lower() or "success" in output.lower(),
                "triggered_by" : "cli_output",
                "raw_response" : output[:500],
                "response_len" : len(output),
            }
        except subprocess.TimeoutExpired:
            log.error("CLI_EXEC timeout")
            return self._empty_obs()
        except Exception as e:
            log.error(f"CLI_EXEC error: {e}")
            return self._empty_obs()

    # ── Helpers ──────────────────────────────────────────────
    def _empty_obs(self) -> dict:
        return {
            "status"       : 0,
            "dom_signal"   : False,
            "triggered_by" : "",
            "raw_response" : "",
            "response_len" : 0,
        }

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
                log.info("Selenium WebDriver ditutup.")
            except Exception:
                pass
