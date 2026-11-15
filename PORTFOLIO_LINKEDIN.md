# 🚀 LinkedIn Portfolio Write-Up & Showcase Guide

Dokumen ini berisi draft materi postingan LinkedIn siap pakai dalam 2 versi bahasa (**Bahasa Indonesia** & **English**) yang dirancang khusus untuk memamerkan *technical depth*, *systems engineering*, dan inovasi di bidang **AI Developer Experience (DevEx) & Autonomous Agents Infrastructure**.

---

## 📌 Pilihan 1: Versi Bahasa Indonesia (Rekomendasi untuk Tech Community ID)

### Judul / Hook:
**Pernah ngalamin AI Coding Agent tiba-tiba macet kena Limit 429 di tengah refactoring kompleks? 😤**

---

### Copy Postingan:

Satu masalah terbesar saat bekerja dengan Autonomous AI Agents (seperti Antigravity di Orca ADE) pada codebase besar adalah **Rate Limits (HTTP 429 / RESOURCE_EXHAUSTED)**. 

Di saat agen lagi fokus mikir, generate ratusan baris kode, atau menjalankan multi-agent DAG... tiba-tiba kuota habis, sesi terputus, dan momentum kerja langsung buyar. Harus ganti akun manual via terminal, buka keyring, lalu ngetik ulang instruksi dari awal.

Untuk menyelesaikan friksi ini, saya merancang dan membangun:
🛠️ **Orca ADE Antigravity Auto-Switcher** — Sistem failover otomatis nir-henti (*zero-downtime*) dan reactive account rotator yang menggabungkan **Linux Systemd User Daemon** + **Official Orca ADE Plugin v2**.

---

### 🧠 Apa yang terjadi di balik layarnya? (Engineering Highlights)

1. **Dual-Engine Failure Detection:**
   Bukan cuma polling berkala yang boros resource. Sistem mengombinasikan *line-buffered streaming log watcher* pada trace NDJSON Orca dengan proaktif *IPC quota health probe*. Begitu pattern rate limit terdeteksi atau kuota menyentuh 100%, sistem langsung bereaksi secara instan.

2. **Automated Terminal Session Rehydration:**
   Ganti akun saja tidak cukup jika agen berhenti bekerja. Rotator ini mendeteksi PTY terminal aktif yang terhubung, menerapkan jeda *settle delay* (2 detik) agar OS keyring tersimpan stabil, lalu menyuntikkan trigger otomatis (`lanjutkan pengerjaan tadi`) sehingga agen langsung melanjutkan eksekusi tugasnya tanpa kehilangan konteks percakapan!

3. **Circuit Breaker & Anti-Ban Protection:**
   Mencegah pergantian berulang-ulang dengan mekanisme safety berlapis:
   - Cooldown period 30 detik antar rotasi.
   - Sliding-window circuit breaker: jika terjadi > 5 kali pergantian dalam 3 menit, rotasi otomatis ditahan untuk melindungi akun dari pemblokiran API Google/Orca.
   - Single-instance PID lockfile & native Linux desktop notifications (`notify-send`).

4. **Native Orca Plugin v2 & Real-time TUI:**
   Dilengkapi panel sidebar responsif berbasis CSS variables bawaan Orca (`var(--orca-*)`) dengan filosofi *Zero AI Slop* (bersih, densitas tinggi, tanpa emoji berlebih). Plus, ada mode **Privacy Masking** agar data sensitif / email terlindungi saat live streaming atau presentasi.

---

### 💡 Dampak & Hasil:
- ⚡ **100% Autonomous Failover:** Alur kerja agen AI dapat berjalan berjam-jam tanpa perlu intervensi manual saat satu akun mencapai kuota.
- 🎯 **Zero Context Loss:** Sesi agen langsung resume tanpa merusak terminal buffer.
- 🧪 **7/7 Passing Unit Tests:** Seluruh skenario edge case (all exhausted, round-robin, rate limit regex, circuit breaker) tervalidasi secara otomatis.

