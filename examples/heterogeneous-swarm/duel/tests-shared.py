"""Suíte oficial do desafio LRU. Cada arena copia este arquivo pro seu cwd
e roda com `python3 -m pytest tests-shared.py -q`. 9 testes — só posta done
quando todos verdes."""

import pytest
from lru import LRUCache


def test_basic_put_and_get():
    c = LRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    assert c.get("a") == 1
    assert c.get("b") == 2


def test_miss_raises_keyerror():
    c = LRUCache(2)
    with pytest.raises(KeyError):
        c.get("missing")


def test_eviction_least_recently_used():
    """Inserir além da capacidade descarta o LRU."""
    c = LRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    c.put("c", 3)        # "a" deveria ser evicted
    assert "a" not in c
    assert c.get("b") == 2
    assert c.get("c") == 3


def test_get_marks_as_recent():
    """get(k) deve mover k pra most-recent — não pode ser evicted antes do que veio depois."""
    c = LRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    c.get("a")           # toca "a" — agora "b" é o LRU
    c.put("c", 3)        # "b" deveria ser evicted, não "a"
    assert "a" in c
    assert "b" not in c
    assert "c" in c


def test_put_existing_updates_and_marks_recent():
    """put numa chave existente atualiza valor E marca como mais-recente."""
    c = LRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    c.put("a", 99)       # atualiza valor + marca como mais-recente
    c.put("c", 3)        # "b" deveria ser evicted (não "a")
    assert c.get("a") == 99
    assert "b" not in c
    assert "c" in c


def test_capacity_zero_stores_nothing():
    """Cache com capacity=0 nunca armazena."""
    c = LRUCache(0)
    c.put("a", 1)
    assert "a" not in c
    assert len(c) == 0
    with pytest.raises(KeyError):
        c.get("a")


def test_capacity_negative_raises():
    with pytest.raises(ValueError):
        LRUCache(-1)


def test_len_reflects_size():
    c = LRUCache(3)
    assert len(c) == 0
    c.put("a", 1)
    assert len(c) == 1
    c.put("b", 2)
    c.put("c", 3)
    assert len(c) == 3
    c.put("d", 4)        # evict
    assert len(c) == 3   # still capped


def test_contains_does_not_mark_recent():
    """`in` operator (__contains__) não deve marcar como mais-recente.
    (Apenas get e put fazem isso.)"""
    c = LRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    _ = "a" in c         # consulta — NÃO deve mexer na ordem
    c.put("c", 3)        # "a" continua sendo o LRU → evicted
    assert "a" not in c
    assert "b" in c
    assert "c" in c
