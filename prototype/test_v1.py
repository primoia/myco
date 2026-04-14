#!/usr/bin/env python3
"""Tests for myco protocol v1 features."""

import tempfile
from pathlib import Path

from mycod import (
    parse_event, parse_detail_kvs, SwarmIndex, render_view,
    write_view_atomic,
)


# ============================================================
# parse_detail_kvs
# ============================================================

class TestParseDetailKvs:
    def test_basic(self):
        text, kvs = parse_detail_kvs("auth-api-v2 ref:origin/feat/login spec:msg/AUTH-001.md")
        assert kvs == {"ref": "origin/feat/login", "spec": "msg/AUTH-001.md"}
        assert text == "auth-api-v2"

    def test_empty_string(self):
        text, kvs = parse_detail_kvs("")
        assert kvs == {}
        assert text == ""

    def test_no_kvs(self):
        text, kvs = parse_detail_kvs("just plain text here")
        assert kvs == {}
        assert text == "just plain text here"

    def test_single_kv_ack(self):
        text, kvs = parse_detail_kvs("recebido ack:msg/CART-001.md")
        assert kvs == {"ack": "msg/CART-001.md"}
        assert text == "recebido"

    def test_only_kvs_no_free_text(self):
        text, kvs = parse_detail_kvs("ref:origin/main spec:msg/X.md")
        assert kvs == {"ref": "origin/main", "spec": "msg/X.md"}
        assert text == ""

    def test_kv_at_start(self):
        text, kvs = parse_detail_kvs("ref:branch some text after")
        assert kvs == {"ref": "branch"}
        assert "some text after" in text

    def test_duplicate_key_last_wins(self):
        """If same key appears twice, last match wins (regex finditer order)."""
        text, kvs = parse_detail_kvs("ref:first ref:second")
        assert kvs["ref"] == "second"

    def test_kv_with_special_chars_in_value(self):
        text, kvs = parse_detail_kvs("ref:origin/feat/my-branch_v2.0")
        assert kvs["ref"] == "origin/feat/my-branch_v2.0"

    def test_mixed_text_and_multiple_kvs(self):
        text, kvs = parse_detail_kvs("deploying service ref:v1.2.3 msg:msg/DEPLOY-001.md to production")
        assert kvs == {"ref": "v1.2.3", "msg": "msg/DEPLOY-001.md"}
        assert "deploying" in text
        assert "service" in text
        assert "to" in text
        assert "production" in text


# ============================================================
# parse_event
# ============================================================

class TestParseEvent:
    def test_with_kvs(self):
        ev = parse_event("AUTH", "2025-01-01T00:00:00 AUTH done auth-api-v2 ref:origin/feat/login spec:msg/AUTH-001.md")
        assert ev is not None
        assert ev["verb"] == "done"
        assert ev["obj"] == "auth-api-v2"
        assert ev["kvs"] == {"ref": "origin/feat/login", "spec": "msg/AUTH-001.md"}
        assert ev["detail_text"] == ""

    def test_without_kvs(self):
        ev = parse_event("AUTH", "2025-01-01T00:00:00 AUTH start login.endpoint")
        assert ev is not None
        assert ev["verb"] == "start"
        assert ev["kvs"] == {}
        assert ev["detail_text"] == ""
        assert ev["detail"] == ""

    def test_empty_line(self):
        assert parse_event("X", "") is None

    def test_whitespace_only(self):
        assert parse_event("X", "   \t  ") is None

    def test_too_few_parts(self):
        assert parse_event("X", "2025-01-01T00:00:00 AUTH") is None

    def test_minimal_event_three_parts(self):
        ev = parse_event("AUTH", "2025-01-01T00:00:00 AUTH start")
        assert ev is not None
        assert ev["verb"] == "start"
        assert ev["obj"] == ""
        assert ev["detail"] == ""
        assert ev["kvs"] == {}

    def test_four_parts_no_detail(self):
        ev = parse_event("AUTH", "2025-01-01T00:00:00 AUTH done auth-api")
        assert ev is not None
        assert ev["obj"] == "auth-api"
        assert ev["detail"] == ""

    def test_session_from_filename_not_line(self):
        """Session comes from filename (first arg), not from line content."""
        ev = parse_event("REAL", "2025-01-01T00:00:00 FAKE start task")
        assert ev["session"] == "REAL"

    def test_raw_preserved(self):
        line = "2025-01-01T00:00:00 AUTH done auth-api ref:branch"
        ev = parse_event("AUTH", line)
        assert ev["raw"] == line

    def test_detail_with_free_text_and_kvs(self):
        ev = parse_event("CART", "2025-01-01T00:00:00 CART block waiting for auth ref:needed spec:msg/REQ.md")
        assert ev["verb"] == "block"
        assert ev["obj"] == "waiting"
        assert ev["kvs"] == {"ref": "needed", "spec": "msg/REQ.md"}
        assert "for" in ev["detail_text"]
        assert "auth" in ev["detail_text"]


# ============================================================
# SwarmIndex — apply() all verbs
# ============================================================