Source code, arsitektur, dan panduan instalasi lengkap sudah tersedia di GitHub:
👉 https://github.com/syharipf/orca-antigravity-rotator

Bagaimana teman-teman menangani rate limiting pada workflow autonomous agent kalian? Let's discuss in the comments! 👇

---

### Hashtags:
#SoftwareEngineering #AIEngineering #DeveloperTools #Linux #Python #DevOps #SystemProgramming #AutonomousAgents #OrcaIDE #OpenSource #TechPortfolio

---

## 🌐 Pilihan 2: English Version (For International Tech & Global Recruiters)

### Hook:
**How do you achieve zero-downtime execution when autonomous AI agents hit strict API rate limits?**

---

### Post Copy:

Autonomous coding agents are transforming software engineering, but they introduce a harsh operational bottleneck: **HTTP 429 / RESOURCE_EXHAUSTED rate limits**.

When an agent is in the middle of a multi-file architectural refactor and hits an hourly token cap, the entire execution halts—forcing engineers to manually swap credentials, re-authenticate keyrings, and re-prompt the terminal from scratch.

To solve this, I designed and open-sourced **Orca ADE Antigravity Auto-Switcher**: an event-driven, zero-downtime account failover engine and native Orca ADE Plugin v2.

---

### 🔬 Architecture & Deep-Dive:

Here is how the system maintains uninterrupted agent execution:

- **Dual-Engine Failure Detection:**
  Combines non-blocking streaming log parsing (monitoring Orca's NDJSON trace streams for quota-exhaustion regex patterns) with proactive IPC quota health checks. Failures are detected reactively in milliseconds.

- **Automated Session Rehydration:**
  Swapping accounts in the OS keyring isn't enough. The system tracks the active writable PTY terminal handle, enforces a 2.0s credential flush settle window, and automatically dispatches a resume prompt (`lanjutkan pengerjaan tadi`), seamlessly continuing the agent's work without losing conversation brain context.

- **Production-Grade Safety Architecture:**
  - 30-second debounce cooldown.
  - Sliding-window Circuit Breaker (halts switching if > 5 swaps happen within 180s) to safeguard against upstream IP bans.
  - PID file lock preventing race conditions across daemon instances.

- **Native Orca Plugin v2 Ecosystem:**
  Engineered with a Node.js `trusted-worker` and a high-density, dynamic sidebar UI matching native Orca dark theme tokens (`var(--orca-*)`). Features a built-in **Privacy Mask mode** to securely obscure credentials for screen recording and live streaming.

---

### 📊 Key Takeaways:
- **Zero-touch recovery:** Long-running agent tasks complete autonomously even when accounts exhaust quota.
- **Pure Standard Library Python + Native Plugin API:** Ultra-lightweight footprint running as a Linux systemd user daemon with 0 external pip dependencies.
- **7/7 Automated Unit Tests** ensuring bulletproof failover logic.

🔗 **GitHub Repository & Full Architecture Diagram:**  
https://github.com/syharipf/orca-antigravity-rotator

I'd love to hear how other teams are orchestrating multi-account quotas for autonomous agent loops!

---

### Hashtags:
#SoftwareEngineering #SystemDesign #AIEngineering #DevTools #Python #Linux #Systemd #AutonomousAgents #DistributedSystems #OpenSource

---

## 📸 Panduan Media Visual (Lampiran Postingan LinkedIn)

Untuk mendapatkan engagement tertinggi di LinkedIn (algoritma LinkedIn menyukai 1-3 gambar beresolusi tajam):

1. **Gambar Utama (Hero):** Gunakan file `images/cover.png` (sudah dirancang dengan rasio 960x600 beresolusi tinggi dan tema modern AI Gateway).
2. **Gambar Pendukung (Opsional):** Screenshot terminal saat menjalankan `./main.py live` atau `./main.py accounts --mask` yang menampilkan status routing `● IN USE` dengan akun dummy (`dev-lead@example.com`).
