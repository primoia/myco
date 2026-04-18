#!/bin/bash
# Testes críticos para multi-channel mode

set -e
SWARM_DIR="/tmp/myco-test-critical"
PORT=9995

cleanup() {
    pkill -f "mycod.py.*$PORT" 2>/dev/null || true
    rm -rf "$SWARM_DIR"
}

trap cleanup EXIT

echo "=========================================="
echo "Testes Críticos - Multi-Channel"
echo "=========================================="

# Tokens
TOKEN1="myco-test-channel-alpha-secure-$(uuidgen)-2026"
TOKEN2="myco-test-channel-beta-secure-$(uuidgen)-2026"

# ==========================================
# Teste 1: Persistência (restart daemon)
# ==========================================
echo
echo "Teste 1: Persistência após restart"
echo "------------------------------------------"

cleanup
python3 mycod.py --multi-channel --port $PORT "$SWARM_DIR" > /dev/null 2>&1 &
DAEMON_PID=$!
sleep 2

# Criar dados no canal 1
curl -s -X POST \
    -H "Authorization: Bearer $TOKEN1" \
    -H "Content-Type: application/json" \
    -d '{"session":"ALICE","events":["start projeto-persistente"]}' \
    http://localhost:$PORT/events > /dev/null

echo "  - Criado evento no canal 1"

# Matar daemon
kill $DAEMON_PID 2>/dev/null
wait $DAEMON_PID 2>/dev/null || true
sleep 1

# Reiniciar daemon
python3 mycod.py --multi-channel --port $PORT "$SWARM_DIR" > /dev/null 2>&1 &
DAEMON_PID=$!
sleep 2

# Verificar se canal foi recarregado
CHANNELS=$(curl -s http://localhost:$PORT/healthz | python3 -c "import json,sys; print(json.load(sys.stdin)['channels'])")
if [ "$CHANNELS" -eq 1 ]; then
    echo "  ✓ Canal recarregado após restart (1 canal ativo)"
else
    echo "  ✗ FALHA: Esperava 1 canal, encontrou $CHANNELS"
    exit 1
fi

# Verificar se dados persistiram
VIEW=$(curl -s -H "Authorization: Bearer $TOKEN1" http://localhost:$PORT/view/ALICE)
if echo "$VIEW" | grep -q "projeto-persistente"; then
    echo "  ✓ Dados persistiram após restart"
else
    echo "  ✗ FALHA: Dados não persistiram"
    exit 1
fi

kill $DAEMON_PID 2>/dev/null
wait $DAEMON_PID 2>/dev/null || true

# ==========================================
# Teste 2: Token obrigatório
# ==========================================
echo
echo "Teste 2: Requisições sem token são rejeitadas (401)"
echo "------------------------------------------"

cleanup
python3 mycod.py --port $PORT "$SWARM_DIR" > /dev/null 2>&1 &
DAEMON_PID=$!
sleep 2

# healthz não requer auth
MODE=$(curl -s http://localhost:$PORT/healthz | python3 -c "import json,sys; print(json.load(sys.stdin).get('mode'))")
if [ "$MODE" = "multi-channel" ]; then
    echo "  ✓ /healthz responde sem auth e reporta multi-channel"
else
    echo "  ✗ FALHA: /healthz modo inesperado: $MODE"
    exit 1
fi

# POST /events sem Authorization → 401
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
    -H "Content-Type: application/json" \
    -d '{"session":"TEST","events":["start unauth"]}' \
    http://localhost:$PORT/events)
if [ "$HTTP_CODE" -eq 401 ]; then
    echo "  ✓ POST /events sem token retorna 401"
else
    echo "  ✗ FALHA: Esperava 401, obteve $HTTP_CODE"
    exit 1
fi

# GET /view/X sem token → 401
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$PORT/view/ANY)
if [ "$HTTP_CODE" -eq 401 ]; then
    echo "  ✓ GET /view/ sem token retorna 401"
else
    echo "  ✗ FALHA: Esperava 401, obteve $HTTP_CODE"
    exit 1
fi

kill $DAEMON_PID 2>/dev/null
wait $DAEMON_PID 2>/dev/null || true

# ==========================================
# Teste 3: Isolamento de Mensagens
# ==========================================
echo
echo "Teste 3: Isolamento de mensagens entre canais"
echo "------------------------------------------"

cleanup
python3 mycod.py --multi-channel --port $PORT "$SWARM_DIR" > /dev/null 2>&1 &
DAEMON_PID=$!
sleep 2

# Canal 1: criar mensagem
curl -s -X POST \
    -H "Authorization: Bearer $TOKEN1" \
    -d "Mensagem secreta do canal ALPHA" \
    http://localhost:$PORT/msg/ALPHA-001.md > /dev/null
echo "  - Mensagem criada no canal ALPHA"

# Canal 2: tentar ler mensagem do canal 1
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN2" \
    http://localhost:$PORT/msg/ALPHA-001.md)

if [ "$HTTP_CODE" -eq 404 ]; then
    echo "  ✓ Canal BETA não vê mensagens do ALPHA (404)"
else
    echo "  ✗ FALHA: Canal BETA conseguiu acessar msg do ALPHA (HTTP $HTTP_CODE)"
    exit 1
fi

# Canal 1: consegue ler sua própria mensagem
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN1" \
    "http://localhost:$PORT/msg/ALPHA-001.md?session=ALICE")

if [ "$HTTP_CODE" -eq 200 ]; then
    echo "  ✓ Canal ALPHA consegue ler suas próprias mensagens"
else
    echo "  ✗ FALHA: Canal ALPHA não conseguiu ler própria msg (HTTP $HTTP_CODE)"
    exit 1
fi

# ==========================================
# Teste 4: Múltiplas Sessões no Mesmo Canal
# ==========================================
echo
echo "Teste 4: Múltiplas sessões no mesmo canal"
echo "------------------------------------------"

# Sessão ALICE envia evento
curl -s -X POST \
    -H "Authorization: Bearer $TOKEN1" \
    -H "Content-Type: application/json" \
    -d '{"session":"ALICE","events":["start frontend"]}' \
    http://localhost:$PORT/events > /dev/null

# Sessão BOB (mesmo canal, token igual) envia evento
curl -s -X POST \
    -H "Authorization: Bearer $TOKEN1" \
    -H "Content-Type: application/json" \
    -d '{"session":"BOB","events":["start backend"]}' \
    http://localhost:$PORT/events > /dev/null

echo "  - ALICE e BOB criaram eventos (mesmo canal)"

# ALICE deve ver eventos do BOB (mesmo canal)
VIEW_ALICE=$(curl -s -H "Authorization: Bearer $TOKEN1" http://localhost:$PORT/view/ALICE)
if echo "$VIEW_ALICE" | grep -q "BOB"; then
    echo "  ✓ ALICE vê BOB no mesmo canal"
else
    echo "  ✗ FALHA: ALICE não vê BOB (mesmo canal)"
    exit 1
fi

# BOB deve ver eventos da ALICE (mesmo canal)
VIEW_BOB=$(curl -s -H "Authorization: Bearer $TOKEN1" http://localhost:$PORT/view/BOB)
if echo "$VIEW_BOB" | grep -q "ALICE"; then
    echo "  ✓ BOB vê ALICE no mesmo canal"
else
    echo "  ✗ FALHA: BOB não vê ALICE (mesmo canal)"
    exit 1
fi

kill $DAEMON_PID 2>/dev/null
wait $DAEMON_PID 2>/dev/null || true

echo
echo "=========================================="
echo "✓ Todos os testes críticos passaram!"
echo "=========================================="
