from pathlib import Path

from fastapi import UploadFile


async def save_upload_file(upload_dir: str, file: UploadFile) -> dict:
    base = Path(upload_dir)
    base.mkdir(parents=True, exist_ok=True)

    destination = base / file.filename
    content = await file.read()
    destination.write_bytes(content)

    return {
        "filename": file.filename,
        "size": len(content),
        "path": str(destination),
    }
