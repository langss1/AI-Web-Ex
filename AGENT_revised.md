# AGENT.md — Autonomous Web Pentesting Agent (Qwen 2.5:7B + RAG)

> Dokumen ini adalah context file utama untuk proyek Tugas Akhir Gilang Wasis Wicaksono (103032300130, Fakultas Informatika, Universitas Telkom). Tujuannya adalah memberi LLM/AI agent lain pemahaman penuh tentang tujuan riset, arsitektur sistem, status implementasi, dan konvensi kerja — sehingga setiap sesi AI baru tidak perlu re-discovery dari nol dan tetap konsisten dengan sesi-sesi sebelumnya.
>
> **Revisi terbaru:** menambahkan (1) menu multi-strategi eksploitasi SQLi & XSS agar Cognitive Engine tidak terpaku satu pendekatan, (2) konten RAG knowledge base konkret + prompt generator untuk membangunnya, (3) fase Environment Scout/Recon sebelum loop ReAct dimulai dengan dukungan auto-login, (4) penegasan format PCB pada Orchestrator & Guardrail Check termasuk ringkasan analisis/respons sebelumnya, (5) Action Layer hybrid: HTTP Requests (backend), Selenium WebDriver (FE/GUI), Subprocess (backend CLI), dan (6) penyesuaian batasan masalah serta lingkungan eksekusi *native*.

---

## 0. Metadata

| Field | Value |
|---|---|
| Judul (ID) | Pengembangan Agen Otonom Berbasis Large Language Model Lokal Qwen 2.5:7b dengan Integrasi Retrieval-Augmented Generation untuk Otomatisasi Pengujian Penetrasi Web |
| Judul (EN) | Development of Autonomous Agent Based on Local Large Language Model with Retrieval-Augmented Generation Integration for Web Penetration Testing Automation |
| Penulis | Gilang Wasis Wicaksono — NIM 103032300130 |
| Program Studi | S1 Teknologi Informasi, Fakultas Informatika, Universitas Telkom, Bandung |
| Calon Pembimbing 1 | Assoc. Prof. Dr. Vera Suryani, S.T., M.T. (NIP 03790039) |
| Status Proposal | Disetujui 22 Mei 2026 |
| Status Implementasi | MVP inti berjalan secara *native* pada mesin lokal (Windows/Linux) menggunakan Ollama. Target: recon phase, multi-strategi, RAG konkret, Action Layer hybrid — lihat §15. |
| Target Akhir | Skripsi lengkap Bab 1–5, eksperimen kuantitatif pada DVWA Low & Medium |

---

## 1. Ringkasan Masalah & Tujuan Penelitian

**Masalah inti:** Solusi pentesting berbasis LLM yang ada (PentestGPT, dkk.) masih *human-in-the-loop* atau, ketika dibuat otonom, sering terjebak *looping eksploitasi* karena hilangnya memori kontekstual. Solusi berbasis LLM komersial juga membawa risiko privasi data target.

**Rumusan masalah:** (a) arsitektur agen otonom berbasis Local LLM Qwen untuk pentest web; (b) implementasi RAG + State Memory sebagai Anti-Looping Guardrail; (c) evaluasi keberhasilan & kinerja agen pada DVWA.

**Tujuan:** merancang arsitektur agen kognitif otonom lokal; mengimplementasikan RAG + State Memory JSON sebagai guardrail anti-looping; mengevaluasi success rate, efisiensi iterasi, dan konsumsi resource pada DVWA.

**Kebaruan:** privasi penuh (LLM lokal), eliminasi *summarizer agent* via State Memory JSON berskema PCB, Anti-Looping Guardrail berbasis skrip Python, **dan** kemampuan agen mempertimbangkan beragam strategi eksploitasi (bukan satu jalur tunggal) — lihat §5.

---

## 2. Lingkup & Batasan (Scope)

