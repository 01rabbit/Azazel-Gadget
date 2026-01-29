#!/bin/bash
# Reprobe: Force re-probing of network
curl -s http://127.0.0.1:8082/action/reprobe 2>/dev/null || true
echo "Reprobe initiated"
