# AGENT.md — Autonomous Web Pentesting Agent (Qwen 2.5:7B + RAG)
## Context File for AI Coding Agent Onboarding — Gilang Wasis Wicaksono (103032300130)

> Setiap sesi AI baru harus membaca dokumen ini terlebih dahulu sebelum menyentuh kode apapun.
> Status implementasi terakhir diverifikasi: **18 Juni 2026** — semua modul berjalan, seluruh fitur aktif.

---

## ✅ CHECKLIST FITUR — STATUS IMPLEMENTASI

| # | Fitur | File | Status |
|---|-------|------|--------|
| 1 | **Multi-strategi eksploitasi** (5 SQLi + 5 XSS, bukan 1 cara) | `guardrail.py`, `memory_system.py` | ✅ Done |
| 2 | **RAG knowledge base** 14 chunk konseptual (SQLi Low+Med, XSS Low+Med) | `memory_system.py` | ✅ Done |
| 3 | **PCB schema lengkap** (`timestamp`, `strategy_category`, `analysis_summary`, `tool_used`) | `memory_system.py` | ✅ Done |
| 4 | **PCB load dari disk** saat startup — histori tidak hilang antar sesi | `memory_system.py` | ✅ Done |
| 5 | **PCB history lengkap di prompt** (strategy, outcome, analysis per iterasi) | `orchestrator.py` | ✅ Done |
| 6 | **Guardrail anti-duplikat payload** | `guardrail.py` | ✅ Done |
| 7 | **Guardrail anti-stagnasi strategi** (blokir jika 3x gagal kategori sama) | `guardrail.py` | ✅ Done |
| 8 | **Environment Scout** (auto-login HTTP + set cookie + Selenium login) sebelum loop | `action_layer.py`, `orchestrator.py` | ✅ Done |
| 9 | **Prompt 4 sumber knowledge** (ENV Profile, RAG, PCB History, Untried Strategies) | `orchestrator.py` | ✅ Done |
| 10 | **Action Layer HTTP_INJECT** — `requests` backend (default, cepat) | `action_layer.py` | ✅ Done |
| 11 | **Action Layer SELENIUM_INJECT** — Selenium WebDriver FE/GUI (konfirmasi XSS alert) | `action_layer.py` | ✅ Done |
| 12 | **Action Layer CLI_EXEC** — `subprocess` backend (external tools) | `action_layer.py` | ✅ Done |
| 13 | **Cognitive Engine** parse `action_type` + `strategy_category` dari LLM JSON | `cognitive_engine.py` | ✅ Done |
| 14 | **Stopping Criteria** — Success Trigger ATAU Hard Limit 10 iterasi | `orchestrator.py` | ✅ Done |
| 15 | **Selenium WebDriver** — ChromeDriver, alert detection, DOM parsing | `action_layer.py` | ✅ Done |
| 16 | **ChromaDB** dengan fallback keyword jika tidak terinstall | `memory_system.py` | ✅ Done |

---

## 🎯 KONTEKS PROYEK

**Judul TA:** Pengembangan Agen Otonom Berbasis Local LLM Qwen 2.5:7B dengan Integrasi RAG untuk Otomatisasi Pengujian Penetrasi Web

**Penulis:** Gilang Wasis Wicaksono — NIM 103032300130
**Institusi:** S1 Teknologi Informasi, Fakultas Informatika, Universitas Telkom

---

## 🏗️ ARSITEKTUR SISTEM (IMPLEMENTASI AKTIF)

```
orchestrator.py         ← Core controller + Environment Scout (run_all)
├── cognitive_engine.py ← Qwen 2.5:7B via Ollama, parse JSON (thought/payload/action_type/strategy_category)
├── memory_system.py    ← RAG (ChromaDB 14 chunk) + PCB State Memory (JSON schema lengkap)
├── guardrail.py        ← Anti-Looping: duplikat payload + stagnasi strategi (3x)
└── action_layer.py     ← Hybrid: HTTP Requests | Selenium WebDriver | Subprocess
```

**Alur satu sesi (LENGKAP):**