- Target eksklusif: **DVWA** di *localhost* (diisolasi dalam *Localhost* / *Container Docker* tanpa perlu full OS VM).
- Cognitive Engine: **Qwen 2.5 (7B)** via **Ollama**.
- Vektor serangan: **SQL Injection** dan **Cross-Site Scripting (XSS)**, sesuai OWASP Top 10.
- Metrik: Success Rate, jumlah iterasi sampai Stopping Criteria, konsumsi CPU/RAM.
- **Batasan Masalah RAG (Direvisi):** Sistem RAG dibatasi pada penggunaan dokumentasi resmi kerentanan OWASP **serta basis pengetahuan pola strategi eksploitasi yang didefinisikan secara khusus untuk lingkungan pengujian** (lihat §7).

---

## 3. Arsitektur Sistem (High-Level, Closed-Loop)

```
                ┌──────────────────────┐
                │  Environment Scout     │  (jalan sekali di awal sesi)
                │  Auto-login DVWA,      │
                │  Set security cookie,  │
                │  Recon: forms, fields, │
                │  modul yang tersedia   │
                └───────────┬────────────┘
                             │ environment_profile
                             ▼
            ┌───────────────┐
   Start ──▶│  Orchestrator  │──▶ Finish ──▶ End
            └───────┬───────┘
     Query/context  │  Action command + strategy_category
        ▲            ▼
┌────────────────┐  ┌──────────────────────┐
│ Cognitive Engine │  │     Memory System      │
│ (Qwen 2.5 7B)    │  │ RAG + PCB History +     │
│ + Strategy Menu  │  │ Ringkasan Respons Lalu   │
└────────────────┘  └──────────────────────┘
                       │ JSON (PCB, termasuk strategy_category)
                       ▼
        ┌─────────────────────────────────────────┐
        │                Action Layer                │
        │  ┌───────────┐ ┌───────────┐ ┌──────────┐ │
        │  │ HTTP Req   │ │ Selenium    │ │ Subprocess│ │
        │  │ (backend)  │ │ WebDriver   │ │ (backend  │ │
        │  │            │ │ (FE/GUI)    │ │  CLI)     │ │
        │  └───────────┘ └───────────┘ └──────────┘ │
        └─────────────────────┬─────────────────────┘
                               │ HTTP/DOM/CLI
                               ▼
                        ┌────────────┐
                        │Target(DVWA)│
                        └────────────┘
                               │ Response/observation
                               ▼ (kembali ke Orchestrator → update PCB)
```

Lima elemen utama (Orchestrator tetap satu-satunya hub komunikasi):

0. **Environment Scout** — recon awal dan login, sekali per sesi (§4.0).
1. **Orchestrator (Python)** — core controller, event loop.
2. **Cognitive Engine** — Qwen 2.5:7B via Ollama, ReAct + Strategy Menu.
3. **Memory System** — RAG (static, ChromaDB lokal) + State Memory PCB (dynamic, termasuk histori analisis/respons).
4. **Action Layer** — tiga sub-modul: HTTP Requests, Selenium WebDriver, Subprocess.

---

## 4. Spesifikasi Modul

### 4.0 Environment Scout / Recon (berjalan sebelum loop utama)

Dijalankan **satu kali** di awal sesi, sebelum iterasi ReAct pertama:

1. **Auto-Login & Security Setup**: Melakukan request GET untuk mengambil token CSRF login, kemudian melakukan POST request ke `/login.php` untuk mendapatkan sesi (`PHPSESSID`). Selanjutnya, memanipulasi cookie (misal `security=low` atau `security=medium`) untuk menetapkan level kesulitan aktif pada target.
2. Enumerasi modul kerentanan yang tersedia (`/vulnerabilities/sqli/`, `/vulnerabilities/sqli_blind/`, `/vulnerabilities/xss_r/`, `/vulnerabilities/xss_s/`, dst.).
3. Parsing tiap halaman target dengan BeautifulSoup: temukan form, nama field input, method (GET/POST), keberadaan token CSRF.
4. Susun **Environment Profile** (skema §6.3) → simpan dan jadikan bagian dari konteks awal yang disuntikkan ke prompt pertama Cognitive Engine.

**Tujuan:** Cognitive Engine tidak "buta" di iterasi pertama dan request tidak diblokir oleh halaman login.

### 4.1 Orchestrator

