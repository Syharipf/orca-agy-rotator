# 🚀 LinkedIn Portfolio Write-Up & Showcase Guide

Dokumen ini berisi materi postingan LinkedIn siap pakai dalam 2 versi bahasa (**Bahasa Indonesia** & **English**) yang dirancang khusus untuk memamerkan *technical depth*, *systems engineering*, dan penyelesaian masalah riil di bidang **AI Developer Experience (DevEx) & Autonomous Agents Infrastructure**.

---

## 📌 Pilihan 1: Versi Bahasa Indonesia (Rekomendasi untuk Komunitas Tech ID)

### Judul / Hook:
**Niatnya pakai Autonomous AI Agent biar bisa ditinggal ngopi, kenyataannya malah sibuk "nge-babysit" agen yang macet gara-gara kuota habis? ☕😤**

---

### Copy Postingan:

Buat teman-teman developer yang pakai **Orca ADE** dengan agent **Antigravity (`agy`)**, pasti familiar dengan masalah ini:

Kita punya banyak akun Google cadangan untuk antisipasi kuota. Tapi **bawaan Orca saat ini BELUM BISA auto-switch akun Antigravity secara otomatis**.

Setiap kali akun aktif kena rate limit (`HTTP 429 Too Many Requests` atau `RESOURCE_EXHAUSTED`):
1. 🛑 Agen langsung berhenti macet di tengah jalan.
2. 🔍 Kita harus cek satu per satu akun mana yang kuotanya masih kosong atau sudah reset.
3. 🔄 Buka terminal / command palette buat ganti akun manual (`orca account switch`).
4. ⌨️ Ketik manual lagi di terminal: *"lanjutkan pengerjaan"* supaya agen mau jalan lagi.

Alhasil, kita gak bisa benar-benar meninggalkan coding agent bekerja secara otonom karena harus bolak-balik ngecek terminal.

Untuk mengatasi friksi ini, saya merancang dan membangun:
🛠️ **Orca ADE Antigravity Auto-Switcher** — Sistem rotasi akun pintar dan *zero-downtime failover* yang menggabungkan **Linux Systemd User Daemon** + **Official Orca ADE Plugin v2**.

---

### 🧠 Cara Kerjanya di Balik Layar:

1. **Dual-Engine Auto-Detection:**
   Memantau stream log trace NDJSON Orca secara non-blocking untuk mendeteksi error `429` & `RESOURCE_EXHAUSTED`. Sekaligus melakukan *proactive health check*: jika kuota akun menyentuh 100%, sistem langsung merotasi akun **sebelum** agen crash.

2. **Smart Quota Ranking:**
   Otomatis memilih akun berikutnya yang kuota Session & Weekly-nya paling kosong (0%), paham penuh dengan skala persentase Orca (0–100%).

3. **Automated Terminal Session Rehydration (Auto-Resume):**
   Ganti akun saja tidak cukup! Sistem mendeteksi PTY terminal aktif yang terhubung, menerapkan jeda *settle delay* (2 detik) agar OS keyring tersinkronisasi stabil, lalu otomatis menyuntikkan perintah `"lanjutkan pengerjaan tadi"` ke terminal aktif tanpa merusak konteks percakapan agen.

4. **Safety & Anti-Ban Protection:**
   Dilengkapi cooldown 30 detik, sliding-window circuit breaker (menahan rotasi jika terjadi > 5 kali pergantian dalam 3 menit untuk melindungi akun dari pemblokiran API), single-instance lockfile, dan notifikasi desktop Linux (`notify-send`).

5. **Official Orca Plugin v2 & Privacy Mask:**
   Hadir dengan panel sidebar kanan berdesain *Zero AI Slop* (bersih, high-contrast, token `var(--orca-*)`) dan fitur **Privacy Mask** untuk menyamarkan email akun asli saat screen recording atau presentasi.

---

