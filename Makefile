# Convenience targets. The canonical one-command entry point is `make up`
# (== docker compose up --build). The others drive the tooling.

.PHONY: up down solve grade test calibrate local deps

up:            ## build + run the challenge (edge on :8080, collector internal)
	docker compose up --build

down:          ## stop and remove the challenge containers/networks
	docker compose down -v

deps:          ## install the tooling deps (solution / grader / calibration)
	pip install -r requirements-tools.txt

solve:         ## run the reference solution against a running challenge
	python solution/solve.py --base http://localhost:8080 --transcript run.json

grade:         ## grade the last transcript against the rubric
	python rubric/grader.py --rubric rubric/rubric.yaml --transcript run.json

test:          ## run grader-monotonicity + guardrail tests (starts a local stack)
	python calibration/test_grader.py
	python calibration/run_local.py & sleep 4; \
	python calibration/test_guardrails.py; kill %1

calibrate:     ## measure reliability + difficulty band, write calibration/report.md
	python calibration/calibrate.py --reliability-runs 16 --rollouts 100

local:         ## run edge + collector as local processes (no Docker)
	python calibration/run_local.py
