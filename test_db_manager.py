from pathlib import Path
from loaders.notebooklm_manager import SourceTracker, SourceRecord

tracker = SourceTracker(Path('data/source_tracking.json'))
for i in range(3):
    tracker.is_already_uploaded("hash123", "nb123")
    tracker.get_active_sources("nb123")
    record = SourceRecord(
        source_id=f"src_{i}",
        notebook_id="nb123",
        notebook_name="Test NB",
        title=f"Test {i}",
        source_type="text",
        local_file="test.txt",
        uploaded_at="2026-05-01T21:00:00",
        content_hash=f"hash_{i}",
        is_active=True
    )
    tracker.add_source(record)
    print(f"Added {i}")

print("Stats:", tracker.get_statistics())
tracker.close()
print("Done")
