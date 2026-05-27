"""
YouTube'da 104 concept playlist oluşturur ve playlist_id'leri DB'ye yazar.
Her playlist sonrası commit yapar — kesintiye dayanıklı, kaldığı yerden devam eder.

Kullanım:
    python scripts/create_yt_playlists.py 2>&1 | tee logs/create_playlists.log
"""

import sys
import time
from pathlib import Path

# Proje kök dizinini PYTHONPATH'e ekle
sys.path.insert(0, str(Path(__file__).parent.parent))

from googleapiclient.errors import HttpError

from src.adapters.youtube.youtube_client import YouTubeClient
from src.config.settings import settings
from src.storage.database import SessionLocal
from src.storage.models import ConceptPlaylist


def main():
    client = YouTubeClient(client_secrets_file=settings.youtube.client_secrets_file)
    svc = client._get_service()

    # 1. YouTube'daki TÜM mevcut playlist'leri bir kez çek (batch)
    print("YouTube playlist listesi alınıyor...", flush=True)
    existing_yt: dict[str, str] = {}  # title -> playlist_id
    page_token = None
    while True:
        resp = svc.playlists().list(
            part="snippet", mine=True, maxResults=50, pageToken=page_token
        ).execute()
        for item in resp.get("items", []):
            title = item["snippet"]["title"]
            pid = item["id"]
            existing_yt[title] = pid
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    print(f"YouTube'da {len(existing_yt)} mevcut playlist bulundu.", flush=True)

    session = SessionLocal()
    try:
        concepts = (
            session.query(ConceptPlaylist)
            .filter_by(is_active=True)
            .order_by(ConceptPlaylist.sort_order)
            .all()
        )
        total = len(concepts)

        # 2. Mevcut YouTube playlist'lerini DB'ye eşleştir
        matched = 0
        for concept in concepts:
            if concept.playlist_id:
                continue
            if concept.title in existing_yt:
                concept.playlist_id = existing_yt[concept.title]
                matched += 1
        session.commit()
        print(f"{matched} mevcut playlist DB'ye eşleştirildi.", flush=True)

        # 3. Kalan (playlist_id'siz) playlist'leri oluştur
        pending = [c for c in concepts if not c.playlist_id]
        print(f"{len(pending)} playlist oluşturulacak...", flush=True)

        for i, concept in enumerate(pending, 1):
            desc = (
                f"Anadolu Geceleri — {concept.title}. "
                "Turkish ambient, lo-fi, and folk music for late nights, "
                "study sessions, and deep focus."
            )
            retry = 0
            while retry < 10:
                try:
                    resp = svc.playlists().insert(
                        part="snippet,status",
                        body={
                            "snippet": {"title": concept.title, "description": desc},
                            "status": {"privacyStatus": "public"},
                        },
                    ).execute()
                    playlist_id = resp["id"]
                    concept.playlist_id = playlist_id
                    session.commit()  # Her playlist sonrası kalıcı kaydet
                    print(
                        f"[{i}/{len(pending)}] OLUŞTURULDU: {concept.title} -> {playlist_id}",
                        flush=True,
                    )
                    time.sleep(30)  # Rate limit için 30s bekle
                    break
                except HttpError as e:
                    if e.resp.status == 429:
                        wait = 30 * (2**retry)
                        print(
                            f"  Rate limit (deneme {retry + 1}), {wait}s bekleniyor...",
                            flush=True,
                        )
                        time.sleep(wait)
                        retry += 1
                    else:
                        print(f"  HTTP Hata: {e}", flush=True)
                        raise
            else:
                print(f"  HATA: {concept.title} oluşturulamadı, atlanıyor.", flush=True)

        # Son durum
        done = session.query(ConceptPlaylist).filter(
            ConceptPlaylist.playlist_id.isnot(None)
        ).count()
        print(f"\nTamamlandı! {done}/{total} playlist'in YouTube ID'si kaydedildi.", flush=True)

    finally:
        session.close()


if __name__ == "__main__":
    main()