### 💡 Dampak & Hasil:
- ⚡ **100% Autonomous Execution:** Dari yang tadinya harus bolak-balik ganti akun manual, sekarang agen bisa bekerja berjam-jam tanpa perlu intervensi manusia sama sekali.
- 🎯 **Zero Context Loss:** Sesi agen langsung lanjut tanpa reset prompt.
- 🧪 **7/7 Passing Unit Tests:** Seluruh skenario edge-case (all exhausted, round-robin, regex streaming, circuit breaker) tervalidasi otomatis.

Source code, diagram arsitektur, dan panduan instalasi lengkap sudah saya open-source di GitHub:
👉 https://github.com/syharipf/orca-antigravity-rotator

Gimana teman-teman menangani limit kuota dan multi-account di workflow AI agent kalian? Let's discuss in the comments! 👇

---

### Hashtags:
#SoftwareEngineering #AIEngineering #DeveloperTools #Linux #Python #DevOps #SystemProgramming #AutonomousAgents #OrcaIDE #OpenSource #TechPortfolio

---

## 🌐 Pilihan 2: English Version (For Global Recruiters & International Tech Community)

### Hook:
**Why autonomous coding agents still require constant babysitting—and how I built zero-downtime auto-failover to fix it.**

---

### Post Copy:

In **Orca ADE**, the **Antigravity (`agy`)** agent is phenomenal for complex autonomous coding. Most engineers link multiple accounts to ensure plenty of quota.

However, there is an annoying operational bottleneck: **Orca ADE does NOT natively support automatic account switching for Antigravity.**

Whenever an active account hits an API limit (`HTTP 429 Too Many Requests` or `RESOURCE_EXHAUSTED`):
1. 🛑 The agent halts abruptly in the middle of a refactor.
2. 🔍 You must manually inspect all accounts to find one with available quota.
3. 🔄 You must manually switch credentials in the terminal (`orca account switch`).
4. ⌨️ You must manually type *"continue previous task"* to get the agent moving again.

Instead of autonomous coding running quietly in the background while you focus on architecture, you end up babysitting rate limits.

To solve this friction, I built **Orca ADE Antigravity Auto-Switcher**: an event-driven background failover engine and native Orca ADE Plugin v2.

---

### 🔬 How It Works Under The Hood:

- **Dual-Engine Failure Detection:**
  Parses Orca's NDJSON trace log streams in real-time for quota errors while running proactive IPC quota health probes. If an account reaches 100% usage, it triggers rotation proactively before the turn fails.

- **Smart Quota Selection:**
  Ranks all available accounts, prioritizing unused quota (0% session usage), while tracking multi-tier model buckets (Gemini, Claude 3.7, GPT-4o, Argon, Carbon).

- **Automated Session Rehydration (Zero Context Loss):**
  Swapping OS keyrings isn't enough. The system locates the active writable PTY terminal handle, enforces a 2.0-second credential settle delay, and dispatches a resume prompt (`"lanjutkan pengerjaan tadi"`), letting the agent seamlessly continue without losing its working memory.

- **Production-Grade Safety Architecture:**
  Guarded by a 30s debounce cooldown, a sliding-window Circuit Breaker (halts switching if > 5 swaps occur in 180s to prevent upstream abuse flags), and PID file locking.

- **Native Orca Plugin v2 with Privacy Mask:**
  Ships with a responsive dark-themed sidebar panel (`var(--orca-*)`) and a built-in Privacy Mask toggle that replaces real corporate emails with sanitized aliases for safe streaming and screencasts.

---

### 📊 Results:
- ⚡ **100% Uninterrupted Execution:** Multi-hour agent sessions run end-to-end without manual intervention.
- 🎯 **Zero Context Loss:** Seamless terminal re-engagement.
- 🧪 **7/7 Automated Unit Tests** verifying edge cases and safety triggers.

🔗 **GitHub Repository & Full Architecture Diagram:**  
https://github.com/syharipf/orca-antigravity-rotator

How do you manage multi-account rate limits in your agentic workflows? I'd love to hear your thoughts in the comments!

---

### Hashtags:
#SoftwareEngineering #SystemDesign #AIEngineering #DevTools #Python #Linux #Systemd #AutonomousAgents #DistributedSystems #OpenSource