**Alur per sesi:**
0. (Sekali di awal) Jalankan **Environment Scout** → simpan Environment Profile.
1. Setiap iterasi: ambil konteks gabungan — Environment Profile + retrieval RAG relevan + **State Memory PCB History lengkap** (termasuk `analysis_summary`) → kirim ke Cognitive Engine.
2. Terima output: Thought + Action + `strategy_category`.
3. Cek **Stopping Criteria** — jika `Action == FINISH` → END.
4. Jika Action = eksploitasi → **Guardrail Check** (dua lapis):
   - a. Cocokkan string payload dengan historis (anti-duplikat).
   - b. Cocokkan `strategy_category` dengan kategori yang gagal berulang (anti-stagnasi).
   - Jika diblokir → kembalikan pesan error dan daftar strategi yang belum dicoba; ulangi loop.
   - Jika aman → teruskan ke Action Layer.
5. Terima Observation dari target.
6. **Update State Memory JSON (PCB)**.
7. Ulangi loop.

### 4.2 Cognitive Engine (ReAct + Strategy Menu)

Murni otak penalaran. Setiap prompt menggabungkan 4 sumber pengetahuan:
1. RAG retrieval
2. PCB History (beserta ringkasan)
3. Environment Profile
4. Strategy Menu

**Instruksi Pemilihan Tool Action Layer (Prompting Rule):**
- **HTTP_INJECT:** Gunakan ini untuk iterasi eksploitasi cepat backend (Submit form langsung). Ini adalah mode default.
- **SELENIUM_INJECT:** Gunakan HANYA jika Anda perlu mengonfirmasi popup `alert()` XSS di layar HTML, atau jika interaksi membutuhkan alur DOM JavaScript penuh.
- **CLI_EXEC:** Gunakan ini jika Anda menginstruksikan penggunaan alat eksternal lokal (contoh: `sqlmap`, `nikto`).

### 4.3 Memory System

**a. RAG (static long-term):** Menggunakan `ChromaDB` dipadukan dengan **model embedding lokal** (`nomic-embed-text` via Ollama atau `all-MiniLM-L6-v2` via HuggingFace) demi menjaga privasi penuh tanpa bergantung API eksternal (NFR1).
**b. State Memory (dynamic short-term):** JSON berformat PCB.
**c. Anti-Looping Guardrail:** Skrip Python untuk mengecek payload dan stagnasi strategi.

### 4.4 Action Layer (Hybrid: 3 Komponen)

| Komponen | Lapisan | Kapan dipakai |
|---|---|---|
| **HTTP Requests Module** (`requests` + `BeautifulSoup`) | Backend | Pengujian form/parameter langsung (cepat, tanpa browser overhead). Default untuk mayoritas pengujian. |
| **Selenium WebDriver** (Headless Chromium) | Frontend / GUI | Saat butuh rendering nyata: konfirmasi visual XSS (`alert()`), interaksi GUI multi-step, atau bypass proteksi browser-side. |
| **Subprocess Module** (`subprocess.run()`) | Backend / CLI | Tools eksternal pendukung (sqlmap, curl). |

---

## 5. Strategi Multi-Pendekatan Eksploitasi

### 5.1 SQL Injection — Menu Strategi
**DVWA Level Low (tanpa filter):**
- **Authentication/Logic Bypass** — manipulasi logika boolean pada parameter string.
- **Union-Based Extraction** — menggabungkan query tambahan.
- **Error-Based Extraction** — memicu pesan error database.
- **Boolean-Based Blind** — membandingkan respons true/false.
- **Time-Based Blind** — memanfaatkan delay (SLEEP/WAITFOR).

**DVWA Level Medium (parameter numerik via dropdown, filter escape):**
- **Union-Based tanpa quote** pada parameter numerik.
- **Encoding-based bypass** (double URL-encoding).
- **Time-based blind** tidak bergantung pada karakter quote.

### 5.2 Cross-Site Scripting (XSS) — Menu Strategi
**DVWA Level Low (tanpa filter):**
- **Reflected XSS dasar**
- **Stored XSS**
- **Event-Handler / Non-Script Tag**

**DVWA Level Medium (tag `<script>` distrip case-sensitive):**
- **Case-Variation Bypass**
- **Non-Script Tag + Event Handler** (gambar/SVG/body)
- **Encoding-Based Bypass**

---

## 6. Skema Data

