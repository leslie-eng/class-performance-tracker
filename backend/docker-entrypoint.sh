#!/bin/sh
set -e
# Bring the schema up to date before the API (or a one-off command) starts.
alembic upgrade head
exec "$@"
