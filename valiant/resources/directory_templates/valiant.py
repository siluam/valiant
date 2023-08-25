from pathlib import Path

dirs = next(
    directory
    for directory in sorted(Path("...").iterdir())
    if not (directory.name.startswith(".") or directory.name.startswith("_"))
)
