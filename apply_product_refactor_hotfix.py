from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil

ROOT = Path.cwd()


def read(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        raise RuntimeError(f"Required file not found: {rel}")
    return path.read_text(encoding="utf-8")


def write(rel: str, text: str) -> None:
    path = ROOT / rel
    path.write_text(text, encoding="utf-8")


def backup_files(paths: list[str]) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = ROOT / "data" / "runtime" / f"product_refactor_hotfix_backup_{stamp}"
    for rel in paths:
        source = ROOT / rel
        if not source.is_file():
            raise RuntimeError(f"Cannot back up missing file: {rel}")
        target = backup_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return backup_root


TOUCH = [
    "src/fire_monitor/services/statistics_service.py",
    "tests/test_mcd64_storage.py",
]

backup_root = backup_files(TOUCH)

# -----------------------------------------------------------------------------
# Fix 1: task-scoped FIRMS statistics must support both the new explicit
# run-membership table and the pre-existing source-provenance path.
#
# Why both?
# - New/repeated analyses need active_fire_run_membership so reused canonical
#   observations still belong to the new analysis record.
# - Existing code/tests and legacy programmatic inserts may only have
#   active_fire_observation_sources -> import_runs provenance.
# UNION de-duplicates observation IDs, so using both paths does not double count.
# -----------------------------------------------------------------------------
stats_rel = "src/fire_monitor/services/statistics_service.py"
stats = read(stats_rel)

old_cte = '''                WITH task_observations AS (\n                    SELECT DISTINCT membership.observation_id\n                    FROM active_fire_run_membership AS membership\n                    JOIN import_runs AS run\n                        ON run.id = membership.run_id\n                    WHERE run.task_id = ?\n                      AND run.data_kind = 'active_fire_observations'\n                      AND run.status = 'completed'\n                )\n'''

new_cte = '''                WITH task_observations AS (\n                    SELECT membership.observation_id\n                    FROM active_fire_run_membership AS membership\n                    JOIN import_runs AS run\n                        ON run.id = membership.run_id\n                    WHERE run.task_id = ?\n                      AND run.data_kind = 'active_fire_observations'\n                      AND run.status = 'completed'\n\n                    UNION\n\n                    SELECT source.observation_id\n                    FROM active_fire_observation_sources AS source\n                    JOIN import_runs AS run\n                        ON run.id = source.import_run_id\n                    WHERE run.task_id = ?\n                      AND run.data_kind = 'active_fire_observations'\n                      AND run.status = 'completed'\n                )\n'''

if old_cte in stats:
    count = stats.count(old_cte)
    if count != 2:
        raise RuntimeError(
            "statistics_service.py: expected 2 unpatched task_observations CTEs, "
            f"found {count}. No file was written."
        )
    stats = stats.replace(old_cte, new_cte)

    # Each updated CTE now contains two task_id placeholders instead of one.
    # Both task_region_statistics() and task_daily_series() originally pass
    # `(task_id,)` immediately after the relevant query.
    marker = '''                (task_id,),\n            ).fetchall()\n'''
    marker_count = stats.count(marker)
    if marker_count < 4:
        # There are also MCD64 queries using one placeholder. We only patch the
        # first FIRMS query in each method via contextual replacement below.
        pass

    # Contextual replacements: one in task_region_statistics, one in
    # task_daily_series. Avoid altering MCD64 query parameter tuples.
    region_context_old = '''                GROUP BY observation.region_name\n                """,\n                (task_id,),\n            ).fetchall()\n'''
    region_context_new = '''                GROUP BY observation.region_name\n                """,\n                (task_id, task_id),\n            ).fetchall()\n'''
    if stats.count(region_context_old) != 1:
        raise RuntimeError(
            "statistics_service.py: region statistics parameter anchor not unique."
        )
    stats = stats.replace(region_context_old, region_context_new, 1)

    daily_context_old = '''                GROUP BY observation.acquired_date\n                ORDER BY observation.acquired_date\n                """,\n                (task_id,),\n            ).fetchall()\n'''
    daily_context_new = '''                GROUP BY observation.acquired_date\n                ORDER BY observation.acquired_date\n                """,\n                (task_id, task_id),\n            ).fetchall()\n'''
    if stats.count(daily_context_old) != 1:
        raise RuntimeError(
            "statistics_service.py: daily series parameter anchor not unique."
        )
    stats = stats.replace(daily_context_old, daily_context_new, 1)

elif "UNION\n\n                    SELECT source.observation_id" in stats:
    print("[SKIP] statistics_service.py already contains compatibility UNION")
else:
    raise RuntimeError(
        "statistics_service.py: expected task membership CTE not found; "
        "stopping instead of guessing."
    )

write(stats_rel, stats)
print("[UPDATED]", stats_rel)


# -----------------------------------------------------------------------------
# Fix 2: schema version is intentionally v4 after adding FIRMS run membership.
# The old MCD64 migration test still expected v3; update only that expectation.
# -----------------------------------------------------------------------------
test_rel = "tests/test_mcd64_storage.py"
test_text = read(test_rel)

old = "assert version == 3"
new = "assert version == 4"

if old in test_text:
    count = test_text.count(old)
    if count != 1:
        raise RuntimeError(
            f"{test_rel}: expected exactly one `{old}`, found {count}."
        )
    test_text = test_text.replace(old, new, 1)
elif new in test_text:
    print(f"[SKIP] {test_rel} already expects schema v4")
else:
    raise RuntimeError(
        f"{test_rel}: schema-version assertion not found; stopping instead of guessing."
    )

write(test_rel, test_text)
print("[UPDATED]", test_rel)

print()
print("Product refactor hotfix applied successfully.")
print("Backup directory:")
print(backup_root)
print()
print("Next: run pytest -q once.")
