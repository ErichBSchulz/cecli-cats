import hashlib
import os
from pathlib import Path

def calculate_directory_hash(directory: Path) -> str:
    sha256_hash = hashlib.sha256()
    
    # Walk directory, sort files for consistency
    for root, _, files in sorted(os.walk(directory)):
        for file in sorted(files):
            if file.startswith("cat") and file.endswith(".yaml"):
                continue
                
            file_path = Path(root) / file
            # Include relative path in hash to detect structure changes
            rel_path = str(file_path.relative_to(directory))
            sha256_hash.update(rel_path.encode())
            
            try:
                with open(file_path, "rb") as f:
                    while chunk := f.read(4096):
                        sha256_hash.update(chunk)
            except (IOError, OSError):
                # We want to fail fast/loud
                raise

    return sha256_hash.hexdigest()