```
run_all()
│
├─ [SEKALI] scout_environment()
│    ├─ HTTP GET login → ambil CSRF token
│    ├─ HTTP POST login → dapat PHPSESSID
│    ├─ Set cookie security=low/medium
│    ├─ Selenium login (untuk session browser)
│    └─ Return environment_profile { level, modules, form_context }
│
└─ [LOOP per skenario: sqli, xss]
     run_scenario(vuln_type, url)
     │
     ├─ [Iterasi 1..HARD_LIMIT]
     │    ├─ 1. memory.retrieve(vuln_type)           → RAG chunks
     │    ├─ 1. memory.get_pcb(vuln_type)            → PCB history list
     │    ├─ 1. guardrail.get_untried_strategies()   → strategi belum dicoba
     │    ├─ 2. _build_prompt(4 sumber knowledge)    → prompt lengkap
     │    ├─ 3. cognitive_engine.reason(prompt)      → {thought, payload, action_type, strategy_category, finish}
     │    ├─ 4. if finish == True → STOP (SUCCESS)
     │    ├─ 5. guardrail.is_blocked(payload, strategy_category)
     │    │    ├─ is_duplicate? → blokir, add_pcb(blocked), continue
     │    │    └─ stagnasi 3x? → blokir, add_pcb(blocked), continue
     │    ├─ 6. action.execute(action_type, url, vuln_type, payload)
     │    │    ├─ HTTP_INJECT   → requests.get/post + BeautifulSoup
     │    │    ├─ SELENIUM_INJECT → driver.get + alert detection
     │    │    └─ CLI_EXEC      → subprocess.run(payload)
     │    ├─ 7. cek dom_signal → if True: SUCCESS, break
     │    └─ 8. memory.add_pcb(... strategy_category, analysis_summary, tool_used ...)
     │
     └─ Save result → logs/results.json
```

---

## 💻 ENVIRONMENT

| Komponen | Detail |
|---|---|
| OS | Windows (native, tanpa VM) |
| LLM | Ollama local + `qwen2.5:7b` |
| Target | DVWA di `localhost/dvwa` (Docker/XAMPP) |
| Python | 3.11+ |
| Key libs | `requests`, `beautifulsoup4`, `selenium`, `chromadb`, `sentence-transformers` |
| Ollama endpoint | `http://localhost:11434/api/generate` |

---

## 📁 STRUKTUR FILE

```
AI Web Ex/
├── orchestrator.py      ✅ — core loop + env scout + prompt builder 4-source
├── cognitive_engine.py  ✅ — Ollama/Qwen wrapper, parse action_type & strategy_category
├── memory_system.py     ✅ — ChromaDB RAG 14 chunk + PCB schema lengkap + _load_pcb startup
├── guardrail.py         ✅ — anti-duplikat payload + anti-stagnasi strategi
├── action_layer.py      ✅ — Hybrid: HTTP | Selenium | Subprocess + scout_environment
├── check_system.py      ✅ — system health check
├── setup_windows.bat    ✅ — Windows setup script
├── requirements.txt     ✅
├── AGENT (2).md         ✅ — dokumen ini (context file terbaru)
├── AGENT_revised.md     ✅ — dokumen arsitektur lengkap
├── memory/
│   ├── pcb_state.json   ← PCB history (persisten antar sesi)
│   └── chromadb/        ← vector store (auto-create)
└── logs/
    ├── run_YYYYMMDD_HHMMSS.log
    └── results.json
```

---

## 🗂️ RAG KNOWLEDGE BASE — 14 CHUNK AKTIF

### SQL Injection (8 chunk)

| chunk_id | Level | Strategy |
|---|---|---|
| `sqli_low_auth_bypass_01` | Low | `auth_bypass` |
| `sqli_low_union_01` | Low | `union_based` |
| `sqli_low_error_based_01` | Low | `error_based` |
| `sqli_low_boolean_blind_01` | Low | `boolean_blind` |
| `sqli_low_time_blind_01` | Low | `time_blind` |
| `sqli_medium_union_01` | Medium | `union_based` |
| `sqli_medium_boolean_blind_01` | Medium | `boolean_blind` |
| `sqli_medium_time_blind_01` | Medium | `time_blind` |

### Cross-Site Scripting (6 chunk)