class TestSwarmIndexApply:
    def _ev(self, session, line):
        return parse_event(session, line)

    def test_start(self):
        idx = SwarmIndex()
        idx.apply(self._ev("AUTH", "T0 AUTH start login"))
        assert idx.session_status["AUTH"] == "active"
        assert idx.session_action["AUTH"] == "start login"
        assert "AUTH" in idx.sessions_known

    def test_done_basic(self):
        idx = SwarmIndex()
        idx.apply(self._ev("AUTH", "T0 AUTH done login"))
        assert idx.session_status["AUTH"] == "idle"
        assert "login" in idx.provides["AUTH"]
        assert "AUTH.login" in idx.provides["AUTH"]
        assert len(idx.artifacts) == 1
        assert idx.artifacts[0]["ref"] == ""
        assert idx.artifacts[0]["spec"] == ""

    def test_done_with_kvs(self):
        idx = SwarmIndex()
        idx.apply(self._ev("AUTH", "T0 AUTH done login ref:origin/feat/login spec:msg/AUTH-001.md"))
        assert idx.artifacts[0]["ref"] == "origin/feat/login"
        assert idx.artifacts[0]["spec"] == "msg/AUTH-001.md"

    def test_multiple_done_accumulate_artifacts(self):
        idx = SwarmIndex()
        idx.apply(self._ev("AUTH", "T0 AUTH done api-v1"))
        idx.apply(self._ev("AUTH", "T1 AUTH done api-v2 ref:v2"))
        idx.apply(self._ev("CART", "T2 CART done cart-service"))
        assert len(idx.artifacts) == 3

    def test_need(self):
        idx = SwarmIndex()
        idx.apply(self._ev("CART", "T0 CART need AUTH.login"))
        assert "AUTH.login" in idx.needs["CART"]

    def test_block(self):
        idx = SwarmIndex()
        idx.apply(self._ev("CART", "T0 CART block waiting for auth"))
        assert idx.session_status["CART"] == "blocked"
        assert "waiting" in idx.session_action["CART"]

    def test_up(self):
        idx = SwarmIndex()
        idx.apply(self._ev("AUTH", "T0 AUTH up database"))
        assert idx.resources["database"] == "UP"

    def test_up_multi_token(self):
        idx = SwarmIndex()
        idx.apply(self._ev("AUTH", "T0 AUTH up container iam-db"))
        assert idx.resources["container iam-db"] == "UP"

    def test_down(self):
        idx = SwarmIndex()
        idx.apply(self._ev("AUTH", "T0 AUTH down database"))
        assert idx.resources["database"] == "DOWN"

    def test_up_then_down(self):
        idx = SwarmIndex()
        idx.apply(self._ev("AUTH", "T0 AUTH up database"))
        idx.apply(self._ev("AUTH", "T1 AUTH down database"))
        assert idx.resources["database"] == "DOWN"

    def test_direct(self):
        idx = SwarmIndex()
        idx.apply(self._ev("DIR", "T0 DIR direct all prioridade no login"))
        assert len(idx.directives) == 1
        assert idx.directives[0] == ("T0", "all", "prioridade no login")

    def test_ask_basic(self):
        idx = SwarmIndex()
        idx.apply(self._ev("CART", "T0 CART ask AUTH como integrar?"))
        assert len(idx.questions) == 1
        assert idx.questions[0] == ("T0", "CART", "AUTH", "como integrar?")

    def test_ask_with_spec_registers_msg_target(self):
        idx = SwarmIndex()
        idx.apply(self._ev("CART", "T0 CART ask AUTH need-help spec:msg/CART-001.md"))
        assert idx.msg_targets["msg/CART-001.md"] == "AUTH"

    def test_ask_with_msg_registers_msg_target(self):
        idx = SwarmIndex()
        idx.apply(self._ev("CART", "T0 CART ask AUTH details msg:msg/CART-002.md"))
        assert idx.msg_targets["msg/CART-002.md"] == "AUTH"

    def test_note_basic(self):
        idx = SwarmIndex()
        idx.apply(self._ev("AUTH", "T0 AUTH note observacao"))
        assert idx.session_status["AUTH"] == "idle"

    def test_note_doesnt_overwrite_active(self):
        idx = SwarmIndex()
        idx.apply(self._ev("AUTH", "T0 AUTH start login"))
        idx.apply(self._ev("AUTH", "T1 AUTH note progress"))
        assert idx.session_status["AUTH"] == "active"  # not overwritten

    def test_note_with_ack(self):
        idx = SwarmIndex()
        idx.apply(self._ev("AUTH", "T0 AUTH note recebido ack:msg/CART-001.md"))
        assert "AUTH" in idx.msg_acks["msg/CART-001.md"]

    def test_note_without_ack(self):
        idx = SwarmIndex()
        idx.apply(self._ev("AUTH", "T0 AUTH note just a note"))
        assert len(idx.msg_acks) == 0


# ============================================================
# SwarmIndex — satisfied, blockers, dependents
# ============================================================

