# Panduan Konfigurasi & Troubleshooting Lingkungan (VM Kali Linux ke Host Windows)

Dokumen ini berisi rangkuman masalah (*troubleshooting*) yang terjadi selama proses konfigurasi agen AI pentesting agar dapat berjalan di dalam VM (Kali Linux) dan berkomunikasi dengan sistem di mesin utama/Host (Windows).

---

## 1. Topologi Eksperimen

- **Agen AI (Script Python)** berjalan di dalam **Kali Linux** (VirtualBox/VMware).
- **Target (DVWA)** berjalan di **Windows (Host)** via XAMPP.
- **Cognitive Engine (Ollama)** berjalan di **Windows (Host)** secara *native* memanfaatkan GPU/CPU.
- **Jembatan Jaringan**: Menggunakan IP `10.0.2.2` (Default Gateway NAT VirtualBox) dari Kali Linux untuk menjangkau Windows Host.

---

## 2. Riwayat Troubleshooting & Solusi

### A. Terminal Hang & Masalah Karakter (Unicode/Emoji)
- **Gejala**: Script Python *hang* (berhenti mengeksekusi) tanpa pesan error (*traceback*) saat *scout_environment* selesai atau tidak memunculkan log eksekusi secara berurutan.
- **Penyebab**: Terminal di VM (terutama bawaan Linux) tidak bisa melakukan *render* beberapa karakter UTF-8 khusus seperti emoji (`🌐`, `✅`, `⚠️`) atau karakter garis Unicode (`─`, `═`). Ini memicu `UnicodeEncodeError` tersembunyi pada sistem log Python.
- **Solusi**: 
  - Mengganti semua karakter garis Unicode menjadi ASCII biasa (`-` dan `=`).
  - Menghapus semua emoji pada baris kode dan merubahnya menjadi teks format tag biasa seperti `[Web]`, `[OK]`, `[WARN]`, `[ERR]`.

### B. `[Errno 111] Connection Refused` (Gagal ke DVWA)
- **Gejala**: WebDriver menampilkan `net::ERR_CONNECTION_REFUSED` ke alamat `http://localhost/dvwa/login.php`.
- **Penyebab**: Script menargetkan *localhost* di dalam Kali Linux, padahal DVWA berada di mesin Host (Windows). Hal ini terjadi karena variabel kontrol `RUNNING_IN_VM = False` secara tak sengaja kembali ke pengaturan aslinya setelah menjalankan `git pull`.
- **Solusi**: Pastikan variabel di file `orchestrator.py` diatur dengan benar setiap kali mengeksekusi di dalam VM:
  ```python
  RUNNING_IN_VM = True
  ```

### C. `404 Client Error` saat Memanggil Cognitive Engine
- **Gejala**: Request ke `http://10.0.2.2:11434/api/generate` ditolak dengan kode `404 Not Found`.
- **Penyebab 1 (Konflik Import)**: File `cognitive_engine.py` telanjur mendefinisikan *base URL* menggunakan string `localhost` secara statis *sebelum* `orchestrator.py` sempat mengubah *Environment Variable* `OLLAMA_HOST` menjadi `10.0.2.2`.
  - **Solusi**: Merombak class `CognitiveEngine` agar membaca URL secara **dinamis** pada saat eksekusi fungsi menggunakan fitur `@property` Python di `cognitive_engine.py`.
- **Penyebab 2 (Firewall Windows)**: Windows Defender secara ketat memblokir koneksi masuk (*inbound*) dari IP jaringan "luar" (VirtualBox) ke port 11434 yang digunakan Ollama.
  - **Solusi**: Mengizinkan *traffic* TCP ke port 11434 di Windows Host. Jalankan di *Command Prompt (Run as Administrator)*:
    ```cmd
    netsh advfirewall firewall add rule name="Ollama API" dir=in action=allow protocol=TCP localport=11434
    ```

### D. `500 Internal Server Error` dari Ollama
- **Gejala**: Cognitive Engine mendapati pesan *500 Server Error* sesaat setelah iterasi dimulai dan Ollama mulai berpikir.
- **Penyebab Asli (Ditelusuri via background testing)**: 
  `llama-server reported out-of-memory during startup... failed to allocate buffer of size 2355144704... error loading model: unable to allocate CUDA_Host buffer`
  Ini artinya mesin Host (Windows) kehabisan ketersediaan kapasitas RAM (VRAM) untuk memasukkan model *Qwen 2.5:7b* secara penuh. Aplikasi VirtualBox (VM Kali Linux) dan aplikasi Windows lainnya menyedot sisa kapasitas memori utama, menyebabkan Ollama *crash* (*Out-of-Memory*) saat menginisiasi komputasi lokal.
- **Solusi**:
  1. Bersihkan sisa memori di Windows dengan menutup paksa aplikasi berat, lalu *restart* Ollama.
  2. Atau ganti tipe model bahasa ke versi *parameter* yang lebih ringan (seperti `qwen2.5:3b` atau `qwen2.5:1.5b` atau `qwen2.5:0.5b`) pada baris variabel `OLLAMA_MODEL` di file `orchestrator.py`, pastikan juga model tersebut sudah diunduh menggunakan `ollama pull [nama model]`.
