# Anadolu Türküleri Ezgileri — Proje Planı

## Proje Özeti
81 Türk şehri için tam otomatik türkü üretim hattı.  
Ollama (LLM) + SDXL-Turbo (görsel) + FFmpeg (video) + YouTube Data API (yayın).  
Müzik üretimi şu an **manuel** (Suno.com) — faz 2'de otomasyon planlandı.

---

## Mevcut Durum

### Tamamlanan Altyapı
- [x] SQLite veritabanı + SQLAlchemy ORM (`Song`, `City`, `GenerationHistory`)
- [x] 81 şehir verisi (`data/cities/cities.json`) + **81 kültürel profil** (`data/cities/cultural_profiles/`)
- [x] Tam pipeline durumu makinesi (`SongStatus` enum, idempotent stage'ler)
- [x] `PipelineService` — tek şarkıyı uçtan uca ilerletiyor
- [x] `CycleRunner` + `Orchestrator` — round-robin şehir seçimi + K şarkı/döngü
- [x] CLI: `db-init`, `generate-city`, `generate-next`, `resume-song`, `run-cycle`, `dry-run`, `review-song`, `import-audio`, `render-video`, `upload-youtube`, `list-songs`, `song-stats`
- [x] YouTube OAuth2 yükleme istemcisi (long + short) + kota takibi
- [x] Suno manuel istemci — prompt dosyası yazıyor, operatör sesi içe aktarıyor

### Ajan Katmanı (Ollama / qwen2.5:7b)
- [x] `ConceptAgent` — şehir başına benzersiz türkü konsepti
- [x] `LyricAgent` — kültürel kısıtlamalar ile sözler
- [x] `QualityChecker` — skor ≥ 8.0 ise onay, yoksa yeniden deneme (max 3)
- [x] `SunoPromptAgent` — Suno tarzı + sözler hazırlama
- [x] `ImagePromptAgent` — arka plan görseli için SDXL prompt
- [x] `MetadataAgent` — YouTube başlık / açıklama / etiketler

### Medya Katmanı
- [x] `ImageGenerator` — SDXL-Turbo (Apple MPS) arka plan
- [x] `SubtitleBuilder` — süreden SRT oluşturma
- [x] `ThumbnailRenderer` — başlık + şehir adıyla JPG küçük resim
- [x] `LongVideoRenderer` — 1920×1080 @ 25fps, CRF 23, AAC 192k
- [x] `ShortRenderer` — 1080×1920 (dikey), 40 sn hook
- [x] `audio_utils` — FFmpeg tabanlı ses süresi okuma

---

## Pipeline Akışı

```
PENDING
  └─► [ConceptAgent]          → CONCEPT_READY
        └─► [LyricAgent]      → QUALITY_APPROVED / QUALITY_REJECTED (max 3 retry)
              └─► [SunoPromptAgent] → SUNO_READY  ← BLOKLAR (manuel adım)
                    └─► import-audio CLI
                          └─► AUDIO_IMPORTED
                                └─► [ImageGenerator]  → IMAGE_READY
                                      └─► [VideoRenderer + ShortRenderer] → VIDEO_READY
                                            └─► [YouTubeClient]  → UPLOADED
```

**Manuel adım:** `SUNO_READY`'de pipeline durur. Operatör:
1. `outputs/_suno_prompts/<song_id>.txt` dosyasını açar
2. suno.com'da şarkı üretir, MP3 indirir
3. `python -m cli import-audio --song-id <id> --file <mp3>` komutuyla devam ettirir

---

## Eksik / Yapılacaklar

### Öncelik 1 — Kültürel Profiller ✅ TAMAMLANDI
- [x] Tüm 81 şehrin `data/cities/cultural_profiles/<slug>.json` dosyası mevcut
- [x] `CityService.load_cultural_profile()` graceful fallback uygulandı (boş dict döner)

### Öncelik 2 — Veritabanı Alanları Uyumu ✅ TAMAMLANDI
- [x] `Song` modeline 8 eksik alan eklendi (`rejected_reason`, `subtitles_path`, `long_video_path`, `short_video_path`, `background_image_path`, `suno_lyrics`, vb.)
- [x] `SongStatus.PENDING` enum'a eklendi
- [x] Alembic kurulumu + initial migration oluşturuldu

### Öncelik 3 — Eksik CLI Komutları ✅ TAMAMLANDI
- [x] `render-video` — AUDIO_IMPORTED veya IMAGE_READY şarkıyı render eder
- [x] `list-songs` — şarkıları duruma göre filtreli tablo listeler
- [x] `song-stats` — durum bazlı özet istatistik
- [x] `resume-song <song_id>` — takılı kalmış şarkıyı pipeline'ın kaldığı yerden ilerletir

### Öncelik 4 — Suno Faz 2 (Otomasyon)
- [ ] `BrowserSunoClient` (Playwright) — `SUNO_CLIENT=browser` ile tam otomatik müzik üretimi
- [ ] Cookie / session yönetimi
- [ ] Üretim sonrası MP3 otomatik indirme

### Öncelik 4 — Suno Faz 2 (Otomasyon)
- [ ] `BrowserSunoClient` (Playwright) — `SUNO_CLIENT=browser` ile tam otomatik müzik üretimi
- [ ] Cookie / session yönetimi
- [ ] Üretim sonrası MP3 otomatik indirme

### Öncelik 5 — Kota ve Güvenilirlik
- [ ] `QuotaTracker` — YouTube kota kontrolü upload öncesi doğru entegre edilmeli
- [ ] Pipeline'da her stage için `try/except` + stage hata durumu kaydı

### Öncelik 6 — Gözlemlenebilirlik
- [x] `list-songs` + `song-stats` özet istatistik komutları
- [ ] JSON yapılandırılmış loglama (`structlog` zaten requirements'ta)
- [ ] `outputs/` dizin yapısı dökümantasyonu

---

## Dosya Yapısı

```
config/config.yaml          ← Tüm ayarlar (Ollama, YouTube, video, pipeline)
data/
  cities/cities.json        ← 81 şehir slug + bölge + sıralama
  cities/cultural_profiles/ ← Şehir başına enstrüman, üslup, kelime kısıtlamaları
  anadolu.db                ← SQLite (git-ignored)
outputs/
  <slug>/<song_id>/
    audio.mp3
    background.png
    video.mp4
    short.mp4
    thumbnail.jpg
    subtitles.srt
  _suno_prompts/<song_id>.txt
prompts/                    ← Ollama system prompt dosyaları
src/
  agents/                   ← LLM ajan sınıfları
  adapters/suno|youtube/    ← Harici servis istemcileri
  config/                   ← settings.py (Pydantic), models_config.py
  image/                    ← SDXL-Turbo görsel üretimi
  quality/                  ← Kalite kontrol kuralları ve denetçi
  scheduler/                ← CycleRunner + Orchestrator
  services/                 ← City, Song, History, Pipeline servisleri
  storage/                  ← ORM modelleri, DB session, dosya depolama
  video/                    ← FFmpeg sarmalayıcıları
  cli/                      ← Click komutları
```

---

## Ortam Değişkenleri (.env)

```env
# Zorunlu
YOUTUBE_CLIENT_SECRETS_FILE=config/youtube_client_secrets.json
YOUTUBE_CHANNEL_ID=UCxxxxxxxxxxxxxxxxx

# Opsiyonel
SUNO_CLIENT=manual          # manual | browser
DRY_RUN=false
DATABASE_URL=sqlite:///data/anadolu.db
OUTPUTS_DIR=outputs
```

---

## Hızlı Başlangıç

```bash
# 1. Bağımlılıkları yükle
pip install -r requirements.txt

# 2. Veritabanı + şehirleri oluştur
python -m cli db-init

# 3. Bir şarkı üret (dry-run)
python -m cli dry-run --city erzincan

# 4. Suno prompt dosyasını görüntüle
cat outputs/_suno_prompts/<song_id>.txt

# 5. Sesi içe aktar ve pipeline'ı devam ettir
python -m cli import-audio --song-id <id> --file ~/Downloads/sarki.mp3

# 6. Şarkıyı incele
python -m cli review-song <song_id>

# 7. YouTube'a yükle
python -m cli upload-youtube <song_id>
```

---

## Sonraki Sprint Hedefleri

1. Kalan 76 şehir için kültürel profil şablonu oluştur ve otomatik doldur
2. Alembic kurulumu + eksik `Song` alanları migration'ı
3. `SongStatus.PENDING` enum'a ekle
4. `list-songs` CLI komutu
5. `render-video` komutunu tamamla
6. Suno Playwright istemcisi (faz 2 — opsiyonel)