| chunk_id | Level | Strategy |
|---|---|---|
| `xss_low_reflected_01` | Low | `reflected_basic` |
| `xss_low_stored_01` | Low | `stored_xss` |
| `xss_low_event_handler_01` | Low | `event_handler_bypass` |
| `xss_medium_case_variation_01` | Medium | `case_variation_bypass` |
| `xss_medium_event_handler_01` | Medium | `event_handler_bypass` |
| `xss_medium_encoding_bypass_01` | Medium | `encoding_bypass` |

> **Catatan desain:** Chunk RAG sengaja berisi **konsep & kapan-dipakai**, bukan payload siap tembak — agar Cognitive Engine tetap bernalar menyusun payload sendiri.

---

## 📋 PCB SCHEMA (FORMAT AKTIF)

```json
{
  "sqli": [
    {
      "timestamp"         : "2026-06-18T12:00:00.000000",
      "target_endpoint"   : "http://localhost/dvwa/vulnerabilities/sqli/",
      "strategy_category" : "union_based",
      "payload"           : "' UNION SELECT 1,2-- -",
      "context": {
        "previous_thought" : "Mencoba union-based karena auth_bypass gagal. Query numerik...",
        "analysis_summary" : "Page returned user data. Signal: First name detected."
      },
      "behavior": {
        "outcome"   : "success",
        "tool_used" : "http_requests"
      }
    }
  ]
}
```

**Field wajib:** `timestamp`, `target_endpoint`, `strategy_category`, `payload`, `context.previous_thought`, `context.analysis_summary`, `behavior.outcome`, `behavior.tool_used`

---

## 🛡️ GUARDRAIL — DUA LAPIS

### Lapis 1: Anti-Duplikat Payload
- Cek apakah payload (normalized lowercase) sudah ada di PCB history
- Jika ya → blokir, catat sebagai `blocked`, paksa iterasi ulang

### Lapis 2: Anti-Stagnasi Strategi
- Cek 3 entri PCB terakhir: jika semua `strategy_category` sama DAN semua `outcome` = `failed`/`blocked`
- Jika ya → blokir strategi itu, sertakan `untried_strategies` ke prompt berikutnya
- Menu strategi SQLi: `union_based`, `error_based`, `boolean_blind`, `time_blind`, `auth_bypass`
- Menu strategi XSS: `reflected_basic`, `stored_xss`, `event_handler_bypass`, `case_variation_bypass`, `encoding_bypass`

---

## 🤖 ACTION LAYER — HYBRID 3 KOMPONEN

| `action_type` | Module | Kapan Dipakai |
|---|---|---|
| `HTTP_INJECT` | `requests` + `BeautifulSoup` | Default untuk semua SQLi dan XSS backend |
| `SELENIUM_INJECT` | Selenium WebDriver (Chrome) | Saat perlu konfirmasi `alert()` popup XSS secara visual |
| `CLI_EXEC` | `subprocess.run()` | Saat LLM ingin jalankan external tool (curl, sqlmap) |

**Cognitive Engine memilih** `action_type` — bukan hardcoded. Orchestrator me-route ke komponen yang tepat.

---

## 🔍 ENVIRONMENT SCOUT (sebelum loop dimulai)

Dijalankan **sekali** di `run_all()` sebelum iterasi ReAct pertama:

1. HTTP GET ke login page → ambil CSRF `user_token`
2. HTTP POST login → dapat cookie `PHPSESSID`
3. Set cookie `security=low/medium` pada HTTP session
4. Selenium login → untuk sesi browser (SELENIUM_INJECT)
5. Return **Environment Profile**:
```python
{
    "dvwa_security_level": "low",
    "available_modules": ["sqli", "xss_r", "sqli_blind", "xss_s"],
    "current_form_context": "Target parameters: id for sqli, name for xss"
}
```

---

## 🧠 PROMPT COGNITIVE ENGINE — 4 SUMBER KNOWLEDGE

```
[SOURCE 1] ENVIRONMENT PROFILE (dari recon)
→ level, modules, form parameters

[SOURCE 2] SECURITY KNOWLEDGE — RAG (OWASP + Strategy KB)
→ top-k chunks dari ChromaDB, berlabel strategy + level

[SOURCE 3] ATTACK HISTORY — PCB State Memory
→ setiap entri: strategy, tool, outcome, analysis (bukan cuma payload mentah)

[SOURCE 4] UNTRIED STRATEGIES
→ daftar strategi yang belum pernah dicoba pada sesi ini
```

