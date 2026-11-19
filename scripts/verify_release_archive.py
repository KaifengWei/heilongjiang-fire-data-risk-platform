"""Validate a Windows onedir release ZIP against the *actual* built bundle.

The build and EXE self-test run first. This final gate catches incomplete
Compress-Archive output, renamed roots, CRC failures, unexpected files,
missing map assets or a different EXE than the one successfully self-tested.
No uploaded FIRMS data, user history or %LOCALAPPDATA% paths are inspected.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys
from zipfile import BadZipFile, ZipFile

if __package__:
    from .verify_windows_bundle import REQUIRED_FILES, missing_bundle_items
else:
    from verify_windows_bundle import REQUIRED_FILES, missing_bundle_items


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _digest_member(archive: ZipFile, name: str) -> str:
    digest = hashlib.sha256()
    with archive.open(name) as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_release_archive(app_dir: Path, zip_path: Path) -> dict[str, int | str]:
    app_dir = Path(app_dir)
    zip_path = Path(zip_path)
    missing = missing_bundle_items(app_dir)
    if missing:
        raise ValueError("Built application is incomplete: " + ", ".join(missing))
    if not zip_path.is_file():
        raise FileNotFoundError("Missing release ZIP: " + str(zip_path))

    root = app_dir.name + "/"
    disk_files = {
        path.relative_to(app_dir).as_posix(): path
        for path in app_dir.rglob("*") if path.is_file()
    }
    exe_name = app_dir.name + ".exe"
    must_check = {exe_name, *(f"_internal/{part}" for part in REQUIRED_FILES)}
    if not must_check.issubset(disk_files):
        raise ValueError("Built folder is missing a mandatory release file")

    try:
        with ZipFile(zip_path, "r") as archive:
            members = [item for item in archive.infolist() if not item.is_dir()]
            names = [item.filename.replace("\\", "/") for item in members]
            if len(names) != len(set(names)):
                raise ValueError("ZIP contains duplicate file paths")
            if any(
                not name.startswith(root)
                or name.endswith("/")
                or "." in name.split("/")[:-1]
                or ".." in name.split("/")
                for name in names
            ):
                raise ValueError("ZIP has a file outside its application folder")

            archive_files = {name[len(root):]: item for name, item in zip(names, members)}
            missing_files = set(disk_files) - set(archive_files)
            extra_files = set(archive_files) - set(disk_files)
            if missing_files or extra_files:
                details = (
                    f"missing={sorted(missing_files)[:5]}, "
                    f"unexpected={sorted(extra_files)[:5]}"
                )
                raise ValueError("ZIP and built folder differ: " + details)
            for name, disk_file in disk_files.items():
                if archive_files[name].file_size != disk_file.stat().st_size:
                    raise ValueError("ZIP file size differs: " + name)

            bad_member = archive.testzip()
            if bad_member:
                raise ValueError("ZIP CRC failed: " + bad_member)

            # A CRC check detects corruption; the SHA comparison also ensures
            # these published bits are the ones that passed the EXE self-test.
            for rel in sorted(must_check):
                if _digest_file(disk_files[rel]) != _digest_member(archive, root + rel):
                    raise ValueError("ZIP contents differ from built file: " + rel)
    except BadZipFile as exc:
        raise ValueError("Invalid ZIP archive") from exc

    return {
        "files": len(disk_files),
        "required": len(must_check),
        "archive_bytes": zip_path.stat().st_size,
        "zip_sha256": _digest_file(zip_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify full onedir Windows release ZIP.")
    parser.add_argument("--app-dir", type=Path, required=True)
    parser.add_argument("--zip-path", type=Path, required=True)
    options = parser.parse_args(argv)
    try:
        result = verify_release_archive(options.app_dir, options.zip_path)
    except (OSError, ValueError) as exc:
        print("RELEASE ZIP VERIFICATION FAILED:", exc, file=sys.stderr)
        return 1
    print(
        "Release ZIP verified:",
        result["files"], "files;",
        result["required"], "critical resources;",
        result["archive_bytes"], "bytes",
    )
    print("ZIP SHA256:", result["zip_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
