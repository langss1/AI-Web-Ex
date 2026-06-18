"""
=============================================================
AUTONOMOUS WEB PENTESTING AGENT - ORCHESTRATOR
=============================================================
Tugas Akhir: Gilang Wasis Wicaksono (103032300130)
Universitas Telkom - Fakultas Informatika

Architecture:
  Orchestrator -> Cognitive Engine (Qwen 2.5 via Ollama)
               -> Memory System (RAG + PCB State Memory JSON)
               -> Anti-Looping Guardrail
               -> Action Layer (Selenium WebDriver — ALL actions)
  Target: DVWA (localhost)

Metrics tracked (for paper Bab IV):
  - Success Rate per scenario
  - Jumlah Iterasi (efficiency)
  - Stopping Criteria (Success Trigger / Hard Limit)
  - Resource Consumption (CPU %, RAM MB) via psutil
=============================================================
"""

import json
import time
import logging
import os
import threading
from datetime import datetime
from cognitive_engine import CognitiveEngine
from memory_system import MemorySystem
from guardrail import AntiLoopingGuardrail
from action_layer import ActionLayer

# Optional: resource monitoring
try:
    import psutil
    PSUTIL_OK = True
except ImportError:
    PSUTIL_OK = False

os.makedirs("logs", exist_ok=True)

