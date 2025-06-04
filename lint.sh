#!/usr/bin/env bash
set -e

echo "Running black…"
black --check echogit/

echo "Running flake8…"
flake8 echogit/

echo "Running isort…"
isort --check-only echogit/

echo "Running pylint…"
pylint echogit/

echo "Running mypy…"
mypy echogit/

echo "Running bandit…"
bandit -r echogit/ -q

echo "✅ All checks passed!"