class TestSwarmIndexDeps:
    def test_satisfied_after_done(self):
        idx = SwarmIndex()
        idx.apply(parse_event("AUTH", "T0 AUTH done login"))
        assert idx.satisfied("login")
        assert idx.satisfied("AUTH.login")
        assert not idx.satisfied("nonexistent")

    def test_blockers_for(self):
        idx = SwarmIndex()
        idx.apply(parse_event("CART", "T0 CART need AUTH.login"))
        assert idx.blockers_for("CART") == ["AUTH.login"]
        # After AUTH provides it
        idx.apply(parse_event("AUTH", "T1 AUTH done login"))
        assert idx.blockers_for("CART") == []

    def test_dependents_of(self):
        idx = SwarmIndex()
        idx.apply(parse_event("CART", "T0 CART need login"))
        idx.apply(parse_event("AUTH", "T1 AUTH done login"))
        deps = idx.dependents_of("AUTH")
        assert "CART" in deps

    def test_no_self_dependency(self):
        idx = SwarmIndex()
        idx.apply(parse_event("AUTH", "T0 AUTH need login"))
        idx.apply(parse_event("AUTH", "T1 AUTH done login"))
        assert idx.dependents_of("AUTH") == []


# ============================================================
# SwarmIndex — visibility filter
# ============================================================

class TestVisibilityFilter:
    def test_own_events_visible(self):
        idx = SwarmIndex()
        ev = parse_event("AUTH", "T0 AUTH start login")
        idx.apply(ev)
        assert idx._is_visible(ev, "AUTH")

    def test_directives_visible_to_all(self):
        idx = SwarmIndex()
        ev = parse_event("DIR", "T0 DIR direct all prioridade")
        idx.apply(ev)
        assert idx._is_visible(ev, "AUTH")
        assert idx._is_visible(ev, "CART")

    def test_ask_visible_to_target(self):
        idx = SwarmIndex()
        ev = parse_event("CART", "T0 CART ask AUTH como?")
        idx.apply(ev)
        assert idx._is_visible(ev, "AUTH")

    def test_note_hidden_from_others(self):
        idx = SwarmIndex()
        ev = parse_event("AUTH", "T0 AUTH note internal stuff")
        idx.apply(ev)
        assert not idx._is_visible(ev, "CART")
        assert idx._is_visible(ev, "AUTH")  # own notes visible

    def test_start_done_visible_to_others(self):
        idx = SwarmIndex()
        ev1 = parse_event("AUTH", "T0 AUTH start login")
        ev2 = parse_event("AUTH", "T1 AUTH done login")
        idx.apply(ev1)
        idx.apply(ev2)
        assert idx._is_visible(ev1, "CART")
        assert idx._is_visible(ev2, "CART")

    def test_recent_events_respects_limit(self):
        idx = SwarmIndex()
        for i in range(30):
            idx.apply(parse_event("AUTH", f"T{i} AUTH start task-{i}"))
        events = idx.recent_events_for("AUTH", limit=15)
        assert len(events) == 15
        # Should be the most recent 15
        assert events[-1]["obj"] == "task-29"
        assert events[0]["obj"] == "task-15"

    def test_recent_events_filters_notes_from_others(self):
        idx = SwarmIndex()
        idx.apply(parse_event("AUTH", "T0 AUTH start login"))
        idx.apply(parse_event("CART", "T1 CART note internal"))
        idx.apply(parse_event("CART", "T2 CART done cart-api"))
        events = idx.recent_events_for("AUTH", limit=15)
        verbs = [e["verb"] for e in events]
        # note from CART should be filtered out for AUTH
        assert "note" not in verbs or all(e["session"] == "AUTH" for e in events if e["verb"] == "note")
        # done from CART should be visible
        assert any(e["verb"] == "done" and e["session"] == "CART" for e in events)


# ============================================================
# SwarmIndex — pending_msgs_for
# ============================================================

