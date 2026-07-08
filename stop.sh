#!/bin/sh
# Stop everything for this project: containers + network (keeps volumes/images).
cd "$(dirname "$0")"
docker compose down
