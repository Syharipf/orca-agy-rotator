# LinkedIn Portfolio Showcase Guide

Draft materi LinkedIn untuk memamerkan proyek **Orca ADE Antigravity Auto-Switcher** dari perspektif Software Engineering, Systems Architecture, dan Developer Tooling.

---

## Opsi 1: Bahasa Indonesia (Tech Community & Engineering Leads)

### Post Copy:

Bagi yang menggunakan Orca ADE dengan agent Antigravity (`antigravity`), pengelolaan akun saat ini dilakukan via subsistem CLI bawaan: `orca account list` dan `orca account select`.

Secara default, Orca ADE belum menyediakan mekanisme automatic failover/rotasi kuota antar akun yang terdaftar. Ketika sebuah akun mencapai limit kuota (`HTTP 429 Too Many Requests` atau `RESOURCE_EXHAUSTED`):
- Sesi aktif di terminal langsung berhenti.
- Developer harus mengecek sisa kuota akun secara manual (`orca account list --json`).
- Menjalankan `orca account select` untuk mengalihkan kredensial keyring host.
- Mengetikkan perintah manual di terminal aktif agar agen melanjutkan pekerjaannya.

Untuk mengotomasi seluruh alur ini tanpa interupsi manual, saya membangun **Orca ADE Antigravity Auto-Switcher** (Linux User Daemon + Orca ADE Plugin v2).

### Arsitektur & Cara Kerja:

1. **Dual-Engine Detection:**
   Mengkombinasikan streaming log watcher (memindai trace NDJSON Orca secara non-blocking untuk mendeteksi error rate-limit) dengan proactive polling berkala (`orca account list`). Jika kuota sesi akun aktif menyentuh 100%, sistem langsung menyiapkan rotasi sebelum terjadi kegagalan turn.

2. **Smart Quota Ranking:**
   Mem-parsing struktur data kuota Orca secara presisi (membedakan skala persentase 0-100% dan model buckets seperti Gemini, Claude, GPT, Argon, dan Carbon), serta memprioritaskan akun dengan kuota kosong (0%). Jika seluruh akun mencapai batas limit, sistem menghitung timestamp reset terdekat secara deterministik.

3. **Keyring Settle & Session Rehydration:**
   Setelah akun dialihkan via IPC `orca account select`, sistem memberikan jeda settle 2.0 detik untuk sinkronisasi kredensial OS keyring, kemudian secara otomatis mengirimkan prompt resume (`orca terminal send`) ke PTY terminal yang aktif dan writable. Konteks percakapan tetap terjaga tanpa perlu re-prompt manual.

4. **Safety & Guardrails:**
   Dilengkapi cooldown gate 30 detik, sliding-window circuit breaker (menahan rotasi jika terjadi > 5 transisi dalam 180 detik), PID file locking, serta mode Privacy Masking untuk menyamarkan identitas email saat screen recording.

Proyek ini sepenuhnya open-source (Python standard library tanpa dependensi pip eksternal + manifest resmi Orca ADE Plugin v2 dengan 7/7 unit tests passing).

Source code dan dokumentasi teknis:
https://github.com/syharipf/orca-antigravity-rotator

---

## Option 2: English (International Tech Audience & Systems Engineering)

### Post Copy:

In Orca ADE, multi-account Antigravity agent authentication is handled via the `orca account` CLI (`orca account list` and `orca account select`).

However, Orca does not feature native automatic quota failover. When an account encounters rate limits (`HTTP 429 Too Many Requests` or `RESOURCE_EXHAUSTED`), execution halts abruptly. Developers must manually query account quotas, execute `orca account select` to re-bind host credentials, and manually prompt the terminal to resume work.

To eliminate this manual bottleneck during long-running autonomous agent sessions, I developed **Orca ADE Antigravity Auto-Switcher**—a background supervisor daemon and native Orca ADE Plugin v2.

### Engineering Highlights:

- **Dual-Engine Failure Detection:**
  Combines non-blocking streaming log parsing (line-buffered regex scanning over Orca's trace NDJSON streams) with proactive IPC quota health evaluation. Failover triggers preemptively before turns crash.

- **Deterministic Quota Selection:**
  Accurately parses Orca's native integer percentage scales (`usedPercent: 0-100`) across all model buckets (Gemini, Claude, GPT, Argon, Carbon), prioritizing 0% utilized accounts. If all accounts are exhausted, it computes the nearest reset epoch and safely holds execution.

- **Credential Settle & Terminal Session Rehydration:**
  Following `orca account select` execution, the supervisor enforces a 2.0s settle delay for OS keyring propagation, then resolves the active writable PTY terminal handle and injects a continuation command (`orca terminal send`) without disrupting conversation state.

- **Production Safety Controls:**
  Enforces a 30s debounce cooldown, a sliding-window circuit breaker (tripping at > 5 rotations per 180s to prevent upstream API abuse flags), PID single-instance locking, and a deterministic Privacy Masking layer for secure screencasting.

Built purely on Python standard library modules and the official Orca Plugin Manifest v2 specification (`trusted-worker`), backed by a 7/7 passing unit test suite.

Repository and technical specifications:
https://github.com/syharipf/orca-antigravity-rotator

#SoftwareEngineering #SystemArchitecture #DeveloperTools #Linux #Python #DevOps #AutonomousAgents #OrcaADE #OpenSource
