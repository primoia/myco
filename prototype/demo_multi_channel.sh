#!/bin/bash
# Demonstração prática de multi-channel mode

set -e

SWARM_DIR="/tmp/myco-demo"
PORT=8888

cleanup() {
    pkill -f "mycod.py.*$PORT" 2>/dev/null || true
    rm -rf "$SWARM_DIR"
}

trap cleanup EXIT

echo "=========================================="
echo "Demo: Multi-Channel Mode"
echo "=========================================="
echo

# Gerar tokens seguros
TOKEN_FRONTEND=$(python3 -c "import secrets; print('myco-frontend-' + secrets.token_urlsafe(24))")
TOKEN_BACKEND=$(python3 -c "import secrets; print('myco-backend-' + secrets.token_urlsafe(24))")

echo "Tokens gerados (boa entropia):"
echo "  Frontend: ${TOKEN_FRONTEND:0:30}..."
echo "  Backend:  ${TOKEN_BACKEND:0:30}..."
echo

cleanup
echo "Iniciando daemon em modo multi-channel..."
python3 mycod.py --multi-channel --port $PORT "$SWARM_DIR" > /dev/null 2>&1 &
DAEMON_PID=$!
sleep 2
echo "✓ Daemon rodando na porta $PORT"
echo

# Simular time Frontend
echo "=== Time Frontend (canal isolado) ==="
curl -s -X POST \
    -H "Authorization: Bearer $TOKEN_FRONTEND" \
    -H "Content-Type: application/json" \
    -d '{"session":"REACT","events":["start componente-login"]}' \
    http://localhost:$PORT/events > /dev/null

curl -s -X POST \
    -H "Authorization: Bearer $TOKEN_FRONTEND" \
    -H "Content-Type: application/json" \
    -d '{"session":"DESIGN","events":["start wireframes"]}' \
    http://localhost:$PORT/events > /dev/null

echo "  - REACT: iniciou componente-login"
echo "  - DESIGN: iniciou wireframes"
echo

# Simular time Backend
echo "=== Time Backend (canal isolado) ==="
curl -s -X POST \
    -H "Authorization: Bearer $TOKEN_BACKEND" \
    -H "Content-Type: application/json" \
    -d '{"session":"API","events":["start endpoint-auth"]}' \
    http://localhost:$PORT/events > /dev/null

curl -s -X POST \
    -H "Authorization: Bearer $TOKEN_BACKEND" \
    -H "Content-Type: application/json" \
    -d '{"session":"DB","events":["start migration-users"]}' \
    http://localhost:$PORT/events > /dev/null

echo "  - API: iniciou endpoint-auth"
echo "  - DB: iniciou migration-users"
echo

# Verificar isolamento
echo "=== Verificando Isolamento ==="

VIEW_REACT=$(curl -s -H "Authorization: Bearer $TOKEN_FRONTEND" http://localhost:$PORT/view/REACT)
if echo "$VIEW_REACT" | grep -q "DESIGN" && ! echo "$VIEW_REACT" | grep -q "API"; then
    echo "  ✓ REACT vê DESIGN (mesmo canal)"
    echo "  ✓ REACT NÃO vê API (canal diferente)"
else
    echo "  ✗ FALHA no isolamento"
fi

VIEW_API=$(curl -s -H "Authorization: Bearer $TOKEN_BACKEND" http://localhost:$PORT/view/API)
if echo "$VIEW_API" | grep -q "DB" && ! echo "$VIEW_API" | grep -q "REACT"; then
    echo "  ✓ API vê DB (mesmo canal)"
    echo "  ✓ API NÃO vê REACT (canal diferente)"
else
    echo "  ✗ FALHA no isolamento"
fi
echo

# Status do daemon
echo "=== Status do Daemon ==="
HEALTH=$(curl -s http://localhost:$PORT/healthz)
echo "  Modo: $(echo $HEALTH | python3 -c "import json,sys; print(json.load(sys.stdin)['mode'])")"
echo "  Canais ativos: $(echo $HEALTH | python3 -c "import json,sys; print(json.load(sys.stdin)['channels'])")"
echo

echo "=========================================="
echo "✓ Demo concluída!"
echo "=========================================="
echo
echo "Estrutura criada:"
ls -1 "$SWARM_DIR/channels/"
echo
echo "Cada hash SHA256 representa um canal isolado."