class TestPendingMsgs:
    def test_no_msg_dir(self, tmp_path):
        idx = SwarmIndex()
        result = idx.pending_msgs_for("AUTH", tmp_path / "nonexistent")
        assert result == []

    def test_empty_msg_dir(self, tmp_path):
        msg_dir = tmp_path / "msg"
        msg_dir.mkdir()
        idx = SwarmIndex()
        result = idx.pending_msgs_for("AUTH", msg_dir)
        assert result == []

    def test_msg_exists_but_not_targeted(self, tmp_path):
        msg_dir = tmp_path / "msg"
        msg_dir.mkdir()
        (msg_dir / "RANDOM.md").write_text("hello")
        idx = SwarmIndex()
        result = idx.pending_msgs_for("AUTH", msg_dir)
        assert result == []

    def test_msg_targeted_and_pending(self, tmp_path):
        msg_dir = tmp_path / "msg"
        msg_dir.mkdir()
        (msg_dir / "CART-001.md").write_text("spec")
        idx = SwarmIndex()
        idx.apply(parse_event("CART", "T0 CART ask AUTH help spec:msg/CART-001.md"))
        result = idx.pending_msgs_for("AUTH", msg_dir)
        assert len(result) == 1
        assert result[0]["sender"] == "CART"

    def test_msg_acked_disappears(self, tmp_path):
        msg_dir = tmp_path / "msg"
        msg_dir.mkdir()
        (msg_dir / "CART-001.md").write_text("spec")
        idx = SwarmIndex()
        idx.apply(parse_event("CART", "T0 CART ask AUTH help spec:msg/CART-001.md"))
        idx.apply(parse_event("AUTH", "T1 AUTH note ok ack:msg/CART-001.md"))
        result = idx.pending_msgs_for("AUTH", msg_dir)
        assert len(result) == 0

    def test_multiple_pending_msgs(self, tmp_path):
        msg_dir = tmp_path / "msg"
        msg_dir.mkdir()
        (msg_dir / "CART-001.md").write_text("spec1")
        (msg_dir / "CART-002.md").write_text("spec2")
        idx = SwarmIndex()
        idx.apply(parse_event("CART", "T0 CART ask AUTH help1 spec:msg/CART-001.md"))
        idx.apply(parse_event("CART", "T1 CART ask AUTH help2 spec:msg/CART-002.md"))
        result = idx.pending_msgs_for("AUTH", msg_dir)
        assert len(result) == 2

    def test_msg_for_different_session_not_shown(self, tmp_path):
        msg_dir = tmp_path / "msg"
        msg_dir.mkdir()
        (msg_dir / "CART-001.md").write_text("spec")
        idx = SwarmIndex()
        idx.apply(parse_event("CART", "T0 CART ask AUTH help spec:msg/CART-001.md"))
        # PAYMENTS should not see AUTH's messages
        result = idx.pending_msgs_for("PAYMENTS", msg_dir)
        assert len(result) == 0


# ============================================================
# render_view — worker sessions
# ============================================================

