# Orca ADE Antigravity Auto-Switcher

Background daemon dan service otomatisasi cerdas untuk **Orca ADE** dengan agent **Antigravity (`agy`)** di sistem Linux. Service ini mendeteksi limit kuota (HTTP 429 / `RESOURCE_EXHAUSTED`), melakukan rotasi akun secara otomatis ke akun yang masih memiliki kuota kosong (0%), dan langsung melanjutkan (*auto-resume*) tugas pada sesi terminal aktif.

---

## 🚀 Fitur Utama

1. **Real-time Log & Quota Monitoring:**
   - Memonitor event log Orca secara realtime pada `~/.config/orca/logs/main.trace.ndjson`, `~/.config/orca/logs/daemon.log`, dan log transcript ACP brain (`transcript*.jsonl`).
   - Mendeteksi error pola limit seperti `RESOURCE_EXHAUSTED`, `429 Too Many Requests`, `Quota exceeded`, `rate_limit_exceeded`, dan pola terkait limit Gemini / Antigravity.
   - Dual-Protection: Melakukan *periodic quota health check* ke Orca CLI (`orca account list --agent antigravity --json`) untuk memastikan jika kuota akun aktif terindikasi 100% habis, rotasi segera dilakukan.

2. **Smart Account Rotation (Rotasi Cerdas):**
   - Menganalisis seluruh akun Antigravity yang terdaftar di Orca host.
   - Memilih akun berikutnya berdasarkan kuota paling kosong (memprioritaskan Session & Weekly used = 0%).
   - Mendukung strategi `smart_quota` (default) dan `round_robin`.
   - Menghitung waktu reset terdekat jika seluruh akun telah mencapai batas kuota (100%), lalu masuk ke mode penghematan aman.

3. **Auto-Resume / Auto-Retry:**
   - Setelah akun berganti, sistem menunggu jeda *settle delay* (default 2 detik) agar kredensial OS keyring tersimpan stabil.
   - Menemukan terminal Orca aktif yang terhubung dan siap ditulisi (`connected: true, writable: true`), memprioritaskan sesi Antigravity.
   - Mengirim trigger otomatis agar pekerjaan dilanjutkan:
     ```bash
     orca terminal send --terminal <terminal_id> --text "lanjutkan pengerjaan tadi" --enter
     ```

4. **Safety & Anti-Ban Engine (Keamanan Tinggi):**
   - **Cooldown Period:** Jeda minimal 30 detik antar rotasi agar tidak terjadi spamming atau pergantian berulang-ulang.
   - **Circuit Breaker:** Jika terjadi > 5 kali perpindahan akun dalam 3 menit, sistem menahan rotasi dan membunyikan alarm agar terhindar dari pemblokiran akun Google / Orca.
   - **Single-Instance Lock:** Mencegah terjadinya *race condition* atau dua proses daemon berjalan bersamaan via `/tmp/orca-agy-rotator.lock`.
   - **Desktop Notification:** Memberikan notifikasi pop-up desktop via `notify-send` untuk setiap rotasi, kegagalan kuota, dan status circuit breaker.

---

## 📁 Struktur Direktori

```text
agy auto switch/
├── config.json                 # File konfigurasi default (bisa disesuaikan)
├── main.py                     # CLI entrypoint executable
├── rotator/                    # Paket modular Python
│   ├── __init__.py
│   ├── account_manager.py      # Orca account listing, selection, quota ranking
│   ├── config.py               # Dataclass konfigurasi & loader
│   ├── monitor.py              # Log file watcher & regex pattern matching
│   ├── notifier.py             # Desktop notifications (notify-send) & logger
│   ├── safety.py               # Cooldown, circuit breaker, & lockfile
│   ├── service.py              # Core daemon engine
│   └── terminal_manager.py     # Orca terminal detection & resume sender
├── orca-agy-rotator.service    # Unit template systemd user service
├── install_service.sh          # Script instalasi otomatis systemd
├── test_rotator.py             # Unit test suite lengkap
└── README.md                   # Dokumentasi
```

