#!/bin/sh
if [ "${MCP_TRANSPORT:-http}" = "http" ]; then
    curl -s -o /dev/null --max-time 5 "http://127.0.0.1:${MCP_PORT:-8770}${MCP_PATH:-/mcp}" && exit 0
    exit 1
fi
kill -0 1 2>/dev/null
