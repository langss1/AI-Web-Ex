"""
=============================================================
MEMORY SYSTEM — RAG (ChromaDB) + PCB State Memory (JSON)
=============================================================
Two complementary layers:
  1. Static RAG   : OWASP strategy knowledge → ChromaDB vector store
  2. Dynamic PCB  : Per-session attack history in JSON
     Schema: { timestamp, target_endpoint, strategy_category,
               payload, context{previous_thought, analysis_summary},
               behavior{outcome, tool_used} }
=============================================================
"""

import json
import os
import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

PCB_FILE = "memory/pcb_state.json"

# ── RAG Knowledge Base ─────────────────────────────────────
# Conceptual descriptions — NOT raw payloads.
# The LLM must reason and construct payloads itself at runtime.
OWASP_KNOWLEDGE = [

    # ══════════════════ SQL INJECTION — LOW ══════════════════
    {
        "chunk_id": "sqli_low_auth_bypass_01",
        "source": "SQLi_Strategy_KB",
        "vulnerability_type": "sqli",
        "dvwa_level": "low",
        "strategy_category": "auth_bypass",
        "content": (
            "Kategori: Authentication/Logic Bypass (SQLi Low). "
            "Teknik ini memanipulasi kondisi WHERE pada query SQL dengan menyisipkan logika "
            "boolean yang selalu bernilai TRUE ke dalam parameter string. Karena DVWA Low "
            "tidak memfilter input, karakter single quote dapat langsung memutus konteks "
            "string asli, diikuti ekspresi OR 1=1 yang membuat kondisi WHERE selalu "
            "terpenuhi. Berguna untuk melewati validasi atau menampilkan semua baris tabel "
            "tanpa mengetahui nilai aslinya. Gunakan komentar SQL (-- atau #) untuk "
            "mengabaikan sisa query setelah injeksi."
        )
    },
    {
        "chunk_id": "sqli_low_union_01",
        "source": "SQLi_Strategy_KB",
        "vulnerability_type": "sqli",
        "dvwa_level": "low",
        "strategy_category": "union_based",
        "content": (
            "Kategori: Union-Based Extraction (SQLi Low). "
            "Menggabungkan query asli dengan SELECT tambahan menggunakan UNION untuk menarik "
            "data dari tabel lain (contoh: tabel users dengan kolom user dan password). "
            "Prasyarat: jumlah kolom pada SELECT tambahan harus sama dengan query asli. "
            "Cara mengetahui jumlah kolom: coba ORDER BY 1, ORDER BY 2, dst hingga error. "
            "Di DVWA Low, parameter tidak difilter sehingga karakter quote dapat dipakai "
            "bebas. Akhiri query dengan komentar -- atau # agar sisa query asli diabaikan."
        )
    },
    {
        "chunk_id": "sqli_low_error_based_01",
        "source": "SQLi_Strategy_KB",
        "vulnerability_type": "sqli",
        "dvwa_level": "low",
        "strategy_category": "error_based",
        "content": (
            "Kategori: Error-Based Extraction (SQLi Low). "
            "Memprovokasi database menghasilkan pesan error yang membocorkan informasi "
            "internal seperti versi, nama database, atau struktur tabel. Pada DVWA Low "
            "tidak ada filter sehingga karakter quote atau syntax tidak valid langsung "
            "memicu error. Pendekatan umum menggunakan fungsi MySQL yang mengembalikan error "
            "saat argumennya berisi ekspresi SQL yang tidak valid secara tipe data. "
            "Relevan dipakai ketika respons HTML memantulkan pesan error database secara langsung."
        )
    },
    {
        "chunk_id": "sqli_low_boolean_blind_01",
        "source": "SQLi_Strategy_KB",
        "vulnerability_type": "sqli",
        "dvwa_level": "low",
        "strategy_category": "boolean_blind",
        "content": (
            "Kategori: Boolean-Based Blind (SQLi Low). "
            "Dipakai saat aplikasi tidak memantulkan error SQL secara langsung, namun "
            "menunjukkan respons yang berbeda antara kondisi TRUE dan FALSE (contoh: "
            "halaman berisi data vs halaman kosong). Agen menyisipkan kondisi bersyarat "
            "ke parameter, lalu membandingkan respons untuk menyimpulkan kebenaran kondisi. "
            "Dengan mengulang secara sistematis, agen dapat mengekstrak data karakter "
            "per karakter tanpa melihat output langsung. Di DVWA Low, quote bebas dipakai."
        )
    },
    {
        "chunk_id": "sqli_low_time_blind_01",
        "source": "SQLi_Strategy_KB",
        "vulnerability_type": "sqli",
        "dvwa_level": "low",
        "strategy_category": "time_blind",
        "content": (
            "Kategori: Time-Based Blind (SQLi Low). "
            "Opsi terakhir ketika tidak ada perbedaan respons HTML sama sekali. "
            "Agen menyisipkan perintah delay kondisional seperti SLEEP(N) dalam IF() "
            "atau CASE WHEN. Jika kondisi benar, server menunda respons selama N detik; "
            "jika salah, respons langsung. Dengan mengukur waktu respons HTTP, agen "
            "dapat melakukan inferensi data. Di DVWA Low, quote bebas dipakai."
        )
    },

    # ══════════════════ SQL INJECTION — MEDIUM ══════════════════
    {
        "chunk_id": "sqli_medium_union_01",
        "source": "SQLi_Strategy_KB",
        "vulnerability_type": "sqli",
        "dvwa_level": "medium",
        "strategy_category": "union_based",
        "content": (
            "Kategori: Union-Based Numeric (SQLi Medium). "
            "DVWA Medium menggunakan mysql_real_escape_string() yang hanya meng-escape "
            "karakter quote. Input diberikan via dropdown angka, namun request dapat "
            "dimodifikasi langsung. Karena konteks query numerik (tidak diapit quote), "
            "injeksi UNION tanpa quote tetap bekerja. Pola: 1 UNION SELECT col1,col2 "
            "FROM tabel -- (tanpa quote). Deteksi jumlah kolom dahulu via ORDER BY."
        )
    },
    {
        "chunk_id": "sqli_medium_boolean_blind_01",
        "source": "SQLi_Strategy_KB",
        "vulnerability_type": "sqli",
        "dvwa_level": "medium",
        "strategy_category": "boolean_blind",
        "content": (
            "Kategori: Boolean-Based Blind Numeric (SQLi Medium). "
            "Pada parameter numerik, kondisi boolean dapat disisipkan tanpa quote: "
            "1 AND 1=1 (true) vs 1 AND 1=2 (false) menghasilkan halaman berbeda. "
            "mysql_real_escape_string() tidak mempengaruhi operator AND, angka, "
            "atau fungsi yang tidak memerlukan string literal."
        )
    },
    {
        "chunk_id": "sqli_medium_time_blind_01",
        "source": "SQLi_Strategy_KB",
        "vulnerability_type": "sqli",
        "dvwa_level": "medium",
        "strategy_category": "time_blind",
        "content": (
            "Kategori: Time-Based Blind Numeric (SQLi Medium). "
            "Filter mysql_real_escape_string() hanya memblokir quote, bukan karakter "
            "numerik atau kata kunci SQL. Pada konteks numerik, SLEEP() dan IF() "
            "dapat disisipkan tanpa quote. Pola: 1 AND IF(kondisi, SLEEP(3), 0) -- "
            "tidak mengandung quote sehingga lolos filter sepenuhnya."
        )
    },

    # ══════════════════ XSS — LOW ══════════════════
    {
        "chunk_id": "xss_low_reflected_01",
        "source": "XSS_Strategy_KB",
        "vulnerability_type": "xss",
        "dvwa_level": "low",
        "strategy_category": "reflected_basic",
        "content": (
            "Kategori: Reflected XSS Dasar (XSS Low). "
            "DVWA Low tidak memiliki filter apapun. Payload yang diinjeksi ke parameter "
            "GET langsung dipantulkan ke HTML respons tanpa sanitasi. Tag script standar "
            "adalah pendekatan pertama. Browser akan mengeksekusi JavaScript saat halaman "
            "dimuat. Indikator sukses: munculnya alert popup atau eksekusi JavaScript. "
            "Perhatikan konteks output (dalam atribut HTML atau langsung dalam body)."
        )
    },
    {
        "chunk_id": "xss_low_stored_01",
        "source": "XSS_Strategy_KB",
        "vulnerability_type": "xss",
        "dvwa_level": "low",
        "strategy_category": "stored_xss",
        "content": (
            "Kategori: Stored XSS (XSS Low). "
            "Payload disimpan secara persisten di database dan dieksekusi setiap kali "
            "halaman dimuat. Di DVWA Low, endpoint /vulnerabilities/xss_s/ adalah target "
            "Stored XSS. Tidak ada filter, sehingga payload script standar langsung berhasil. "
            "Indikator sukses: script tereksekusi saat halaman dimuat ulang."
        )
    },
    {
        "chunk_id": "xss_low_event_handler_01",
        "source": "XSS_Strategy_KB",
        "vulnerability_type": "xss",
        "dvwa_level": "low",
        "strategy_category": "event_handler_bypass",
        "content": (
            "Kategori: Event Handler Non-Script Tag (XSS Low). "
            "Alternatif tag script: menyisipkan JavaScript melalui atribut event handler "
            "HTML pada elemen lain. Contoh: tag gambar dengan src tidak valid memicu "
            "onerror, atau elemen dengan atribut onload atau onmouseover. "
            "Berguna sebagai variasi teknik dan untuk memahami konteks output HTML."
        )
    },

    # ══════════════════ XSS — MEDIUM ══════════════════
    {
        "chunk_id": "xss_medium_case_variation_01",
        "source": "XSS_Strategy_KB",
        "vulnerability_type": "xss",
        "dvwa_level": "medium",
        "strategy_category": "case_variation_bypass",
        "content": (
            "Kategori: Case-Variation Bypass (XSS Medium). "
            "DVWA Medium menghapus string script (huruf kecil persis) secara case-sensitive. "
            "Variasi kapitalisasi pada tag tidak cocok dengan pola filter sehingga lolos. "
            "Browser tetap menginterpretasikan tag dengan kapitalisasi apapun sebagai "
            "elemen script yang valid. Ini adalah pendekatan pertama yang harus dicoba "
            "di DVWA Medium sebelum beralih ke teknik lain."
        )
    },
    {
        "chunk_id": "xss_medium_event_handler_01",
        "source": "XSS_Strategy_KB",
        "vulnerability_type": "xss",
        "dvwa_level": "medium",
        "strategy_category": "event_handler_bypass",
        "content": (
            "Kategori: Non-Script Tag plus Event Handler (XSS Medium). "
            "Jika semua variasi tag script diblokir, gunakan elemen HTML lain yang "
            "mendukung atribut event handler: img dengan onerror, body dengan onload, "
            "svg dengan onload, a dengan onmouseover. "
            "Filter DVWA Medium hanya menarget string script literal, bukan atribut event "
            "pada elemen lain. JavaScript dalam atribut event tetap dieksekusi browser."
        )
    },
    {
        "chunk_id": "xss_medium_encoding_bypass_01",
        "source": "XSS_Strategy_KB",
        "vulnerability_type": "xss",
        "dvwa_level": "medium",
        "strategy_category": "encoding_bypass",
        "content": (
            "Kategori: Encoding-Based Bypass (XSS Medium). "
            "Menyandikan payload menggunakan HTML Entities atau URL encoding untuk "
            "menghindari pattern matching filter. Browser secara otomatis mendekode "
            "entities sebelum rendering sehingga payload tetap dieksekusi. "
            "Contoh: HTML entity encoding untuk karakter tag, atau memanfaatkan "
            "pseudo-protocol javascript dalam atribut href. Efektif ketika filter mencari "
            "pola string literal tanpa mendekode input terlebih dahulu."
        )
    },
]