---

## 🛠️ Panduan Penggunaan CLI

Tool ini dilengkapi antarmuka CLI yang kaya fitur melalui `./main.py`:

### 1. Melihat Status Sistem & Terminal
```bash
./main.py status
```
Menampilkan:
- Status daemon & service systemd
- Akun aktif saat ini beserta penggunaan kuota Session & Weekly
- Waktu hitung mundur menuju reset kuota
- Terminal Orca yang terdeteksi aktif

### 2. Melihat Tabel Seluruh Akun Antigravity
```bash
./main.py accounts
```
Contoh output:
```text
==========================================================================================
STATUS     | EMAIL                            | SESSION    | WEEKLY     | RESET TERDEKAT      
==========================================================================================
READY      | dev-account-1@gmail.com          | 0%         | 0%         | 23:09:59 (178m lagi)
READY      | dev-account-2@gmail.com          | 2%         | 2%         | 23:25:32 (194m lagi)
READY      | dev-account-3@gmail.com          | 1%         | 1%         | 23:43:11 (211m lagi)
READY      | dev-account-4@gmail.com          | 1%         | 1%         | 23:50:54 (219m lagi)
READY      | dev-account-5@gmail.com          | 1%         | 1%         | 23:52:13 (220m lagi)
[ACTIVE]   | dev-account-6@gmail.com          | 0%         | 0%         | 01:08:49 (297m lagi)
==========================================================================================
```

### 3. Rotasi Akun Manual
- Beralih ke akun terbaik secara otomatis:
  ```bash
  ./main.py switch
  ```
- Beralih ke email spesifik:
  ```bash
  ./main.py switch dev-account-1@gmail.com
  ```
- Menguji rotasi tanpa mengubah akun sungguhan (*dry-run*):
  ```bash
  ./main.py switch --dry-run
  ```

### 4. Menguji Pengiriman Auto-Resume
```bash
./main.py resume --dry-run
```

### 5. Menguji Notifikasi Desktop
```bash
./main.py test-notify
```

### 6. Menjalankan Daemon di Foreground
```bash
./main.py run
```
Atau dengan mode dry-run:
```bash
./main.py run --dry-run
```

---

## ⚙️ Menjalankan Sebagai Systemd User Service

Agar service otomatis berjalan di latar belakang setiap kali Anda login ke sesi grafis Linux:

### Cara 1: Menggunakan Perintah CLI
```bash
./main.py install-service
```

### Cara 2: Menggunakan Helper Script
```bash
./install_service.sh
```

### Memeriksa Status Service
```bash
systemctl --user status orca-agy-rotator.service
```

### Melihat Log Realtime Service
```bash
journalctl --user -u orca-agy-rotator.service -f
```

### Menghentikan atau Menonaktifkan Service
```bash
systemctl --user stop orca-agy-rotator.service
# Atau copot service secara permanen:
./main.py uninstall-service
```

---

## 🔧 Konfigurasi (`config.json`)

Anda dapat menyesuaikan parameter di `config.json` atau file konfigurasi kustom:

```json
{
  "log_check_interval": 1.0,
  "quota_check_interval": 20.0,
  "cooldown_seconds": 30.0,
  "circuit_breaker_max_switches": 5,
  "circuit_breaker_window_seconds": 180.0,
  "rotation_strategy": "smart_quota",
  "auto_resume": true,
  "resume_delay_seconds": 2.0,
  "resume_command": "lanjutkan pengerjaan tadi",
  "target_terminal": null,
  "notifications_enabled": true,
  "notification_app_name": "Orca ADE Rotator"
}
```

