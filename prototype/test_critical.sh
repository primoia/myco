#!/bin/bash
# Testes críticos para multi-tenant mode

set -e
SWARM_DIR="/tmp/myco-test-critical"
PORT=9995

cleanup() {
    pkill -f "mycod.py.*$PORT" 2>/dev/null || true
    rm -rf "$SWARM_DIR"
}

trap cleanup EXIT

echo "=========================================="
echo "Testes Críticos - Multi-Tenant"
echo "=========================================="

# Tokens
TOKEN1="myco-test-tenant-alpha-secure-$(uuidgen)-2026"
TOKEN2="myco-test-tenant-beta-secure-$(uuidgen)-2026"

# ==========================================
# Teste 1: Persistência (restart daemon)
# ==========================================
echo
echo "Teste 1: Persistência após restart"
echo "------------------------------------------"

cleanup
python3 mycod.py --multi-tenant --port $PORT "$SWARM_DIR" > /dev/null 2>&1 &
DAEMON_PID=$!
sleep 2

# Criar dados no tenant 1
curl -s -X POST \
    -H "Authorization: Bearer $TOKEN1" \
    -H "Content-Type: application/json" \
    -d '{"session":"ALICE","events":["start projeto-persistente"]}' \
    http://localhost:$PORT/events > /dev/null

echo "  - Criado evento no tenant 1"

# Matar daemon
kill $DAEMON_PID 2>/dev/null
wait $DAEMON_PID 2>/dev/null || true
sleep 1

# Reiniciar daemon
python3 mycod.py --multi-tenant --port $PORT "$SWARM_DIR" > /dev/null 2>&1 &
DAEMON_PID=$!
sleep 2

# Verificar se tenant foi recarregado
TENANTS=$(curl -s http://localhost:$PORT/healthz | python3 -c "import json,sys; print(json.load(sys.stdin)['tenants'])")
if [ "$TENANTS" -eq 1 ]; then
    echo "  ✓ Tenant recarregado após restart (1 tenant ativo)"
else
    echo "  ✗ FALHA: Esperava 1 tenant, encontrou $TENANTS"
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
# Teste 2: Backward Compatibility
# ==========================================
echo
echo "Teste 2: Backward compatibility (single-tenant)"
echo "------------------------------------------"

cleanup
SWARM_SINGLE="/tmp/myco-test-single"
rm -rf "$SWARM_SINGLE"

# Rodar em modo single-tenant (SEM --multi-tenant)
python3 mycod.py --port $PORT "$SWARM_SINGLE" > /dev/null 2>&1 &
DAEMON_PID=$!
sleep 2

# Criar evento sem token
curl -s -X POST \
    -H "Content-Type: application/json" \
    -d '{"session":"TEST","events":["start single-mode"]}' \
    http://localhost:$PORT/events > /dev/null

# Verificar healthz
MODE=$(curl -s http://localhost:$PORT/healthz | python3 -c "import json,sys; print(json.load(sys.stdin).get('mode', 'single-tenant'))")
if [ "$MODE" = "single-tenant" ]; then
    echo "  ✓ Modo single-tenant funciona"
else
    echo "  ✗ FALHA: Modo deveria ser single-tenant, obteve: $MODE"
    exit 1
fi

# Verificar estrutura (não deve ter tenants/)
if [ ! -d "$SWARM_SINGLE/tenants" ]; then
    echo "  ✓ Estrutura single-tenant correta (sem tenants/)"
else
    echo "  ✗ FALHA: Modo single criou tenants/ indevidamente"
    exit 1
fi

kill $DAEMON_PID 2>/dev/null
wait $DAEMON_PID 2>/dev/null || true
rm -rf "$SWARM_SINGLE"

# ==========================================
# Teste 3: Isolamento de Mensagens
# ==========================================
echo
echo "Teste 3: Isolamento de mensagens entre tenants"
echo "------------------------------------------"

cleanup
python3 mycod.py --multi-tenant --port $PORT "$SWARM_DIR" > /dev/null 2>&1 &
DAEMON_PID=$!
sleep 2

# Tenant 1: criar mensagem
curl -s -X POST \
    -H "Authorization: Bearer $TOKEN1" \
    -d "Mensagem secreta do tenant ALPHA" \
    http://localhost:$PORT/msg/ALPHA-001.md > /dev/null
echo "  - Mensagem criada no tenant ALPHA"

# Tenant 2: tentar ler mensagem do tenant 1
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN2" \
    http://localhost:$PORT/msg/ALPHA-001.md)

if [ "$HTTP_CODE" -eq 404 ]; then
    echo "  ✓ Tenant BETA não vê mensagens do ALPHA (404)"
else
    echo "  ✗ FALHA: Tenant BETA conseguiu acessar msg do ALPHA (HTTP $HTTP_CODE)"
    exit 1
fi

# Tenant 1: consegue ler sua própria mensagem
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN1" \
    "http://localhost:$PORT/msg/ALPHA-001.md?session=ALICE")

if [ "$HTTP_CODE" -eq 200 ]; then
    echo "  ✓ Tenant ALPHA consegue ler suas próprias mensagens"
else
    echo "  ✗ FALHA: Tenant ALPHA não conseguiu ler própria msg (HTTP $HTTP_CODE)"
    exit 1
fi

# ==========================================
# Teste 4: Múltiplas Sessões no Mesmo Tenant
# ==========================================
echo
echo "Teste 4: Múltiplas sessões no mesmo tenant"
echo "------------------------------------------"

# Sessão ALICE envia evento
curl -s -X POST \
    -H "Authorization: Bearer $TOKEN1" \
    -H "Content-Type: application/json" \
    -d '{"session":"ALICE","events":["start frontend"]}' \
    http://localhost:$PORT/events > /dev/null

# Sessão BOB (mesmo tenant, token igual) envia evento
curl -s -X POST \
    -H "Authorization: Bearer $TOKEN1" \
    -H "Content-Type: application/json" \
    -d '{"session":"BOB","events":["start backend"]}' \
    http://localhost:$PORT/events > /dev/null

echo "  - ALICE e BOB criaram eventos (mesmo tenant)"

# ALICE deve ver eventos do BOB (mesmo tenant)
VIEW_ALICE=$(curl -s -H "Authorization: Bearer $TOKEN1" http://localhost:$PORT/view/ALICE)
if echo "$VIEW_ALICE" | grep -q "BOB"; then
    echo "  ✓ ALICE vê BOB no mesmo tenant"
else
    echo "  ✗ FALHA: ALICE não vê BOB (mesmo tenant)"
    exit 1
fi

# BOB deve ver eventos da ALICE (mesmo tenant)
VIEW_BOB=$(curl -s -H "Authorization: Bearer $TOKEN1" http://localhost:$PORT/view/BOB)
if echo "$VIEW_BOB" | grep -q "ALICE"; then
    echo "  ✓ BOB vê ALICE no mesmo tenant"
else
    echo "  ✗ FALHA: BOB não vê ALICE (mesmo tenant)"
    exit 1
fi

kill $DAEMON_PID 2>/dev/null
wait $DAEMON_PID 2>/dev/null || true

echo
echo "=========================================="
echo "✓ Todos os testes críticos passaram!"
echo "=========================================="
