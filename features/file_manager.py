"""
JARVIS Phase 4 — File Manager
Handles:
  - Search and open files by name
  - Auto-organize folders by file type
  - Delete junk/temp/duplicate files
  - Compress folders/files to zip
  - Batch rename files
  - Read and summarize documents (pdf, docx, txt)
  - Sync files between Windows and ChromeOS (via WebSocket - Phase 5)
"""

import os
import re
import shutil
import zipfile
import hashlib
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

# Store last search results globally
last_search_results = []
# ─── Common paths ─────────────────────────────────────────────────────────────
DOWNLOADS  = Path("C:/Users/Dell/Downloads")
DESKTOP    = Path("C:/Users/Dell/Desktop")
DOCUMENTS  = Path("C:/Users/Dell/Documents")
JARVIS_DIR = Path("E:/Himanshu Work/JARVIS_Phase1/JARVIS")

# ─── File type categories ──────────────────────────────────────────────────────
FILE_CATEGORIES = {
    "Images":     [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".ico", ".tiff"],
    "Videos":     [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v"],
    "Audio":      [".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a"],
    "Documents":  [".pdf", ".docx", ".doc", ".txt", ".pptx", ".ppt", ".xlsx", ".xls", ".odt"],
    "Code":       [".py", ".js", ".ts", ".html", ".css", ".cpp", ".c", ".h", ".java", ".json",
                   ".xml", ".yaml", ".yml", ".sh", ".bat", ".ps1", ".sql", ".php", ".rb", ".go"],
    "Archives":   [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"],
    "Executables":[".exe", ".msi", ".apk", ".dmg", ".deb"],
    "Others":     []
}

# Junk file patterns
JUNK_PATTERNS = [
    "*.tmp", "*.temp", "~*", "*.bak", "*.log",
    "desktop.ini", "thumbs.db", ".ds_store",
    "*.crdownload", "*.part"
]


# ─── File Search ──────────────────────────────────────────────────────────────

def search_file(filename: str, search_dirs: list = None) -> str:
    """Search for a file by name across common directories."""

    if not search_dirs:
        search_dirs = [
            DOWNLOADS, DESKTOP, DOCUMENTS,
            Path("C:/Users/Dell"),
            Path("E:/Himanshu Work"),
        ]

    filename_lower = filename.lower().strip()
    global last_search_results
    found = []

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        try:
            for file in search_dir.rglob("*"):
                if filename_lower in file.name.lower():
                    found.append(file)
                    if len(found) >= 5:  # limit results
                        break
        except PermissionError:
            continue
        if len(found) >= 5:
            break

    if not found:
        return f"No file found matching '{filename}', Sir."

    if len(found) == 1:
        # Open the file directly
        subprocess.Popen(f'explorer /select,"{found[0]}"', shell=True)
        return f"Found '{found[0].name}' at {found[0].parent}, Sir. Opening in Explorer."
    last_search_results = found
    # Multiple results
    results = "\n".join([f"  {i+1}. {f}" for i, f in enumerate(found)])
    return f"Found {len(found)} matches for '{filename}', Sir:\n{results}"

def open_by_number(number: int) -> str:
    """Open a file from last search results by number."""
    global last_search_results
    if not last_search_results:
        return "No recent search results, Sir. Search for a file first."
    idx = number - 1
    if idx < 0 or idx >= len(last_search_results):
        return f"No result number {number}, Sir. Search returned {len(last_search_results)} results."
    filepath = last_search_results[idx]
    try:
        os.startfile(str(filepath))
        return f"Opening '{filepath.name}', Sir."
    except Exception as e:
        return f"Could not open file, Sir: {e}"
def open_file(filepath: str) -> str:
    """Open a file with its default application."""
    filepath = filepath.strip().strip('"').strip("'")
    path = Path(filepath)

    # If full path given and exists — open directly
    if path.exists():
        os.startfile(str(path))
        return f"Opening '{path.name}', Sir."

    # Search in common folders
    search_dirs = [DOWNLOADS, DESKTOP, DOCUMENTS,
                   Path("C:/Users/Dell/Pictures"),
                   Path("C:/Users/Dell/Videos"),
                   Path("C:/Users/Dell/Music"),
                   Path("E:/Himanshu Work")]

    for d in search_dirs:
        if not d.exists():
            continue
        # Exact name match first
        candidate = d / filepath
        if candidate.exists():
            os.startfile(str(candidate))
            return f"Opening '{candidate.name}', Sir."
        # Search recursively
        try:
            for f in d.iterdir():
                # Only match FILES not folders, exact name match
                if f.is_file() and f.name.lower() == filepath.lower():
                    os.startfile(str(f))
                    return f"Opening '{f.name}' from {f.parent}, Sir."
                # One level deep
                if f.is_dir():
                    try:
                        for ff in f.iterdir():
                            if ff.is_file() and ff.name.lower() == filepath.lower():
                                os.startfile(str(ff))
                                return f"Opening '{ff.name}' from {ff.parent}, Sir."
                    except PermissionError:
                        continue
        except PermissionError:
            continue
    return f"Could not find '{filepath}', Sir. Try saying the full path."

def open_folder(folder_path: str) -> str:
    """Open a folder in File Explorer."""
    path = Path(folder_path)
    if path.exists():
        subprocess.Popen(f'explorer "{path}"', shell=True)
        return f"Opening {path.name} folder, Sir."
    return f"Folder not found: {folder_path}, Sir."


# ─── File Organization ────────────────────────────────────────────────────────

def organize_folder(folder_name: str = "downloads") -> str:
    """
    Auto-organize a folder by moving files into subfolders by type.
    e.g. Downloads → Images/, Videos/, Documents/, Code/, etc.
    """
    # Resolve folder path
    folder_map = {
        "downloads": DOWNLOADS,
        "download":  DOWNLOADS,
        "desktop":   DESKTOP,
        "documents": DOCUMENTS,
        "docs":      DOCUMENTS,
    }

    folder = folder_map.get(folder_name.lower().strip())
    if not folder:
        folder = Path(folder_name)

    if not folder.exists():
        return f"Folder '{folder_name}' not found, Sir."

    moved = 0
    skipped = 0

    for file in folder.iterdir():
        if file.is_dir():
            continue

        # Skip junk matching files
        if file.name.lower() in ["desktop.ini", "thumbs.db"]:
            continue

        # Find category
        ext = file.suffix.lower()
        category = "Others"
        for cat, extensions in FILE_CATEGORIES.items():
            if ext in extensions:
                category = cat
                break

        # Create category subfolder
        dest_folder = folder / category
        dest_folder.mkdir(exist_ok=True)

        # Move file
        dest = dest_folder / file.name
        # Handle duplicates
        if dest.exists():
            stem = file.stem
            suffix = file.suffix
            counter = 1
            while dest.exists():
                dest = dest_folder / f"{stem}_{counter}{suffix}"
                counter += 1

        try:
            shutil.move(str(file), str(dest))
            moved += 1
        except Exception:
            skipped += 1

    return (
        f"Organized '{folder.name}' folder, Sir. "
        f"Moved {moved} files into categories. "
        f"{skipped} files skipped."
    )


# ─── Delete Junk ──────────────────────────────────────────────────────────────

def delete_junk(folder_name: str = "downloads") -> str:
    """Delete temporary, junk and cache files from a folder."""
    folder_map = {
        "downloads": DOWNLOADS,
        "desktop":   DESKTOP,
        "documents": DOCUMENTS,
        "temp":      Path("C:/Windows/Temp"),
        "all":       None
    }

    target = folder_map.get(folder_name.lower().strip(), Path(folder_name))

    deleted = 0
    freed_bytes = 0

    def _delete_in(folder: Path):
        nonlocal deleted, freed_bytes
        if not folder.exists():
            return
        for pattern in JUNK_PATTERNS:
            for file in folder.glob(pattern):
                try:
                    size = file.stat().st_size
                    file.unlink()
                    deleted += 1
                    freed_bytes += size
                except Exception:
                    pass

    if target is None:
        # Delete from all common locations
        for folder in [DOWNLOADS, DESKTOP, Path("C:/Windows/Temp")]:
            _delete_in(folder)
    else:
        _delete_in(target)

    freed_mb = round(freed_bytes / (1024 * 1024), 2)
    return (
        f"Deleted {deleted} junk files, Sir. "
        f"Freed {freed_mb} MB of space."
    ) if deleted > 0 else "No junk files found, Sir. Everything looks clean."


def find_duplicates(folder_name: str = "downloads") -> str:
    """Find duplicate files in a folder by comparing MD5 hashes."""
    folder_map = {
        "downloads": DOWNLOADS,
        "desktop":   DESKTOP,
        "documents": DOCUMENTS,
    }

    folder = folder_map.get(folder_name.lower().strip(), Path(folder_name))
    if not folder.exists():
        return f"Folder '{folder_name}' not found, Sir."

    hashes = {}
    duplicates = []

    for file in folder.rglob("*"):
        if not file.is_file():
            continue
        try:
            md5 = hashlib.md5(file.read_bytes()).hexdigest()
            if md5 in hashes:
                duplicates.append((hashes[md5], file))
            else:
                hashes[md5] = file
        except Exception:
            pass

    if not duplicates:
        return f"No duplicate files found in '{folder.name}', Sir."

    # Delete duplicates
    deleted = 0
    freed = 0
    for original, duplicate in duplicates:
        try:
            freed += duplicate.stat().st_size
            duplicate.unlink()
            deleted += 1
        except Exception:
            pass

    freed_mb = round(freed / (1024 * 1024), 2)
    return (
        f"Found and deleted {deleted} duplicate files in '{folder.name}', Sir. "
        f"Freed {freed_mb} MB."
    )


# ─── Compress Files ───────────────────────────────────────────────────────────

def compress_folder(folder_name: str, output_name: str = None) -> str:
    """Compress a folder or file into a zip archive."""
    # Try to find the folder
    search_paths = [DOWNLOADS, DESKTOP, DOCUMENTS, Path("E:/Himanshu Work")]
    target = None

    for base in search_paths:
        candidate = base / folder_name
        if candidate.exists():
            target = candidate
            break

    if not target:
        # Try as absolute path
        target = Path(folder_name)
        if not target.exists():
            return f"Could not find '{folder_name}', Sir. Please specify the full path."

    # Output zip name
    if not output_name:
        output_name = f"{target.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    if not output_name.endswith(".zip"):
        output_name += ".zip"

    output_path = target.parent / output_name

    try:
        with zipfile.ZipFile(str(output_path), 'w', zipfile.ZIP_DEFLATED) as zf:
            if target.is_dir():
                for file in target.rglob("*"):
                    if file.is_file():
                        zf.write(file, file.relative_to(target.parent))
            else:
                zf.write(target, target.name)

        size_mb = round(output_path.stat().st_size / (1024 * 1024), 2)
        return (
            f"Compressed '{target.name}' to '{output_name}', Sir. "
            f"Archive size: {size_mb} MB. Saved at {output_path.parent}"
        )
    except Exception as e:
        return f"Compression failed, Sir: {e}"


def extract_zip(zip_path: str, dest_folder: str = None) -> str:
    """Extract a zip file."""
    zip_file = Path(zip_path)
    if not zip_file.exists():
        return f"Zip file not found: {zip_path}, Sir."

    dest = Path(dest_folder) if dest_folder else zip_file.parent / zip_file.stem
    dest.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(str(zip_file), 'r') as zf:
            zf.extractall(str(dest))
        return f"Extracted '{zip_file.name}' to '{dest}', Sir."
    except Exception as e:
        return f"Extraction failed, Sir: {e}"


# ─── Batch Rename ─────────────────────────────────────────────────────────────

def batch_rename(folder_name: str, pattern: str, prefix: str = "file") -> str:
    """
    Batch rename files in a folder.
    pattern: 'numbered' → file_001, file_002...
             'date'     → file_20240101_001...
             'prefix'   → just add prefix to existing names
    """
    folder_map = {
        "downloads": DOWNLOADS,
        "desktop":   DESKTOP,
        "documents": DOCUMENTS,
    }

    folder = folder_map.get(folder_name.lower().strip(), Path(folder_name))
    if not folder.exists():
        return f"Folder '{folder_name}' not found, Sir."

    files = sorted([f for f in folder.iterdir() if f.is_file()])
    if not files:
        return f"No files found in '{folder_name}', Sir."

    renamed = 0
    for i, file in enumerate(files, 1):
        ext = file.suffix
        if pattern == "numbered":
            new_name = f"{prefix}_{str(i).zfill(3)}{ext}"
        elif pattern == "date":
            date_str = datetime.now().strftime("%Y%m%d")
            new_name = f"{prefix}_{date_str}_{str(i).zfill(3)}{ext}"
        else:
            new_name = f"{prefix}_{file.name}"

        new_path = folder / new_name
        try:
            file.rename(new_path)
            renamed += 1
        except Exception:
            pass

    return f"Renamed {renamed} files in '{folder_name}', Sir."


# ─── Document Reader ──────────────────────────────────────────────────────────

def read_document(filepath: str) -> str:
    """Read and return text content from txt, pdf, or docx files."""
    path = Path(filepath)
    if not path.exists():
        # Try searching for it
        result = search_file(path.name)
        return f"File not found. {result}"

    ext = path.suffix.lower()

    try:
        if ext == ".txt":
            content = path.read_text(encoding="utf-8", errors="ignore")
            return content[:2000] + "..." if len(content) > 2000 else content

        elif ext == ".pdf":
            try:
                import pdfplumber
                with pdfplumber.open(str(path)) as pdf:
                    text = ""
                    for page in pdf.pages[:3]:  # first 3 pages
                        text += page.extract_text() or ""
                return text[:2000] + "..." if len(text) > 2000 else text
            except ImportError:
                # Fallback
                return f"PDF reading requires pdfplumber. Run: py -3.11 -m pip install pdfplumber"

        elif ext in (".docx", ".doc"):
            try:
                import docx
                doc = docx.Document(str(path))
                text = "\n".join([para.text for para in doc.paragraphs])
                return text[:2000] + "..." if len(text) > 2000 else text
            except ImportError:
                return "DOCX reading requires python-docx. Run: py -3.11 -m pip install python-docx"

        else:
            return f"Unsupported file type '{ext}', Sir. I can read .txt, .pdf, and .docx files."

    except Exception as e:
        return f"Could not read file, Sir: {e}"


def summarize_document(filepath: str, llm=None) -> str:
    """Read a document and summarize it using the LLM."""
    content = read_document(filepath)

    if content.startswith("File not found") or content.startswith("Unsupported"):
        return content

    if llm and llm.is_available():
        prompt = f"Summarize this document in 3-4 sentences:\n\n{content[:1500]}"
        summary = llm.ask_once(prompt)
        return f"Summary of '{Path(filepath).name}', Sir: {summary}"

    # No LLM — return first 300 chars
    return f"First part of '{Path(filepath).name}', Sir:\n{content[:300]}..."


# ─── Disk Info ────────────────────────────────────────────────────────────────

def get_disk_info() -> str:
    """Get disk usage info for all drives."""
    import psutil
    info = []
    for disk in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(disk.mountpoint)
            total_gb = round(usage.total / (1024**3), 1)
            free_gb  = round(usage.free  / (1024**3), 1)
            used_pct = usage.percent
            info.append(
                f"{disk.mountpoint} — {used_pct}% used, "
                f"{free_gb}GB free of {total_gb}GB"
            )
        except Exception:
            pass
    return "Disk status, Sir: " + " | ".join(info) if info else "Could not read disk info, Sir."


def get_large_files(folder_name: str = "downloads", min_size_mb: int = 100) -> str:
    """Find large files in a folder."""
    folder_map = {
        "downloads": DOWNLOADS,
        "desktop":   DESKTOP,
        "documents": DOCUMENTS,
    }
    folder = folder_map.get(folder_name.lower().strip(), Path(folder_name))
    if not folder.exists():
        return f"Folder not found, Sir."

    large = []
    for file in folder.rglob("*"):
        if file.is_file():
            try:
                size_mb = file.stat().st_size / (1024**2)
                if size_mb >= min_size_mb:
                    large.append((size_mb, file))
            except Exception:
                pass

    if not large:
        return f"No files larger than {min_size_mb}MB found in '{folder.name}', Sir."

    large.sort(reverse=True)
    result = "\n".join([f"  {round(s,1)}MB — {f.name}" for s, f in large[:5]])
    return f"Large files in '{folder.name}', Sir:\n{result}"


def count_files(folder_name: str = "downloads") -> str:
    """Count files in a folder by type."""
    folder_map = {
        "downloads": DOWNLOADS,
        "desktop":   DESKTOP,
        "documents": DOCUMENTS,
    }
    folder = folder_map.get(folder_name.lower().strip(), Path(folder_name))
    if not folder.exists():
        return f"Folder not found, Sir."

    counts = {}
    for file in folder.iterdir():
        if file.is_file():
            ext = file.suffix.lower() or "no extension"
            counts[ext] = counts.get(ext, 0) + 1

    total = sum(counts.values())
    top = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:5]
    top_str = ", ".join([f"{ext}: {n}" for ext, n in top])
    return f"'{folder.name}' has {total} files, Sir. Top types: {top_str}"