### 6.1 PCB Schema (JSON)
```json
{
  "session_id": "string",
  "iteration": 0,
  "timestamp": "ISO-8601",
  "vulnerability_type": "SQLi | XSS",
  "dvwa_level": "low | medium",
  "target_endpoint": "string",
  "strategy_category": "string (lihat §5)",
  "payload": {
    "value": "string",
    "http_method": "GET | POST",
    "form_field": "string"
  },
  "context": {
    "previous_thought": "string",
    "analysis_summary": "string",
    "rag_snippets_used": ["string"],
    "guardrail_status": "passed | blocked_duplicate_payload | blocked_stagnant_strategy"
  },
  "behavior": {
    "tool_used": "http_requests | selenium | subprocess",
    "http_status": 200,
    "response_snippet": "string",
    "dom_change_detected": false,
    "outcome": "success | fail | blocked"
  }
}
```

### 6.2 RAG Document Chunk Schema (ChromaDB)
```json
{
  "chunk_id": "string",
  "source": "string",
  "vulnerability_type": "SQLi | XSS",
  "dvwa_level": "low | medium | both",
  "strategy_category": "string",
  "content": "string (konseptual)",
  "embedding": "[float, ...]"
}
```

---

## 7. RAG Knowledge Base — Konten Konkret

Berikut adalah *knowledge chunks* yang fokus pada konsep (bukan hardcoded payload), agar Cognitive Engine tetap bernalar menyusun payload sendiri:

### 7.1 Chunk SQLi - Error-Based (Low)
```json
{
  "chunk_id": "sqli_low_error_based_01",
  "source": "SQLi_Strategy_KB",
  "vulnerability_type": "SQLi",
  "dvwa_level": "low",
  "strategy_category": "error_based",
  "content": "Kategori: Error-Based Extraction. Teknik ini memprovokasi database untuk menghasilkan pesan error yang membocorkan informasi struktur database, versi, atau data internal. Relevan digunakan ketika respons aplikasi memantulkan pesan error SQL mentah ke layar HTML. Pada DVWA Low, karena tidak ada filter, karakter khusus seperti single quote (') atau syntax yang tidak valid dapat disisipkan langsung. Pendekatan umumnya adalah menggunakan fungsi matematika/XML yang rentan error (misal extractvalue() atau updatexml() pada MySQL) dengan argumen yang dievaluasi dari query SELECT target."
}
```

### 7.2 Chunk SQLi - Time-Based Blind (Medium / Low)
```json
{
  "chunk_id": "sqli_both_time_blind_01",
  "source": "SQLi_Strategy_KB",
  "vulnerability_type": "SQLi",
  "dvwa_level": "both",
  "strategy_category": "time_blind",
  "content": "Kategori: Time-Based Blind. Digunakan sebagai opsi terakhir ketika aplikasi sama sekali tidak memantulkan perubahan di UI (baik pesan error maupun perbedaan layout/boolean) setelah injeksi. Agen menyisipkan perintah delay eksekusi seperti SLEEP() yang bergantung pada kondisi logika bersyarat (IF atau CASE). Jika kondisi benar, server akan menunda respons HTTP selama sekian detik. Teknik ini sangat efektif di DVWA Medium pada parameter numerik, karena payload dapat dikonstruksi tanpa menggunakan karakter single quote (') sehingga lolos dari filter mysql_real_escape_string()."
}
```

### 7.3 Chunk XSS - Event-Handler Bypass (Low / Medium)
```json
{
  "chunk_id": "xss_both_event_handler_01",
  "source": "XSS_Strategy_KB",
  "vulnerability_type": "XSS",
  "dvwa_level": "both",
  "strategy_category": "event_handler_bypass",
  "content": "Kategori: Event-Handler / Non-Script Tag. Teknik injeksi XSS yang diimplementasikan ketika tag <script> standar dihapus atau diblokir oleh filter aplikasi (misalnya pencarian case-sensitive di DVWA Medium). Payload JavaScript dieksekusi melalui atribut event handler bawaan HTML (seperti onerror, onload, onmouseover) yang disematkan pada tag alternatif seperti <img>, <body>, atau <svg>. Contoh fundamental: menyuntikkan tag gambar dengan source yang tidak valid (src='x') untuk secara otomatis memicu atribut onerror yang mengeksekusi JavaScript."
}
```