class TestRenderViewWorker:
    def test_v1_header(self):
        idx = SwarmIndex()
        idx.sessions_known.add("AUTH")
        view = render_view(idx, "AUTH")
        assert view.startswith("<!-- myco protocol v1 -->")

    def test_all_sections_present(self):
        idx = SwarmIndex()
        idx.sessions_known.add("AUTH")
        view = render_view(idx, "AUTH")
        for section in [
            "## AGORA",
            "## DIRETIVAS",
            "## ARTEFATOS PUBLICADOS",
            "## SEUS BLOQUEADORES",
            "## SEUS DEPENDENTES",
            "## RECURSOS COMPARTILHADOS",
            "## EVENTOS RELEVANTES (últimos 15)",
            "## PERGUNTAS PENDENTES",
            "## MENSAGENS PENDENTES",
        ]:
            assert section in view, f"Missing section: {section}"

    def test_status_shown(self):
        idx = SwarmIndex()
        idx.apply(parse_event("AUTH", "T0 AUTH start login"))
        view = render_view(idx, "AUTH")
        assert "**active**" in view

    def test_blockers_shown(self):
        idx = SwarmIndex()
        idx.apply(parse_event("CART", "T0 CART need AUTH.login"))
        view = render_view(idx, "CART")
        assert "AUTH.login" in view

    def test_no_blocker_message(self):
        idx = SwarmIndex()
        idx.apply(parse_event("AUTH", "T0 AUTH start login"))
        view = render_view(idx, "AUTH")
        assert "Nenhum bloqueador conhecido." in view

    def test_dependents_shown(self):
        idx = SwarmIndex()
        idx.apply(parse_event("CART", "T0 CART need login"))
        idx.apply(parse_event("AUTH", "T1 AUTH done login"))
        view = render_view(idx, "AUTH")
        assert "CART" in view

    def test_no_dependents_message(self):
        idx = SwarmIndex()
        idx.sessions_known.add("AUTH")
        view = render_view(idx, "AUTH")
        assert "Ninguém esperando você." in view

    def test_directives_shown(self):
        idx = SwarmIndex()
        idx.apply(parse_event("DIR", "T0 DIR direct all prioridade no login"))
        idx.sessions_known.add("AUTH")
        view = render_view(idx, "AUTH")
        assert "prioridade no login" in view

    def test_directives_filtered_by_target(self):
        idx = SwarmIndex()
        idx.apply(parse_event("DIR", "T0 DIR direct CART foque no carrinho"))
        idx.sessions_known.add("AUTH")
        view = render_view(idx, "AUTH")
        # DIRETIVAS section should NOT show CART-targeted directive for AUTH
        diretivas_section = view.split("## DIRETIVAS")[1].split("##")[0]
        assert "foque no carrinho" not in diretivas_section
        assert "Nenhuma diretiva ativa." in diretivas_section
        # But CART should see it
        view_cart = render_view(idx, "CART")
        diretivas_cart = view_cart.split("## DIRETIVAS")[1].split("##")[0]
        assert "foque no carrinho" in diretivas_cart

    def test_no_directives_message(self):
        idx = SwarmIndex()
        idx.sessions_known.add("AUTH")
        view = render_view(idx, "AUTH")
        assert "Nenhuma diretiva ativa." in view

    def test_resources_shown(self):
        idx = SwarmIndex()
        idx.apply(parse_event("AUTH", "T0 AUTH up database"))
        idx.apply(parse_event("AUTH", "T1 AUTH down redis"))
        view = render_view(idx, "AUTH")
        assert "database" in view
        assert "UP" in view
        assert "redis" in view
        assert "DOWN" in view

    def test_no_resources_message(self):
        idx = SwarmIndex()
        idx.sessions_known.add("AUTH")
        view = render_view(idx, "AUTH")
        assert "Nenhum recurso registrado." in view

    def test_events_shown(self):
        idx = SwarmIndex()
        idx.apply(parse_event("AUTH", "T0 AUTH start login"))
        view = render_view(idx, "AUTH")
        assert "T0 AUTH start login" in view

    def test_no_events_message(self):
        idx = SwarmIndex()
        idx.sessions_known.add("AUTH")
        view = render_view(idx, "AUTH")
        assert "Nada recente." in view

    def test_questions_shown(self):
        idx = SwarmIndex()
        idx.apply(parse_event("CART", "T0 CART ask AUTH como integrar?"))
        view = render_view(idx, "AUTH")
        assert "CART" in view
        assert "como integrar?" in view

    def test_no_questions_message(self):
        idx = SwarmIndex()
        idx.sessions_known.add("AUTH")
        view = render_view(idx, "AUTH")
        assert "Nenhuma." in view

    def test_artifacts_table(self):
        idx = SwarmIndex()
        idx.apply(parse_event("AUTH", "T0 AUTH done api ref:origin/main spec:msg/A.md"))
        idx.apply(parse_event("CART", "T1 CART done cart"))
        view = render_view(idx, "AUTH")
        assert "| AUTH | api | origin/main | msg/A.md |" in view
        assert "| CART | cart | — | — |" in view

    def test_no_artifacts_message(self):
        idx = SwarmIndex()
        idx.sessions_known.add("AUTH")
        view = render_view(idx, "AUTH")
        assert "Nenhum artefato publicado." in view

    def test_pending_msgs_rendered(self, tmp_path):
        swarm_dir = tmp_path
        msg_dir = swarm_dir / "msg"
        msg_dir.mkdir()
        (msg_dir / "CART-001.md").write_text("spec")
        idx = SwarmIndex()
        idx.apply(parse_event("CART", "T0 CART ask AUTH help spec:msg/CART-001.md"))
        idx.sessions_known.add("AUTH")
        view = render_view(idx, "AUTH", swarm_dir=swarm_dir)
        assert "De **CART**" in view
        assert "msg/CART-001.md" in view
        # Should include absolute path so Claude can Read it directly
        assert str(msg_dir / "CART-001.md") in view
        assert "leia com Read" in view

    def test_no_pending_msgs(self):
        idx = SwarmIndex()
        idx.sessions_known.add("AUTH")
        view = render_view(idx, "AUTH")
        assert "Nenhuma mensagem pendente." in view

    def test_blocked_status_no_blocker_message(self):
        """When blocked, should NOT show 'Nenhum bloqueador conhecido.'"""
        idx = SwarmIndex()
        idx.apply(parse_event("AUTH", "T0 AUTH block waiting"))
        view = render_view(idx, "AUTH")
        assert "**blocked**" in view
        assert "Nenhum bloqueador conhecido." not in view


# ============================================================
# render_view — DIRECTOR session
# ============================================================