# ── Logging setup ───────────────────────────────────────────
RUN_TIMESTAMP = datetime.now().strftime('%Y%m%d_%H%M%S')
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(f"logs/run_{RUN_TIMESTAMP}.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ── Network & Environment Config ────────────────────────────
# Set ke True JIKA menjalankan script ini di dalam VM (Kali Linux) 
# dan menargetkan DVWA & Ollama yang berjalan di Windows.
# Set ke False JIKA menjalankan script ini langsung di Windows.
RUNNING_IN_VM = False

if RUNNING_IN_VM:
    HOST_IP = "10.0.2.2"  # IP NAT bawaan VirtualBox untuk Host (Windows)
else:
    HOST_IP = "localhost"

# Paksa cognitive_engine.py untuk membaca IP ini
os.environ["OLLAMA_HOST"] = HOST_IP

# ── Config ──────────────────────────────────────────────────
DVWA_BASE       = f"http://{HOST_IP}/dvwa"
DVWA_LOGIN_URL  = f"{DVWA_BASE}/login.php"
DVWA_SQLI_URL   = f"{DVWA_BASE}/vulnerabilities/sqli/"
DVWA_XSS_URL    = f"{DVWA_BASE}/vulnerabilities/xss_r/"
OLLAMA_MODEL    = "qwen2.5"
MAX_ITER        = 10          # max iterations per scenario
DVWA_SECURITY   = "low"       # "low" | "medium" | "impossible"
SUCCESS_PAUSE_S = 20          # seconds to pause in browser after confirmed success


# ── Resource Monitor ────────────────────────────────────────
class ResourceMonitor:
    """Background thread: sample CPU & RAM every second."""
    def __init__(self):
        self.cpu_samples  = []
        self.ram_samples  = []
        self._running     = False
        self._thread      = None
        self._proc        = psutil.Process() if PSUTIL_OK else None

    def start(self):
        if not PSUTIL_OK:
            return
        self._running = True
        self._thread  = threading.Thread(target=self._sample, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _sample(self):
        while self._running:
            try:
                self.cpu_samples.append(psutil.cpu_percent(interval=None))
                self.ram_samples.append(psutil.virtual_memory().used / (1024 ** 2))
            except Exception:
                pass
            time.sleep(1)

    def summary(self) -> dict:
        if not self.cpu_samples:
            return {"cpu_avg_%": "N/A", "cpu_peak_%": "N/A",
                    "ram_avg_mb": "N/A", "ram_peak_mb": "N/A"}
        return {
            "cpu_avg_%"  : round(sum(self.cpu_samples) / len(self.cpu_samples), 1),
            "cpu_peak_%"  : round(max(self.cpu_samples), 1),
            "ram_avg_mb" : round(sum(self.ram_samples) / len(self.ram_samples), 1),
            "ram_peak_mb": round(max(self.ram_samples), 1),
        }


class Orchestrator:
    def __init__(self):
        log.info("=" * 60)
        log.info("AUTONOMOUS WEB PENTESTING AGENT — STARTING")
        log.info("=" * 60)

        self.cognitive  = CognitiveEngine(model=OLLAMA_MODEL)
        self.memory     = MemorySystem()
        self.guardrail  = AntiLoopingGuardrail(self.memory)
        self.action     = ActionLayer(base_url=DVWA_BASE)

        self.results     = []
        self.env_profile = None
        self.res_monitor = ResourceMonitor()

    # ── Main run loop ────────────────────────────────────────
    def run_scenario(self, vuln_type: str, target_url: str):
        log.info(f"\n{'-'*50}")
        log.info(f"SCENARIO: {vuln_type.upper()} | Security: {DVWA_SECURITY.upper()}")
        log.info(f"Target: {target_url}")
        log.info(f"{'-'*50}")

        self.memory.reset_pcb(vuln_type)
        iteration        = 0
        success          = False
        success_count    = 0     # how many distinct payloads succeeded
        success_payloads = []    # list of all successful payloads found
        stopping_criteria = "hard_limit"
        start_time       = time.time()

        # Navigate Selenium browser to target page immediately
        if self.action.driver:
            try:
                log.info(f"🌐 Browser navigating to: {target_url}")
                self.action.driver.get(target_url)
                time.sleep(0.5)
            except Exception as e:
                log.warning(f"Browser pre-navigation skipped: {e}")

        while iteration < MAX_ITER:
            iteration += 1
            log.info(f"\n[Iter {iteration}] {'-'*25}")

            # ── Build context for this iteration ──────────────
            rag_context        = self.memory.retrieve(vuln_type)
            pcb_history        = self.memory.get_pcb(vuln_type)
            untried_strategies = self.guardrail.get_untried_strategies(vuln_type)

            # If all strategies tried + at least 1 success → stop exploring
            if not untried_strategies and success:
                log.info("✅ All strategies explored and at least 1 success found. Stopping.")
                stopping_criteria = "all_strategies_explored"
                break

            prompt = self._build_prompt(
                vuln_type, target_url, rag_context,
                pcb_history, untried_strategies, self.env_profile
            )

            # 2. Cognitive Engine
            log.info("Calling Cognitive Engine...")
            response = self.cognitive.reason(prompt)
            log.info(f"THOUGHT   : {response.get('thought', '—')}")
            log.info(f"ACTION    : {response.get('payload', '—')} [{response.get('action_type', 'HTTP_INJECT')}]")
            log.info(f"STRATEGY  : {response.get('strategy_category', '—')}")
            log.info(f"CONTINUE? : {response.get('should_continue', True)} — {response.get('continue_reason', '')}")
            log.info(f"FINISH    : {response.get('finish', False)}")

            # 3. AI decides to stop
            if not response.get("should_continue", True):
                reason = response.get("continue_reason", "AI decided no further iterations needed.")
                log.info(f"⏹️  AI stopped iteration: {reason}")
                stopping_criteria = "ai_decided_stop"
                break

            # 4. Check legacy FINISH flag
            if response.get("finish") and success:
                log.info("✅ Agent declared FINISH after exploration.")
                stopping_criteria = "agent_finish"
                break

            payload           = response.get("payload", "")
            action_type       = response.get("action_type", "HTTP_INJECT")
            strategy_category = response.get("strategy_category", "unknown")

            if not payload:
                log.warning("No payload extracted — skipping iteration.")
                continue

            # 4. Guardrail check
            if self.guardrail.is_blocked(vuln_type, payload, strategy_category):
                log.warning("⛔ GUARDRAIL BLOCKED. Forcing new strategy.")
                self.memory.add_pcb(
                    vuln_type, payload, response.get("thought", ""),
                    "blocked", strategy_category,
                    "Blocked by guardrail", action_type, target_url
                )
                continue

            # 5. Execute via Action Layer (ALL actions → browser)
            log.info(f"Executing payload: {payload} via {action_type}")
            obs = self.action.execute(action_type, target_url, vuln_type, payload)
            log.info(f"Observation: {obs['status']} | DOM signal: {obs.get('dom_signal', False)}")

            # 6. Record PCB
            # Use vuln_signal for behavior: if any vulnerability indicator found,
            # record as 'vuln_detected'; only 'success' if real exploit confirmed.
            vuln_signal = obs.get("vuln_signal", False)
            if obs["dom_signal"]:
                behavior = "success"
            elif vuln_signal:
                behavior = "vuln_detected"   # error visible → useful for AI reasoning
            else:
                behavior = "failed"

            analysis_summary = (
                f"Status: {obs['status']}. "
                f"Exploit confirmed: {obs['dom_signal']}. "
                f"Vuln detected: {vuln_signal}. "
                f"Signal: {obs['triggered_by'] or 'none'}."
            )
            self.memory.add_pcb(
                vuln_type, payload, response.get("thought", ""),
                behavior, strategy_category, analysis_summary,
                action_type, target_url
            )

            # 7. Handle success
            if obs["dom_signal"]:
                success_count += 1
                success_payloads.append({
                    "iteration"    : iteration,
                    "strategy"     : strategy_category,
                    "payload"      : payload,
                    "triggered_by" : obs["triggered_by"],
                })
                if not success:
                    success           = True
                    stopping_criteria = "success_trigger"
                    log.info(f"\u2705 DOM signal detected \u2014 exploitation confirmed! (case #{success_count})")
                    self._pause(SUCCESS_PAUSE_S)
                    log.info("\u25b6\ufe0f  Continuing to explore more attack strategies...")
                else:
                    log.info(f"\u2705 Additional success found (case #{success_count}): {strategy_category}")
                    self._pause(SUCCESS_PAUSE_S)

        elapsed = time.time() - start_time
        result = {
            "vuln_type"        : vuln_type,
            "security"         : DVWA_SECURITY,
            "success"          : success,
            "success_count"    : success_count,
            "success_payloads" : success_payloads,
            "iterations"       : iteration,
            "elapsed_s"        : round(elapsed, 2),
            "stopping_criteria": stopping_criteria,
        }
        self.results.append(result)
        self._log_result(result)
        return result

    # ── Safe pause (countdown, terminal only, no browser touch) ──
    def _pause(self, seconds: int):
        """
        Pause for N seconds. Browser stays frozen on current result page.
        Countdown shown in terminal every 5s. No browser interaction.
        """
        log.info(f"\u23f8  Pausing {seconds}s \u2014 browser stays on result page. Watching...")
        for remaining in range(seconds, 0, -1):
            try:
                time.sleep(1)
                if remaining % 5 == 0 or remaining == 1:
                    log.info(f"   ... {remaining}s remaining")
            except KeyboardInterrupt:
                log.info("Pause skipped by user (Ctrl+C caught, continuing...)")
                break
            except Exception:
                break

    def _build_prompt(self, vuln_type, target_url, rag_context,
                      pcb_history, untried_strategies, env_profile):
        pcb_summary = self.memory.get_pcb_summary_for_prompt(vuln_type)

        failed_payloads = [
            e["payload"] for e in pcb_history
            if e.get("behavior", {}).get("outcome", "") in ("failed", "blocked")
        ]
        success_payloads = [
            e["payload"] for e in pcb_history
            if e.get("behavior", {}).get("outcome", "") == "success"
        ]

        failed_str  = "\n".join(f"  - {p}" for p in failed_payloads)  or "  (none yet)"
        success_str = "\n".join(f"  ✅ {p}" for p in success_payloads) or "  (none yet)"
        env_str     = json.dumps(env_profile, indent=2) if env_profile else "{}"
        untried_str = ", ".join(untried_strategies) if untried_strategies else "all strategies already attempted"

        return f"""You are an autonomous ethical web penetration testing agent (ReAct framework).
Your current task: exploit the [{vuln_type.upper()}] vulnerability at: {target_url}
Security level: {DVWA_SECURITY.upper()}

You have access to 4 knowledge sources below. Use ALL of them before deciding your next action.

════════════════════════════════════════
[SOURCE 1] ENVIRONMENT PROFILE (from recon)
════════════════════════════════════════
{env_str}

════════════════════════════════════════
[SOURCE 2] SECURITY KNOWLEDGE — RAG (OWASP + Strategy KB)
════════════════════════════════════════
{rag_context}

════════════════════════════════════════
[SOURCE 3] ATTACK HISTORY — PCB State Memory
(each entry: strategy used, tool used, outcome, agent analysis)
════════════════════════════════════════
{pcb_summary}

════════════════════════════════════════
[SOURCE 4] UNTRIED STRATEGIES (try these next)
════════════════════════════════════════
{untried_str}

════════════════════════════════════════
ALREADY SUCCEEDED WITH THESE PAYLOADS:
════════════════════════════════════════
{success_str}

════════════════════════════════════════
FAILED PAYLOADS — DO NOT REPEAT ANY:
════════════════════════════════════════
{failed_str}

════════════════════════════════════════
INSTRUCTIONS:
════════════════════════════════════════
1. THOUGHT: Analyze all sources. Explain WHY previous attempts failed/succeeded and WHY your new strategy will work.
2. ACTION_TYPE — choose one:
   - "HTTP_INJECT"     → default (uses browser via Selenium)
   - "SELENIUM_INJECT" → same as HTTP_INJECT (uses browser)
   - "CLI_EXEC"        → external CLI tool (payload = shell command)
3. STRATEGY_CATEGORY — pick from untried strategies above.
4. PAYLOAD: construct ONE new injection string not in any list above.
5. FINISH: set true ONLY if all untried strategies are exhausted.

CRITICAL RULES:
- Never repeat any payload from failed OR succeeded lists.
- Always try a strategy from the UNTRIED list.
- Even after success, continue exploring untried strategies.
- For {vuln_type} at {DVWA_SECURITY} level, adapt to known filter behavior.

════════════════════════════════════════
DVWA TECHNICAL FACTS (you MUST follow these exactly):
════════════════════════════════════════
For SQLi:
- The original DVWA query is: SELECT first_name, last_name FROM users WHERE user_id='$id'
- UNION payloads MUST select EXACTLY 2 columns, no more, no less.
  CORRECT:   1' UNION SELECT user, password FROM users-- -
  WRONG:     1' UNION SELECT 1,2,3-- (3 columns — will always error)
  WRONG:     1' UNION SELECT version()-- (1 column — will always error)
- MySQL/MariaDB comment syntax: use '-- -' (dash dash SPACE dash) OR '#'.
  CORRECT:   1' UNION SELECT user, password FROM users-- -
  CORRECT:   1' UNION SELECT user, password FROM users#
  WRONG:     anything ending in just '--' without space+dash after it
- Verified working payload (use as template): 1' UNION SELECT user, password FROM users-- -
For XSS:
- Target URL param is 'name'. Payload is reflected directly in HTML.
- Basic working payload: <script>alert('XSS')</script>
- If basic fails, try event handlers: <img src=x onerror=alert(1)>

Respond ONLY in this exact JSON format (no markdown, no extra text):
{{
  "thought": "your detailed reasoning about why previous attempts succeeded/failed and what to try next",
  "payload": "your_injection_string_here",
  "action_type": "HTTP_INJECT",
  "strategy_category": "chosen_strategy_name",
  "should_continue": true,
  "continue_reason": "brief reason why further iterations are or aren't needed",
  "finish": false
}}

For should_continue:
  Set to FALSE if:
    - All untried strategies have been attempted
    - The last 3+ iterations all produced the same error with no new information
    - You have fully confirmed exploitation and there is nothing new to try
  Set to TRUE if:
    - There are still untried strategies to explore
    - You believe a different payload variation could succeed
    - The vulnerability shows partial signals worth pursuing further
"""

    def _log_result(self, result):
        status = "✅ SUCCESS" if result["success"] else "❌ FAILED"
        log.info(f"\n{'='*50}")
        log.info(f"RESULT: {status}")
        log.info(f"  Vuln              : {result['vuln_type'].upper()}")
        log.info(f"  Security          : {result['security'].upper()}")
        log.info(f"  Iterations used   : {result['iterations']}/{MAX_ITER}")
        log.info(f"  Successful cases  : {result['success_count']}")
        log.info(f"  Stopping criteria : {result['stopping_criteria']}")
        log.info(f"  Elapsed time      : {result['elapsed_s']}s")
        if result["success_payloads"]:
            log.info(f"  Successful payloads found:")
            for sp in result["success_payloads"]:
                log.info(f"    [Iter {sp['iteration']}] {sp['strategy']} → {sp['payload'][:60]}")
        log.info(f"{'='*50}\n")

    # ── Entry point ──────────────────────────────────────────
    def run_all(self):
        self.res_monitor.start()
        overall_start = time.time()

        log.info("Running scout environment...")
        self.env_profile = self.action.scout_environment(DVWA_LOGIN_URL, DVWA_SECURITY)

        scenarios = [
            ("sqli", DVWA_SQLI_URL),
            ("xss",  DVWA_XSS_URL),
        ]
        for vuln_type, url in scenarios:
            self.run_scenario(vuln_type, url)

        overall_elapsed = time.time() - overall_start
        self.res_monitor.stop()
        resource_data   = self.res_monitor.summary()

        # -- Final summary ------------------------------------
        log.info("\n" + "=" * 60)
        log.info("ALL SCENARIOS COMPLETE — SUMMARY")
        log.info("=" * 60)
        for r in self.results:
            status = "✅" if r["success"] else "❌"
            log.info(
                f"  {status} {r['vuln_type'].upper():5} | {r['security'].upper():6} | "
                f"Iters: {r['iterations']:2}/{MAX_ITER} | "
                f"Cases: {r['success_count']} | "
                f"Stop: {r['stopping_criteria']} | "
                f"Time: {r['elapsed_s']}s"
            )

        total_scenarios = len(self.results)
        success_count   = sum(1 for r in self.results if r["success"])
        success_rate    = round((success_count / total_scenarios) * 100, 1) if total_scenarios else 0

        log.info(f"\n  Success Rate : {success_rate}% ({success_count}/{total_scenarios})")
        log.info(f"  Total Time   : {round(overall_elapsed, 2)}s")
        log.info(f"  CPU avg/peak : {resource_data.get('cpu_avg_%')}% / {resource_data.get('cpu_peak_%')}%")
        log.info(f"  RAM avg/peak : {resource_data.get('ram_avg_mb')} MB / {resource_data.get('ram_peak_mb')} MB")

        # ── Save results JSON ────────────────────────────────
        results_data = {
            "run_timestamp"   : RUN_TIMESTAMP,
            "dvwa_security"   : DVWA_SECURITY,
            "hard_limit"      : MAX_ITER,
            "overall_elapsed_s": round(overall_elapsed, 2),
            "success_rate_%"  : success_rate,
            "resource"        : resource_data,
            "scenarios"       : self.results,
        }
        results_path = f"logs/results_{RUN_TIMESTAMP}.json"
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump(results_data, f, indent=2, ensure_ascii=False)
        log.info(f"Results saved to {results_path}")

        # ── Generate paper report ────────────────────────────
        self._generate_report(results_data, overall_elapsed, resource_data)

        self.action.close()

    # ── Report generator ─────────────────────────────────────
    def _generate_report(self, results_data: dict, overall_elapsed: float, resource: dict):
        report_path = f"logs/report_{RUN_TIMESTAMP}.txt"
        lines = []
        lines.append("=" * 72)
        lines.append("LAPORAN EVALUASI — AGEN OTONOM PENGUJIAN PENETRASI WEB")
        lines.append("Tugas Akhir: Gilang Wasis Wicaksono (103032300130)")
        lines.append("Universitas Telkom — Fakultas Informatika")
        lines.append(f"Tanggal Run : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Model LLM   : Qwen 2.5:7B via Ollama (local)")
        lines.append(f"Target      : DVWA localhost | Security: {DVWA_SECURITY.upper()}")
        lines.append("=" * 72)
        lines.append("")

        # Metrik per skenario
        lines.append("─" * 72)
        lines.append("TABEL HASIL PER SKENARIO")
        lines.append("─" * 72)
        header = f"{'Vuln':8} {'Level':8} {'Sukses':8} {'Cases':6} {'Iterasi':10} {'Stop Criteria':25} {'Waktu(s)':10}"
        lines.append(header)
        lines.append("─" * 72)
        for r in results_data["scenarios"]:
            status = "YES" if r["success"] else "NO"
            row = (
                f"{r['vuln_type'].upper():8} "
                f"{r['security'].upper():8} "
                f"{status:8} "
                f"{r['success_count']:6} "
                f"{r['iterations']:2}/{MAX_ITER:<7} "
                f"{r['stopping_criteria']:25} "
                f"{r['elapsed_s']:10}"
            )
            lines.append(row)
        lines.append("─" * 72)
        lines.append("")

        # Payload sukses
        for r in results_data["scenarios"]:
            if r["success_payloads"]:
                lines.append(f"[{r['vuln_type'].upper()}] Payload yang Berhasil:")
                for sp in r["success_payloads"]:
                    lines.append(
                        f"  Iter {sp['iteration']:2} | Strategi: {sp['strategy']:25} "
                        f"| Signal: {sp['triggered_by']}"
                    )
                    lines.append(f"  Payload: {sp['payload']}")
                    lines.append("")

        # Metrik agregat
        lines.append("-" * 72)
        lines.append("METRIK EVALUASI (sesuai parameter paper)")
        lines.append("-" * 72)

        total     = len(results_data["scenarios"])
        successes = sum(1 for r in results_data["scenarios"] if r["success"])
        total_cases = sum(r["success_count"] for r in results_data["scenarios"])
        avg_iters = (
            sum(r["iterations"] for r in results_data["scenarios"]) / total
            if total else 0
        )

        lines.append(f"1. Success Rate         : {results_data['success_rate_%']}%  ({successes}/{total} skenario)")
        lines.append(f"   Total payload sukses  : {total_cases} payload (lintas strategi)")
        lines.append(f"2. Rata-rata Iterasi     : {avg_iters:.1f} iterasi per skenario (dari maks {MAX_ITER})")
        lines.append(f"3. Total Waktu Eksekusi  : {overall_elapsed:.2f} detik")
        lines.append(f"4. Stopping Criteria:")
        for r in results_data["scenarios"]:
            lines.append(
                f"   - {r['vuln_type'].upper():5}: {r['stopping_criteria']}"
            )
        lines.append(f"5. Resource Consumption  :")
        lines.append(f"   CPU rata-rata  : {resource.get('cpu_avg_%')} %")
        lines.append(f"   CPU puncak     : {resource.get('cpu_peak_%')} %")
        lines.append(f"   RAM rata-rata  : {resource.get('ram_avg_mb')} MB")
        lines.append(f"   RAM puncak     : {resource.get('ram_peak_mb')} MB")
        lines.append("")
        lines.append("-" * 72)
        lines.append("KETERANGAN STOPPING CRITERIA")
        lines.append("-" * 72)
        lines.append("  success_trigger          : Eksploitasi berhasil dikonfirmasi (DOM signal)")
        lines.append("  all_strategies_explored  : Semua strategi telah dicoba (minimal 1 sukses)")
        lines.append("  hard_limit               : Batas maksimal iterasi tercapai tanpa sukses")
        lines.append("  agent_finish             : Agen mendeklarasikan selesai (finish=true)")
        lines.append("")
        lines.append("=" * 72)
        lines.append("END OF REPORT")
        lines.append("=" * 72)

        report_text = "\n".join(lines)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_text)

        log.info(f"\n📄 Report saved to: {report_path}")
        log.info("\n" + report_text)


if __name__ == "__main__":
    agent = Orchestrator()
    try:
        agent.run_all()
    except KeyboardInterrupt:
        log.info("\nPentest dibatalkan oleh pengguna.")
        agent.res_monitor.stop()
        agent.action.close()