class MemorySystem:
    def __init__(self):
        Path("memory").mkdir(exist_ok=True)
        self._pcb: dict = {}
        self._use_chromadb = False
        self._load_pcb()           # Restore PCB from disk on startup
        self._try_init_chromadb()

    # ── Load PCB from disk on startup ───────────────────────
    def _load_pcb(self):
        if os.path.exists(PCB_FILE):
            try:
                with open(PCB_FILE, "r", encoding="utf-8") as f:
                    self._pcb = json.load(f)
                log.info(f"PCB loaded from disk: {list(self._pcb.keys())}")
            except Exception as e:
                log.warning(f"Could not load PCB file: {e} — starting fresh.")
                self._pcb = {}
        else:
            self._pcb = {}

    # ── ChromaDB (optional, graceful fallback) ──────────────
    def _try_init_chromadb(self):
        try:
            import chromadb
            from chromadb.utils import embedding_functions

            self._chroma_client = chromadb.PersistentClient(path="memory/chromadb")
            ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2"
            )
            self._collection = self._chroma_client.get_or_create_collection(
                name="owasp_knowledge_v2",
                embedding_function=ef
            )
            if self._collection.count() == 0:
                self._populate_chromadb()
            self._use_chromadb = True
            log.info(f"[OK] ChromaDB initialized — RAG enabled ({self._collection.count()} chunks)")

        except ImportError:
            log.warning("[WARN]  chromadb/sentence-transformers not installed.")
            log.warning("   Falling back to keyword-based retrieval.")
            log.warning("   Install: pip install chromadb sentence-transformers")
        except Exception as e:
            log.warning(f"[WARN]  ChromaDB init failed: {e} — using keyword fallback.")

    def _populate_chromadb(self):
        """Embed only the 'content' field of each chunk (not the full JSON object)."""
        docs, ids, metas = [], [], []
        for item in OWASP_KNOWLEDGE:
            docs.append(item["content"])
            ids.append(item["chunk_id"])
            metas.append({
                "vuln_type"         : item["vulnerability_type"],
                "strategy_category" : item["strategy_category"],
                "dvwa_level"        : item["dvwa_level"],
            })
        self._collection.add(documents=docs, ids=ids, metadatas=metas)
        log.info(f"RAG: Populated ChromaDB with {len(docs)} knowledge chunks.")

    # ── Public: Retrieve RAG context ────────────────────────
    def retrieve(self, vuln_type: str, n_results: int = 4) -> str:
        if self._use_chromadb:
            try:
                query = f"{vuln_type} injection bypass technique DVWA exploitation"
                results = self._collection.query(
                    query_texts=[query],
                    n_results=n_results,
                    where={"vuln_type": vuln_type}
                )
                docs  = results.get("documents", [[]])[0]
                metas = results.get("metadatas", [[]])[0]
                if docs:
                    chunks = []
                    for doc, meta in zip(docs, metas):
                        chunks.append(
                            f"[Strategy: {meta.get('strategy_category','?')} | "
                            f"Level: {meta.get('dvwa_level','?')}]\n{doc}"
                        )
                    return "\n\n---\n\n".join(chunks)
            except Exception as e:
                log.warning(f"ChromaDB query failed: {e}")

        # Fallback: return all matching static knowledge with labels
        fallback = []
        for item in OWASP_KNOWLEDGE:
            if item["vulnerability_type"] == vuln_type:
                fallback.append(
                    f"[Strategy: {item['strategy_category']} | "
                    f"Level: {item['dvwa_level']}]\n{item['content']}"
                )
        return "\n\n---\n\n".join(fallback) if fallback else "No knowledge available."

    # ── Public: PCB State Memory ─────────────────────────────
    def reset_pcb(self, vuln_type: str):
        self._pcb[vuln_type] = []
        self._save_pcb()
        log.info(f"PCB reset for: {vuln_type}")

    def add_pcb(
        self,
        vuln_type: str,
        payload: str,
        context: str,
        behavior: str,
        strategy_category: str = "unknown",
        analysis_summary: str = "",
        tool_used: str = "http_requests",
        target_endpoint: str = ""
    ):
        """
        Record one attack attempt with full PCB schema.
        behavior: 'success' | 'failed' | 'blocked'
        """
        entry = {
            "timestamp"         : datetime.now().isoformat(),
            "target_endpoint"   : target_endpoint,
            "strategy_category" : strategy_category,
            "payload"           : payload,
            "context"           : {
                "previous_thought" : context[:500],
                "analysis_summary" : analysis_summary[:300],
            },
            "behavior"          : {
                "outcome"   : behavior,
                "tool_used" : tool_used,
            }
        }
        if vuln_type not in self._pcb:
            self._pcb[vuln_type] = []
        self._pcb[vuln_type].append(entry)
        self._save_pcb()
        log.debug(f"PCB [{vuln_type}] recorded: strategy={strategy_category} | outcome={behavior}")

    def get_pcb(self, vuln_type: str) -> list:
        return self._pcb.get(vuln_type, [])

    def get_all_payloads(self, vuln_type: str) -> list:
        return [e["payload"] for e in self.get_pcb(vuln_type)]

    def get_pcb_summary_for_prompt(self, vuln_type: str) -> str:
        """
        Rich PCB history for LLM prompt: strategy, tool, outcome, AND analysis per iteration.
        """
        history = self.get_pcb(vuln_type)
        if not history:
            return "  (no history yet — this is the first attempt)"

        lines = []
        for i, entry in enumerate(history, 1):
            outcome  = entry.get("behavior", {}).get("outcome", "?")
            strategy = entry.get("strategy_category", "?")
            tool     = entry.get("behavior", {}).get("tool_used", "?")
            payload  = entry.get("payload", "?")
            summary  = entry.get("context", {}).get("analysis_summary", "")
            lines.append(
                f"  [{i}] strategy={strategy} | tool={tool} | outcome={outcome}\n"
                f"      payload: {payload[:80]}\n"
                f"      analysis: {summary}"
            )
        return "\n".join(lines)

    def _save_pcb(self):
        with open(PCB_FILE, "w", encoding="utf-8") as f:
            json.dump(self._pcb, f, indent=2, ensure_ascii=False)