| Parameter | Keterangan | Default |
|---|---|---|
| `log_check_interval` | Frekuensi polling file log (detik) | `1.0` |
| `quota_check_interval` | Frekuensi pengecekan kuota aktif ke Orca CLI | `20.0` |
| `cooldown_seconds` | Jeda waktu minimal antar pergantian akun | `30.0` |
| `circuit_breaker_max_switches` | Batas maksimum pergantian dalam window | `5` |
| `circuit_breaker_window_seconds` | Durasi window circuit breaker (detik) | `180.0` |
| `rotation_strategy` | `smart_quota` (kuota 0% dulu) atau `round_robin` | `smart_quota` |
| `auto_resume` | Aktifkan pengiriman trigger otomatis ke terminal | `true` |
| `resume_delay_seconds` | Waktu jeda setelah ganti akun sebelum resume | `2.0` |
| `resume_command` | Perintah yang diketikkan ke terminal aktif | `"lanjutkan pengerjaan tadi"` |
| `target_terminal` | Handle terminal spesifik (`null` = deteksi otomatis) | `null` |
| `notifications_enabled` | Aktifkan pop-up desktop Linux via `notify-send` | `true` |

---

## 🧩 Integrasi Penuh Sebagai Plugin Resmi Orca ADE

Project ini telah dilengkapi dengan spesifikasi **Official Orca Plugin Manifest v2** (`orca-plugin.json`):

1. **Status Bar Item di Orca:**
   Menampilkan email akun aktif dan status kuota real-time di status bar Orca bagian bawah:
   `[refresh] Agy: indahmysri1 (0%)`
2. **Sidebar Panel UI di Orca (`panel/index.html`):**
   Membuka panel visual di sidebar kanan Orca untuk melihat seluruh 6 akun Antigravity, progress bar sisa kuota Session & Weekly, countdown waktu reset, dan tombol *Rotate Best* serta *Pilih Akun*.
3. **Background Worker (`src/worker.mjs`):**
   Worker Node.js `trusted-worker` yang terus aktif di latar belakang Orca, mendeteksi event `agent.status.changed`, merotasi akun saat rate limit, dan memicu auto-resume ke terminal.

### Menjalankan Plugin di Orca Lokal (Development Mode)
```bash
# Validasi struktur plugin:
orca plugin validate .

# Muat plugin langsung ke Orca Anda:
orca plugin dev load .

# Buka panel visual switcher di sidebar kanan Orca:
orca plugin open local.antigravity-rotator
```

### 🚀 Cara Rilis ke Marketplace Orca Komunitas (`orca-community-plugins`)
1. **Push repository ini ke GitHub Anda:**
   ```bash
   git remote add origin https://github.com/<username>/orca-antigravity-rotator.git
   git branch -M main
   git push -u origin main
   ```
2. **Generate Release Entry:**
   ```bash
   orca plugin release-entry .
   ```
3. **Submit ke Orca Marketplace:**
   - Buka repository [stablyai/orca-community-plugins](https://github.com/stablyai/orca-community-plugins).
   - Fork repo tersebut dan tempelkan blok JSON hasil `orca plugin release-entry .` ke dalam file `orca-catalog.json`.
   - Buka Pull Request (PR).
   - Setelah di-merge, pengguna di seluruh dunia bisa menginstalnya dengan satu baris:
     ```bash
     orca plugin install antigravity-rotator --approve
     ```

---

## 🧪 Pengujian & Validasi

Suite pengujian unit test telah disertakan:
```bash
python3 test_rotator.py
```
Output:
```text
Ran 7 tests in 0.004s

OK
```
Test mencakup:
1. Pemilihan kandidat akun dengan kuota kosong (*Smart Quota*).
2. Penanganan kondisi seluruh akun limit (*All Exhausted* & kalkulasi waktu reset).
3. Pemilihan metode *Round-Robin*.
4. Penegakan waktu jeda (*Cooldown Enforcement*).
5. Pengaktifan pemutus sirkuit (*Circuit Breaker Trip*).
6. Pendeteksian regex pola rate limit pada log streaming.
7. Pemeringkatan prioritas terminal agen aktif.
