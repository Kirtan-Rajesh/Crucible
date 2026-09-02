# Crucible convenience targets. TASK defaults to the reference task.
# All targets are thin wrappers over `python -m harness.cli`.

TASK ?= edge-pivot
PY   ?= python

.PHONY: deps solve grade calibrate gate verify up down test

deps:        ## install the harness/tooling deps
	$(PY) -m pip install -r requirements-tools.txt

solve:       ## solve TASK and grade the run (local env)
	$(PY) -m harness.cli solve $(TASK)

up:          ## build + run TASK's containers (Docker or Podman)
	$(PY) -m harness.cli up $(TASK)

down:        ## stop + remove TASK's containers
	$(PY) -m harness.cli down $(TASK)

calibrate:   ## measure reliability + difficulty band -> report.json/report.md
	$(PY) -m harness.cli calibrate $(TASK)

gate:        ## enforce TASK's acceptance targets (non-zero exit on FAIL)
	$(PY) -m harness.cli gate $(TASK)

verify:      ## tests + calibrate + gate (the full local check)
	$(PY) -m harness.cli verify $(TASK)

grade:       ## grade an existing transcript: make grade TRANSCRIPT=run.json
	$(PY) -m harness.cli grade $(TASK) --transcript $(TRANSCRIPT)
