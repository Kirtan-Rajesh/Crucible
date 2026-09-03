"""
Crucible schema-validate command.

Validates a task's manifest and rubric against harness/schema/*.json before
anything is calibrated or gated -- catches a malformed rubric (bad check DSL,
missing solved_stage, fewer than the minimum gradable stages) with a precise
error instead of a confusing downstream grader/calibrator failure.

Usage:
    python -m harness.validate <task_dir_or_name>
"""
import json
import pathlib
import sys

import jsonschema
import yaml

SCHEMA_DIR = pathlib.Path(__file__).resolve().parent / "schema"


def _load_schema(name):
    with (SCHEMA_DIR / name).open(encoding="utf-8") as fh:
        return json.load(fh)


def validate_task(task_dir):
    """Validate task.yaml and its referenced rubric.yaml. Returns a list of
    error strings (empty means valid)."""
    task_dir = pathlib.Path(task_dir)
    errors = []

    task_schema = _load_schema("task.schema.json")
    rubric_schema = _load_schema("rubric.schema.json")

    manifest_path = task_dir / "task.yaml"
    if not manifest_path.exists():
        return [f"{manifest_path}: no such file"]
    with manifest_path.open(encoding="utf-8") as fh:
        manifest = yaml.safe_load(fh)

    for err in jsonschema.Draft7Validator(task_schema).iter_errors(manifest):
        errors.append(f"task.yaml: {err.message} (at {'/'.join(str(p) for p in err.path)})")

    rubric_rel = manifest.get("rubric") if isinstance(manifest, dict) else None
    if rubric_rel:
        rubric_path = task_dir / rubric_rel
        if not rubric_path.exists():
            errors.append(f"rubric file '{rubric_rel}' referenced by task.yaml does not exist")
        else:
            with rubric_path.open(encoding="utf-8") as fh:
                rubric = yaml.safe_load(fh)
            for err in jsonschema.Draft7Validator(rubric_schema).iter_errors(rubric):
                errors.append(f"{rubric_rel}: {err.message} (at {'/'.join(str(p) for p in err.path)})")

            # Cross-checks a JSON Schema can't express on its own.
            if isinstance(rubric, dict):
                stage_ids = {s.get("id") for s in rubric.get("stages", []) if isinstance(s, dict)}
                solved_stage = rubric.get("meta", {}).get("solved_stage")
                if solved_stage and solved_stage not in stage_ids:
                    errors.append(f"{rubric_rel}: meta.solved_stage "
                                  f"'{solved_stage}' is not a defined stage id")
                orders = [s.get("order") for s in rubric.get("stages", []) if isinstance(s, dict)]
                if sorted(orders) != list(range(1, len(orders) + 1)):
                    errors.append(f"{rubric_rel}: stage 'order' values must be "
                                  f"a contiguous 1..N sequence, got {orders}")
                for guard in rubric.get("guards", []):
                    target = guard.get("forbidden_before")
                    if target not in stage_ids:
                        errors.append(f"{rubric_rel}: guard '{guard.get('id')}' "
                                      f"forbidden_before '{target}' is not a defined stage id")

    return errors


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("task_dir")
    args = ap.parse_args(argv)

    errors = validate_task(args.task_dir)
    if errors:
        print(f"INVALID -- {len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"VALID: {args.task_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