### 7.4 Chunk XSS - Encoding-Based Bypass (Medium)
```json
{
  "chunk_id": "xss_medium_encoding_bypass_01",
  "source": "XSS_Strategy_KB",
  "vulnerability_type": "XSS",
  "dvwa_level": "medium",
  "strategy_category": "encoding_bypass",
  "content": "Kategori: Encoding-Based Bypass. Digunakan untuk menghindari pattern matching dari WAF atau filter backend (seperti pada DVWA Medium). Bypass dilakukan dengan menyandikan payload JavaScript menggunakan representasi HTML Entities (misal &#x3C; untuk karakter <) atau Unicode escape sequences. Payload yang disandikan ini disisipkan ke dalam konteks atribut HTML yang secara otomatis akan di-decode oleh browser sebelum dieksekusi, seperti atribut 'href' pada tag <a> yang dipadukan dengan pseudo-protocol 'javascript:'. Teknik ini mungkin membutuhkan interaksi dari entitas target (klik)."
}
```

### 7.5 Prompt Template — Generator Konten RAG
```text
Anda adalah knowledge engineer untuk basis pengetahuan RAG sebuah agen
pentesting otonom yang menyasar DVWA (Damn Vulnerable Web Application)
untuk tujuan riset akademik yang sah.

Buatkan SATU chunk pengetahuan baru dengan kriteria:
- vulnerability_type: {SQLi | XSS}
- dvwa_level: {low | medium}
- strategy_category: {pilih satu dari menu strategi §5 yang belum ada chunk-nya}

Format output WAJIB JSON sesuai schema:
{
  "chunk_id": "...",
  "source": "...",
  "vulnerability_type": "...",
  "dvwa_level": "...",
  "strategy_category": "...",
  "content": "..."
}

Isi 'content' harus: (1) menjelaskan PRINSIP teknik secara konseptual,
(2) menjelaskan KAPAN teknik ini relevan dipakai, (3) TIDAK perlu payload
string yang spesifik/siap-pakai — cukup deskripsi pola/struktur agar
Cognitive Engine tetap bernalar saat runtime.
```

---

## 8. Alur Kerja End-to-End (Pseudocode)
```python
def run_agent(target_url, max_iteration=10):
    env_profile = orchestrator.scout_environment(target_url)   # §4.0
    state = StateMemory.load_or_init(session_id)

    for i in range(max_iteration):
        pcb_history = state.get_full_history()  # termasuk analysis_summary
        rag_chunks = rag.retrieve_top_k(env_profile.current_form_context)
        untried_strategies = guardrail.get_untried_strategies(pcb_history)

        prompt = build_react_prompt(
            env_profile, rag_chunks, pcb_history, untried_strategies
        )

        thought, action, strategy_category = cognitive_engine.infer(prompt)

        if action.type == "FINISH":
            break

        if guardrail.is_blocked(action.payload, strategy_category, pcb_history):
            orchestrator.notify_blocked(action.payload, untried_strategies)
            continue

        tool = orchestrator.select_action_layer(action)  # http | selenium | subprocess
        observation = action_layer.execute(action, tool=tool)

        state.append_pcb(
            payload=action.payload,
            strategy_category=strategy_category,
            context=thought,
            analysis_summary=summarize(thought, observation),
            behavior=observation,
        )

    return state.summary()
```

---

## 9. Isu Terpecahkan dan Penyesuaian Lingkungan

- **Lingkungan Eksekusi**: Dikonfirmasi dijalankan secara *native* pada mesin lokal host (Windows/Linux) tanpa harus ke VM Kali Linux. LLM tetap lokal (Ollama) dan Embedding RAG dijalankan lokal (`nomic-embed-text` atau sejenisnya) untuk patuh terhadap privasi (NFR1). Target DVWA berjalan di Docker/XAMPP lokal.
- **Integrasi Action Layer Hybrid**: Solusi yang lebih fleksibel, di mana agen dapat dinamis memilih HTTP/Selenium/Subprocess via prompt.
- **Login Sesi DVWA**: Scout Phase dirancang untuk melakukan auto-login dan konfigurasi `security` cookie agar loop tidak gagal prematur.