class TestRenderViewDirector:
    def test_director_has_no_bloqueadores_dependentes_sections(self):
        idx = SwarmIndex()
        idx.sessions_known.add("DIRECTOR")
        view = render_view(idx, "DIRECTOR")
        assert "## SEUS BLOQUEADORES" not in view
        assert "## SEUS DEPENDENTES" not in view

    def test_director_has_grafo_and_conflitos(self):
        idx = SwarmIndex()
        idx.sessions_known.add("DIRECTOR")
        view = render_view(idx, "DIRECTOR")
        assert "## GRAFO DE DEPENDÊNCIAS" in view
        assert "## CONFLITOS DETECTADOS" in view

    def test_director_worker_table_enriched(self):
        idx = SwarmIndex()
        idx.apply(parse_event("AUTH", "T0 AUTH start login"))
        idx.apply(parse_event("CART", "T1 CART need AUTH.login"))
        idx.sessions_known.add("DIRECTOR")
        view = render_view(idx, "DIRECTOR")
        assert "bloqueadores" in view
        assert "dependentes" in view
        # AUTH should show CART as dependent
        assert "CART" in view

    def test_director_no_workers(self):
        idx = SwarmIndex()
        idx.sessions_known.add("DIRECTOR")
        view = render_view(idx, "DIRECTOR")
        assert "0 sessões worker" in view

    def test_director_conflict_detection(self):
        idx = SwarmIndex()
        idx.apply(parse_event("AUTH", "T0 AUTH start shared-module"))
        idx.apply(parse_event("CART", "T1 CART start shared-module"))
        idx.sessions_known.add("DIRECTOR")
        view = render_view(idx, "DIRECTOR")
        assert "ATENÇÃO" in view
        assert "shared-module" in view

    def test_director_no_conflict(self):
        idx = SwarmIndex()
        idx.apply(parse_event("AUTH", "T0 AUTH start login"))
        idx.apply(parse_event("CART", "T1 CART start cart"))
        idx.sessions_known.add("DIRECTOR")
        view = render_view(idx, "DIRECTOR")
        assert "Nenhum conflito detectado." in view

    def test_director_dependency_graph(self):
        idx = SwarmIndex()
        idx.apply(parse_event("CART", "T0 CART need AUTH.login"))
        idx.sessions_known.add("DIRECTOR")
        view = render_view(idx, "DIRECTOR")
        assert "CART --espera--> AUTH.AUTH.login" in view

    def test_director_no_pending_deps(self):
        idx = SwarmIndex()
        idx.apply(parse_event("CART", "T0 CART need login"))
        idx.apply(parse_event("AUTH", "T1 AUTH done login"))
        idx.sessions_known.add("DIRECTOR")
        view = render_view(idx, "DIRECTOR")
        assert "Nenhuma dependência pendente." in view

    def test_director_conflict_only_active_sessions(self):
        """Conflict only detected between active (not idle/blocked) sessions."""
        idx = SwarmIndex()
        idx.apply(parse_event("AUTH", "T0 AUTH start module"))
        idx.apply(parse_event("CART", "T1 CART start module"))
        idx.apply(parse_event("CART", "T2 CART done module"))  # CART now idle
        idx.sessions_known.add("DIRECTOR")
        view = render_view(idx, "DIRECTOR")
        assert "Nenhum conflito detectado." in view


# ============================================================
# write_view_atomic
# ============================================================

class TestWriteViewAtomic:
    def test_basic_write(self, tmp_path):
        path = tmp_path / "view" / "TEST.md"
        write_view_atomic(path, "hello world\n")
        assert path.read_text() == "hello world\n"

    def test_overwrites_existing(self, tmp_path):
        path = tmp_path / "TEST.md"
        path.write_text("old content")
        write_view_atomic(path, "new content")
        assert path.read_text() == "new content"

    def test_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "view.md"
        write_view_atomic(path, "content")
        assert path.read_text() == "content"


# ============================================================
# Backward compatibility
# ============================================================

class TestBackwardCompat:
    def test_v0_events_work(self):
        """Events from v0 (no kvs) should work perfectly."""
        idx = SwarmIndex()
        events = [
            ("AUTH", "T0 AUTH start login.endpoint"),
            ("AUTH", "T1 AUTH done login.endpoint"),
            ("AUTH", "T2 AUTH need database.users-table"),
            ("AUTH", "T3 AUTH block waiting for DB"),
            ("AUTH", "T4 AUTH up api.auth"),
            ("AUTH", "T5 AUTH down api.auth"),
            ("DIR",  "T6 DIR direct all prioridade"),
            ("CART", "T7 CART ask AUTH como?"),
            ("AUTH", "T8 AUTH note tudo certo"),
        ]
        for sess, line in events:
            ev = parse_event(sess, line)
            assert ev is not None
            assert ev["kvs"] == {}
            idx.apply(ev)
        view = render_view(idx, "AUTH")
        assert "<!-- myco protocol v1 -->" in view

    def test_mixed_v0_v1_events(self):
        """Mix of v0 and v1 events in same index."""
        idx = SwarmIndex()
        idx.apply(parse_event("AUTH", "T0 AUTH done login"))  # v0
        idx.apply(parse_event("AUTH", "T1 AUTH done api ref:origin/main"))  # v1
        assert len(idx.artifacts) == 2
        assert idx.artifacts[0]["ref"] == ""
        assert idx.artifacts[1]["ref"] == "origin/main"


# ============================================================
# Integration: full cycle
# ============================================================