**Output JSON wajib dari LLM:**
```json
{
  "thought": "reasoning lengkap kenapa strategi X dipilih...",
  "payload": "injection_string",
  "action_type": "HTTP_INJECT",
  "strategy_category": "union_based",
  "finish": false
}
```

---

## 🎯 TARGET PENGUJIAN & SUCCESS SIGNALS

| Skenario | URL | Success Signal |
|---|---|---|
| SQLi Low | `/dvwa/vulnerabilities/sqli/` | "First name", "admin", "gordonb" di DOM |
| SQLi Medium | Same URL + `security=medium` cookie | "First name", UNION data di DOM |
| XSS Low | `/dvwa/vulnerabilities/xss_r/` | Alert popup terpicu (Selenium) |
| XSS Medium | Same URL + `security=medium` | `onerror=`, `onload=` event di DOM |

---

## 📊 METRIK EVALUASI (logs/results.json)

```json
[
  {
    "vuln_type"  : "sqli",
    "security"   : "low",
    "success"    : true,
    "iterations" : 3,
    "elapsed_s"  : 47.2
  }
]
```

Dipakai untuk **Bab IV (Hasil dan Analisis)** — Success Rate, Jumlah Iterasi, Waktu Eksekusi.

---

## 🐛 COMMON ISSUES & FIX

| Issue | Penyebab | Fix |
|---|---|---|
| `ConnectionError` Ollama | Ollama tidak jalan | `ollama serve` di terminal lain |
| `ConnectionError` DVWA | DVWA belum start | `docker run -d -p 80:80 vulnerables/web-dvwa` |
| JSON parse error Qwen | Reply dengan markdown | `_parse_response()` sudah handle, cek `_fallback_extract()` |
| ChromaDB error Windows | Missing C++ build tools | `pip install chromadb --no-build-isolation` atau biarkan keyword fallback |
| Login DVWA gagal | CSRF token berubah | Cek `scout_environment()` di `action_layer.py` |
| Semua payload gagal | Security level salah | Set `DVWA_SECURITY = "low"` di `orchestrator.py` |
| Selenium tidak start | ChromeDriver tidak ada | `pip install webdriver-manager` atau download ChromeDriver manual |
| PCB tidak ke-load | File corrupt | Hapus `memory/pcb_state.json`, sistem buat baru otomatis |

---

## ⚠️ CONSTRAINT YANG TIDAK BOLEH DIUBAH

1. **Model harus Qwen 2.5:7B via Ollama** — jangan ganti ke API eksternal
2. **Target hanya DVWA localhost** — ethical testing only
3. **Nama file/class tidak boleh berubah** — semua module di-import by name
4. **Hard limit tetap 10 iterasi** per skenario
5. **Orchestrator adalah satu-satunya hub** — modul lain tidak boleh saling komunikasi langsung

---

## 🚀 CARA RUN

```bash
# 1. Ollama
ollama serve
# (terminal lain)
ollama pull qwen2.5:7b

# 2. DVWA
docker run -d -p 80:80 vulnerables/web-dvwa

# 3. Cek sistem
cd "AI Web Ex"
python check_system.py

# 4. Jalankan agent
python orchestrator.py
```

---

## 📝 CATATAN UNTUK CODING AGENT

- Semua file ada di **satu folder flat** (`AI Web Ex/`)
- `memory/` dan `logs/` dibuat otomatis saat runtime
- PCB **persisten antar sesi** — tidak di-reset kecuali `memory.reset_pcb()` dipanggil
- Log tersimpan di `logs/run_YYYYMMDD_HHMMSS.log`
- Debug LLM: set `logging.basicConfig(level=logging.DEBUG)` di `orchestrator.py`
- Jika edit RAG: tambah chunk ke `OWASP_KNOWLEDGE` di `memory_system.py`, hapus `memory/chromadb/` agar repopulate
- Referensi: Gilang Wasis Wicaksono, Tugas Akhir Universitas Telkom 2026
