#!/bin/bash
echo "=== [$(date)] STARTING MARKET AI AUTOMATION SERVICE ==="

echo "Running crawler for iNet..."
python3 /opt/market-ai/crawler/providers/inet.py

echo "Running crawler for PA..."
python3 /opt/market-ai/crawler/providers/pa.py

echo "Running crawler for MatBao..."
python3 /opt/market-ai/crawler/providers/matbao.py

echo "Running crawler for Vietnix..."
python3 /opt/market-ai/crawler/providers/vietnix.py

echo "=== [$(date)] MARKET AI AUTOMATION SERVICE COMPLETED ==="