class TestIntegrationFullCycle:
    def test_auth_cart_cycle(self, tmp_path):
        """Full cycle: AUTH publishes, CART asks, AUTH acks."""
        swarm_dir = tmp_path
        msg_dir = swarm_dir / "msg"
        msg_dir.mkdir()

        idx = SwarmIndex()

        # AUTH starts and finishes work
        idx.apply(parse_event("AUTH", "T0 AUTH start auth-api"))
        idx.apply(parse_event("AUTH", "T1 AUTH done auth-api ref:origin/feat/auth spec:msg/AUTH-001.md"))

        # CART creates spec and asks AUTH
        (msg_dir / "CART-001.md").write_text("Need auth endpoint to accept JWT tokens")
        idx.apply(parse_event("CART", "T2 CART need AUTH.auth-api"))
        idx.apply(parse_event("CART", "T3 CART ask AUTH need-jwt-support spec:msg/CART-001.md"))

        # Verify CART sees AUTH's artifact
        view_cart = render_view(idx, "CART", swarm_dir=swarm_dir)
        assert "auth-api" in view_cart
        assert "origin/feat/auth" in view_cart

        # Verify AUTH sees pending message from CART
        view_auth = render_view(idx, "AUTH", swarm_dir=swarm_dir)
        assert "De **CART**" in view_auth
        assert "msg/CART-001.md" in view_auth

        # AUTH acks
        idx.apply(parse_event("AUTH", "T4 AUTH note recebido ack:msg/CART-001.md"))

        # Message disappears from AUTH's view
        view_auth2 = render_view(idx, "AUTH", swarm_dir=swarm_dir)
        assert "Nenhuma mensagem pendente." in view_auth2

        # DIRECTOR sees everything
        idx.sessions_known.add("DIRECTOR")
        view_dir = render_view(idx, "DIRECTOR", swarm_dir=swarm_dir)
        assert "AUTH" in view_dir
        assert "CART" in view_dir
        assert "auth-api" in view_dir

    def test_artifacts_survive_event_flood(self, tmp_path):
        """Artifacts persist even after many events push past the 15-event window."""
        idx = SwarmIndex()
        idx.apply(parse_event("AUTH", "T0 AUTH done critical-api ref:v1.0.0"))

        # Flood with 50 events
        for i in range(50):
            idx.apply(parse_event("CART", f"T{i+1} CART start task-{i}"))

        view = render_view(idx, "CART")
        assert "critical-api" in view
        assert "v1.0.0" in view

        # Recent events should only show 15
        events = idx.recent_events_for("CART", limit=15)
        assert len(events) == 15


# ============================================================
# myco_view.py — direct import
# ============================================================

class TestMycoView:
    def test_render_view_for_session_import(self, tmp_path):
        from myco_view import render_view_for_session
        swarm_dir = tmp_path
        log_dir = swarm_dir / "log"
        msg_dir = swarm_dir / "msg"
        log_dir.mkdir()
        msg_dir.mkdir()

        (log_dir / "AUTH.log").write_text(
            "T0 AUTH done api ref:origin/main\n"
            "T1 AUTH start next-task\n"
        )
        result = render_view_for_session(swarm_dir, "AUTH")
        assert "<!-- myco protocol v1 -->" in result
        assert "api" in result
        assert "origin/main" in result

    def test_render_view_for_session_empty(self, tmp_path):
        from myco_view import render_view_for_session
        result = render_view_for_session(tmp_path / "nonexistent", "AUTH")
        assert result == ""

    def test_render_view_for_session_no_logs(self, tmp_path):
        from myco_view import render_view_for_session
        (tmp_path / "log").mkdir()
        result = render_view_for_session(tmp_path, "AUTH")
        assert result == ""

    def test_cli_v1_output(self, tmp_path):
        import subprocess
        swarm_dir = tmp_path / "swarm"
        log_dir = swarm_dir / "log"
        msg_dir = swarm_dir / "msg"
        log_dir.mkdir(parents=True)
        msg_dir.mkdir()

        (log_dir / "AUTH.log").write_text("T0 AUTH done api ref:branch\n")
        (log_dir / "CART.log").write_text("T1 CART ask AUTH help spec:msg/CART-001.md\n")
        (msg_dir / "CART-001.md").write_text("need help")

        result = subprocess.run(
            ["python3", "myco_view.py", str(swarm_dir), "AUTH"],
            capture_output=True, text=True,
            cwd="/home/cezar/Workspace/myco/prototype",
        )
        assert result.returncode == 0
        assert "<!-- myco protocol v1 -->" in result.stdout
        assert "ARTEFATOS PUBLICADOS" in result.stdout
        assert "MENSAGENS PENDENTES" in result.stdout


# ============================================================
# Daemon class
# ============================================================

class TestDaemon:
    def test_init_creates_dirs(self, tmp_path):
        from mycod import Daemon
        d = Daemon(tmp_path)
        assert (tmp_path / "log").is_dir()
        assert (tmp_path / "view").is_dir()
        assert (tmp_path / "msg").is_dir()

    def test_process_line(self, tmp_path):
        from mycod import Daemon
        d = Daemon(tmp_path)
        assert d.process_line("AUTH", "T0 AUTH start login")
        assert d.index.session_status["AUTH"] == "active"

    def test_process_line_malformed(self, tmp_path):
        from mycod import Daemon
        d = Daemon(tmp_path)
        assert not d.process_line("AUTH", "")
        assert not d.process_line("AUTH", "only two")

    def test_process_line_verbose(self, tmp_path, capsys):
        from mycod import Daemon
        d = Daemon(tmp_path, verbose=True)
        d.process_line("AUTH", "T0 AUTH start login")
        captured = capsys.readouterr()
        assert "AUTH" in captured.err
        assert "start" in captured.err

    def test_render_all(self, tmp_path):
        from mycod import Daemon
        d = Daemon(tmp_path)
        d.process_line("AUTH", "T0 AUTH start login")
        d.index.sessions_known.add("DIRECTOR")
        d.render_all()
        assert (tmp_path / "view" / "AUTH.md").exists()
        assert (tmp_path / "view" / "DIRECTOR.md").exists()
        content = (tmp_path / "view" / "AUTH.md").read_text()
        assert "<!-- myco protocol v1 -->" in content

    def test_scan_once_picks_up_new_log(self, tmp_path):
        from mycod import Daemon
        d = Daemon(tmp_path)
        # Write a log file
        log_file = tmp_path / "log" / "AUTH.log"
        log_file.write_text("T0 AUTH start login\n")
        changed = d.scan_once()
        assert changed
        assert d.index.session_status["AUTH"] == "active"

    def test_scan_once_no_change(self, tmp_path):
        from mycod import Daemon
        d = Daemon(tmp_path)
        log_file = tmp_path / "log" / "AUTH.log"
        log_file.write_text("T0 AUTH start login\n")
        d.scan_once()
        # Second scan with no new data
        assert not d.scan_once()

    def test_scan_once_incremental(self, tmp_path):
        from mycod import Daemon
        d = Daemon(tmp_path)
        log_file = tmp_path / "log" / "AUTH.log"
        log_file.write_text("T0 AUTH start login\n")
        d.scan_once()
        # Append more
        with open(log_file, "a") as f:
            f.write("T1 AUTH done login\n")
        changed = d.scan_once()
        assert changed
        assert d.index.session_status["AUTH"] == "idle"

    def test_scan_once_truncated_file(self, tmp_path):
        from mycod import Daemon
        d = Daemon(tmp_path)
        log_file = tmp_path / "log" / "AUTH.log"
        log_file.write_text("T0 AUTH start login\nT1 AUTH done login\n")
        d.scan_once()
        # Truncate (smaller file)
        log_file.write_text("T2 AUTH start api\n")
        changed = d.scan_once()
        assert changed

    def test_scan_once_partial_line_buffered(self, tmp_path):
        from mycod import Daemon
        d = Daemon(tmp_path)
        log_file = tmp_path / "log" / "AUTH.log"
        # Write partial line (no newline)
        log_file.write_bytes(b"T0 AUTH start log")
        d.scan_once()
        # Should not have processed anything yet
        assert "AUTH" not in d.index.session_status
        # Complete the line
        with open(log_file, "ab") as f:
            f.write(b"in\n")
        d.scan_once()
        assert d.index.session_status["AUTH"] == "active"

    def test_daemon_run_initial_render(self, tmp_path):
        """Test that run() creates initial views before entering loop."""
        import threading
        from mycod import Daemon
        d = Daemon(tmp_path)

        # Run daemon in thread, stop after initial render
        def run_briefly():
            import signal
            d.run()

        t = threading.Thread(target=run_briefly, daemon=True)
        t.start()
        # Give it a moment to start
        import time
        time.sleep(0.05)
        # It should have created DIRECTOR view
        assert (tmp_path / "view" / "DIRECTOR.md").exists()

    def test_scan_once_deleted_log_file(self, tmp_path):
        from mycod import Daemon
        d = Daemon(tmp_path)
        log_file = tmp_path / "log" / "AUTH.log"
        log_file.write_text("T0 AUTH start login\n")
        d.scan_once()
        # Delete the file
        log_file.unlink()
        # Should not crash
        assert not d.scan_once()


# ============================================================
# myco_view.py — CLI main()
# ============================================================

class TestMycoViewCli:
    def test_cli_missing_args(self):
        import subprocess
        result = subprocess.run(
            ["python3", "myco_view.py"],
            capture_output=True, text=True,
            cwd="/home/cezar/Workspace/myco/prototype",
        )
        assert result.returncode == 2

    def test_cli_nonexistent_dir(self):
        import subprocess
        result = subprocess.run(
            ["python3", "myco_view.py", "/nonexistent", "AUTH"],
            capture_output=True, text=True,
            cwd="/home/cezar/Workspace/myco/prototype",
        )
        assert result.returncode == 0
        assert result.stdout == ""

    def test_render_view_for_session_oserror(self, tmp_path):
        """OSError reading a log file should be silently skipped."""
        from myco_view import render_view_for_session
        log_dir = tmp_path / "log"
        log_dir.mkdir()
        # Create a valid log
        (log_dir / "AUTH.log").write_text("T0 AUTH start login\n")
        # Create a log that's a directory (will cause OSError)
        (log_dir / "BAD.log").mkdir()
        result = render_view_for_session(tmp_path, "AUTH")
        assert "<!-- myco protocol v1 -->" in result


# ============================================================
# write_view_atomic — error path
# ============================================================

class TestWriteViewAtomicErrors:
    def test_write_to_readonly_dir_raises(self, tmp_path):
        import os
        readonly = tmp_path / "readonly"
        readonly.mkdir()
        target = readonly / "test.md"
        # Write once (should work)
        write_view_atomic(target, "content")
        # Make dir readonly
        os.chmod(readonly, 0o444)
        try:
            import pytest
            with pytest.raises(PermissionError):
                write_view_atomic(target, "new content")
        finally:
            os.chmod(readonly, 0o755)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
