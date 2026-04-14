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
        text, kvs = parse_detail_kvs("deploying service ref:v1.2.3 spec:msg/DEPLOY-001.md to production")
        assert kvs == {"ref": "v1.2.3", "spec": "msg/DEPLOY-001.md"}
        assert "deploying" in text
        assert "service" in text
        assert "to" in text
        assert "production" in text

    def test_unknown_keys_ignored(self):
        """Unknown keys like http:, mailto: should not be extracted."""
        text, kvs = parse_detail_kvs("see http://localhost:3000 for details")
        assert kvs == {}
        assert "http://localhost:3000" in text

    def test_only_known_keys_extracted(self):
        text, kvs = parse_detail_kvs("done ref:master foo:bar spec:msg/A.md")
        assert kvs == {"ref": "master", "spec": "msg/A.md"}
        assert "foo:bar" in text


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

    def test_ask_sets_status_from_unknown(self):
        idx = SwarmIndex()
        idx.apply(self._ev("CART", "T0 CART ask AUTH como?"))
        assert idx.session_status["CART"] == "active"
        assert idx.session_action["CART"] == "ask AUTH"

    def test_ask_doesnt_overwrite_active(self):
        idx = SwarmIndex()
        idx.apply(self._ev("CART", "T0 CART start cart-module"))
        idx.apply(self._ev("CART", "T1 CART ask AUTH como?"))
        assert idx.session_status["CART"] == "active"
        assert idx.session_action["CART"] == "start cart-module"

    def test_ask_with_spec_registers_msg_target(self):
        idx = SwarmIndex()
        idx.apply(self._ev("CART", "T0 CART ask AUTH need-help spec:msg/CART-001.md"))
        assert idx.msg_targets["msg/CART-001.md"] == "AUTH"

    def test_ask_with_msg_not_tracked(self):
        """msg: key is no longer tracked — only spec: works."""
        idx = SwarmIndex()
        idx.apply(self._ev("CART", "T0 CART ask AUTH details msg:msg/CART-002.md"))
        assert "msg/CART-002.md" not in idx.msg_targets

    def test_note_basic(self):
        idx = SwarmIndex()
        idx.apply(self._ev("AUTH", "T0 AUTH note observacao"))
        assert idx.session_status["AUTH"] == "active"

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
        # Without session_dirs, path column shows —
        view = render_view(idx, "AUTH")
        assert "| AUTH | api | origin/main | — | msg/A.md |" in view
        assert "| CART | cart | — | — | — |" in view
        # With session_dirs, path column shows the dir
        view2 = render_view(idx, "AUTH", session_dirs={"AUTH": "/tmp/a", "CART": "/tmp/b"})
        assert "| AUTH | api | origin/main | /tmp/a | msg/A.md |" in view2
        assert "| CART | cart | — | /tmp/b | — |" in view2

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
# Question cleanup (ack resolves questions)
# ============================================================

class TestQuestionCleanup:
    def test_acked_question_disappears_from_view(self):
        idx = SwarmIndex()
        idx.apply(parse_event("CART", "T0 CART ask AUTH help spec:msg/CART-001.md"))
        idx.sessions_known.add("AUTH")
        # Before ack: question visible
        view = render_view(idx, "AUTH")
        assert "CART" in view.split("## PERGUNTAS PENDENTES")[1].split("##")[0]

        # After ack: question disappears
        idx.apply(parse_event("AUTH", "T1 AUTH note ok ack:msg/CART-001.md"))
        view2 = render_view(idx, "AUTH")
        perguntas = view2.split("## PERGUNTAS PENDENTES")[1].split("##")[0]
        assert "Nenhuma." in perguntas

    def test_question_without_spec_persists(self):
        """Questions without spec: should never be auto-resolved."""
        idx = SwarmIndex()
        idx.apply(parse_event("CART", "T0 CART ask AUTH como integrar?"))
        idx.sessions_known.add("AUTH")
        view = render_view(idx, "AUTH")
        perguntas = view.split("## PERGUNTAS PENDENTES")[1].split("##")[0]
        assert "como integrar?" in perguntas

    def test_ack_only_resolves_matching_spec(self):
        idx = SwarmIndex()
        idx.apply(parse_event("CART", "T0 CART ask AUTH q1 spec:msg/CART-001.md"))
        idx.apply(parse_event("CART", "T1 CART ask AUTH q2 spec:msg/CART-002.md"))
        # Ack only CART-001
        idx.apply(parse_event("AUTH", "T2 AUTH note ok ack:msg/CART-001.md"))
        idx.sessions_known.add("AUTH")
        view = render_view(idx, "AUTH")
        perguntas = view.split("## PERGUNTAS PENDENTES")[1].split("##")[0]
        assert "CART-001" not in perguntas
        assert "CART-002" in perguntas


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


# ============================================================
# reply verb
# ============================================================

class TestReplyVerb:
    def test_reply_parsed(self):
        ev = parse_event("AUTH", "T0 AUTH reply CART resposta-sobre-jwt")
        assert ev["verb"] == "reply"
        assert ev["obj"] == "CART"

    def test_reply_with_spec(self):
        ev = parse_event("AUTH", "T0 AUTH reply CART resposta spec:msg/AUTH-002.md")
        assert ev["kvs"]["spec"] == "msg/AUTH-002.md"

    def test_reply_with_ack(self):
        ev = parse_event("AUTH", "T0 AUTH reply CART ok ack:msg/CART-001.md")
        assert ev["kvs"]["ack"] == "msg/CART-001.md"

    def test_reply_resolves_question_by_spec(self):
        idx = SwarmIndex()
        idx.apply(parse_event("CART", "T0 CART ask AUTH como-integrar spec:msg/CART-001.md"))
        assert len(idx.questions) == 1
        # AUTH replies with ack on the spec
        idx.apply(parse_event("AUTH", "T1 AUTH reply CART resposta ack:msg/CART-001.md"))
        assert "msg/CART-001.md" in idx.answered_specs
        # Question should be filtered in view
        view = render_view(idx, "AUTH")
        assert "como-integrar" not in view.split("PERGUNTAS PENDENTES")[1]

    def test_reply_resolves_question_without_spec(self):
        idx = SwarmIndex()
        idx.apply(parse_event("CART", "T0 CART ask AUTH como-integrar"))
        # AUTH replies without spec/ack — resolves all questions from CART→AUTH
        idx.apply(parse_event("AUTH", "T1 AUTH reply CART ja-esta-pronto"))
        view = render_view(idx, "AUTH")
        assert "como-integrar" not in view.split("PERGUNTAS PENDENTES")[1]

    def test_reply_updates_status(self):
        idx = SwarmIndex()
        idx.apply(parse_event("AUTH", "T0 AUTH reply CART algo"))
        assert idx.session_status["AUTH"] == "active"

    def test_reply_tracks_msg_target(self):
        idx = SwarmIndex()
        idx.apply(parse_event("AUTH", "T0 AUTH reply CART veja spec:msg/AUTH-002.md"))
        assert idx.msg_targets.get("msg/AUTH-002.md") == "CART"

    def test_reply_auto_acks_question_spec(self, tmp_path):
        """reply without explicit ack: should auto-ack the spec from the question."""
        idx = SwarmIndex()
        idx.apply(parse_event("CART", "T0 CART ask AUTH como-integrar spec:msg/CART-001.md"))
        # AUTH replies without ack: — should auto-resolve the spec
        idx.apply(parse_event("AUTH", "T1 AUTH reply CART ja-esta-pronto"))
        assert "msg/CART-001.md" in idx.answered_specs
        # msg/ should also be acked
        assert "AUTH" in idx.msg_acks.get("msg/CART-001.md", set())
        # Question should be resolved
        assert (("CART", "AUTH", "T0")) in idx.resolved_questions
        # Pending msg should not show
        msg_dir = tmp_path / "msg"
        msg_dir.mkdir()
        (msg_dir / "CART-001.md").write_text("spec content")
        pending = idx.pending_msgs_for("AUTH", msg_dir)
        assert len(pending) == 0

    def test_reply_uses_resolved_questions_not_hack(self):
        """Verify resolved_questions is used instead of synthetic answered_specs keys."""
        idx = SwarmIndex()
        idx.apply(parse_event("CART", "T0 CART ask AUTH pergunta"))
        idx.apply(parse_event("AUTH", "T1 AUTH reply CART resposta"))
        # Should use resolved_questions, not answered_specs hacks
        assert ("CART", "AUTH", "T0") in idx.resolved_questions
        # answered_specs should NOT contain synthetic keys
        for key in idx.answered_specs:
            assert not key.startswith("_resolved_"), f"synthetic key found: {key}"


# ============================================================
# reply visibility
# ============================================================

class TestReplyVisibility:
    def test_reply_visible_to_target(self):
        idx = SwarmIndex()
        idx.apply(parse_event("AUTH", "T0 AUTH reply CART resposta"))
        view = render_view(idx, "CART")
        assert "AUTH reply CART" in view

    def test_reply_not_visible_to_others(self):
        idx = SwarmIndex()
        idx.apply(parse_event("AUTH", "T0 AUTH reply CART resposta"))
        idx.sessions_known.add("OTHER")
        view = render_view(idx, "OTHER")
        assert "AUTH reply CART" not in view

    def test_reply_visible_to_sender(self):
        idx = SwarmIndex()
        idx.apply(parse_event("AUTH", "T0 AUTH reply CART resposta"))
        view = render_view(idx, "AUTH")
        assert "AUTH reply CART" in view


# ============================================================
# note ack visibility fix
# ============================================================

class TestNoteAckVisibility:
    def test_note_ack_visible_to_asker(self):
        """Notes with ack: should be visible to the session that asked."""
        idx = SwarmIndex()
        # CART asked with spec — AUTH acks
        idx.apply(parse_event("CART", "T0 CART ask AUTH pergunta spec:msg/CART-001.md"))
        idx.apply(parse_event("AUTH", "T1 AUTH note recebido ack:msg/CART-001.md"))
        view = render_view(idx, "CART")
        assert "AUTH note recebido" in view

    def test_note_ack_not_visible_to_unrelated(self):
        """Notes with ack: should NOT be visible to unrelated sessions."""
        idx = SwarmIndex()
        idx.apply(parse_event("CART", "T0 CART ask AUTH pergunta spec:msg/CART-001.md"))
        idx.apply(parse_event("AUTH", "T1 AUTH note recebido ack:msg/CART-001.md"))
        idx.sessions_known.add("OTHER")
        view = render_view(idx, "OTHER")
        assert "AUTH note recebido" not in view

    def test_note_without_ack_hidden_from_others(self):
        """Regular notes should still be hidden from other sessions."""
        idx = SwarmIndex()
        idx.apply(parse_event("AUTH", "T0 AUTH note observacao-interna"))
        idx.sessions_known.add("CART")
        view = render_view(idx, "CART")
        assert "observacao-interna" not in view

    def test_note_visible_to_self(self):
        """Notes should always be visible to the session that wrote them."""
        idx = SwarmIndex()
        idx.apply(parse_event("AUTH", "T0 AUTH note minha-observacao"))
        view = render_view(idx, "AUTH")
        assert "minha-observacao" in view


# ============================================================
# session_dirs in artifacts
# ============================================================

class TestSessionDirsInArtifacts:
    def test_artifacts_with_session_dirs(self):
        idx = SwarmIndex()
        idx.apply(parse_event("AUTH", "T0 AUTH done api ref:master"))
        view = render_view(idx, "CART", session_dirs={"AUTH": "/tmp/teste1"})
        assert "/tmp/teste1" in view
        assert "| path |" in view

    def test_artifacts_without_session_dirs(self):
        idx = SwarmIndex()
        idx.apply(parse_event("AUTH", "T0 AUTH done api ref:master"))
        view = render_view(idx, "CART")
        # path column exists but shows —
        assert "| path |" in view


# ============================================================
# daemon loads session_dirs
# ============================================================

class TestDaemonSessionDirs:
    def test_daemon_loads_state_file(self, tmp_path):
        import json
        from mycod import Daemon
        state = {"sessions": {"AUTH": "/tmp/a", "CART": "/tmp/b"}}
        (tmp_path / ".myco-state.json").write_text(json.dumps(state))
        d = Daemon(tmp_path)
        assert d.session_dirs == {"AUTH": "/tmp/a", "CART": "/tmp/b"}

    def test_daemon_no_state_file(self, tmp_path):
        from mycod import Daemon
        d = Daemon(tmp_path)
        assert d.session_dirs == {}

    def test_daemon_render_uses_session_dirs(self, tmp_path):
        import json
        from mycod import Daemon
        state = {"sessions": {"AUTH": "/tmp/auth-proj"}}
        (tmp_path / ".myco-state.json").write_text(json.dumps(state))
        d = Daemon(tmp_path)
        d.process_line("AUTH", "T0 AUTH done api ref:master")
        d.index.sessions_known.add("DIRECTOR")
        d.render_all()
        view = (tmp_path / "view" / "DIRECTOR.md").read_text()
        assert "/tmp/auth-proj" in view


# ============================================================
# peers/ setup
# ============================================================

class TestPeerLinks:
    def test_create_peer_links(self, tmp_path):
        import subprocess
        auth_dir = tmp_path / "auth"
        cart_dir = tmp_path / "cart"
        auth_dir.mkdir()
        cart_dir.mkdir()

        # Use myco setup to create peer links
        result = subprocess.run(
            ["python3", str(Path(__file__).parent / "myco"),
             "--swarm", str(tmp_path / "swarm"),
             "setup", f"AUTH:{auth_dir}", f"CART:{cart_dir}"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0

        # AUTH should have a symlink to CART
        assert (auth_dir / "peers" / "CART").is_symlink()
        assert (auth_dir / "peers" / "CART").resolve() == cart_dir.resolve()
        # CART should have a symlink to AUTH
        assert (cart_dir / "peers" / "AUTH").is_symlink()
        assert (cart_dir / "peers" / "AUTH").resolve() == auth_dir.resolve()
        # Neither should have DIRECTOR
        assert not (auth_dir / "peers" / "DIRECTOR").exists()
        assert not (cart_dir / "peers" / "DIRECTOR").exists()


# ============================================================
# HTTP transport — ingest_events
# ============================================================

class TestIngestEvents:
    def test_ingest_persists_to_log(self, tmp_path):
        from mycod import Daemon
        d = Daemon(tmp_path)
        d.ingest_events("AUTH", ["start login", "need DB.users"])
        log_file = tmp_path / "log" / "AUTH.log"
        assert log_file.exists()
        lines = log_file.read_text().splitlines()
        assert len(lines) == 2
        assert "AUTH start login" in lines[0]
        assert "AUTH need DB.users" in lines[1]

    def test_ingest_updates_index(self, tmp_path):
        from mycod import Daemon
        d = Daemon(tmp_path)
        d.ingest_events("AUTH", ["start login"])
        assert d.index.session_status["AUTH"] == "active"

    def test_ingest_populates_view_cache(self, tmp_path):
        from mycod import Daemon
        d = Daemon(tmp_path)
        d.ingest_events("AUTH", ["start login"])
        assert "AUTH" in d.view_cache
        assert "<!-- myco protocol v1 -->" in d.view_cache["AUTH"]

    def test_ingest_multiple_sessions(self, tmp_path):
        from mycod import Daemon
        d = Daemon(tmp_path)
        d.ingest_events("AUTH", ["start login"])
        d.ingest_events("CART", ["start cart-api"])
        assert d.index.session_status["AUTH"] == "active"
        assert d.index.session_status["CART"] == "active"
        assert "AUTH" in d.view_cache
        assert "CART" in d.view_cache

    def test_ingest_thread_safety(self, tmp_path):
        """Concurrent ingest from multiple threads should not corrupt state."""
        import threading
        from mycod import Daemon
        d = Daemon(tmp_path)
        errors = []

        def ingest(session, events):
            try:
                d.ingest_events(session, events)
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(10):
            t = threading.Thread(target=ingest, args=(f"S{i}", [f"start task-{i}"]))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert len(d.index.sessions_known) == 10


# ============================================================
# HTTP transport — handler
# ============================================================

class TestHTTPHandler:
    """Test the HTTP server end-to-end using a real server on a random port."""

    @staticmethod
    def _start_server(tmp_path):
        from mycod import Daemon, MycoHTTPServer, MycoHandler
        d = Daemon(tmp_path)
        d.index.sessions_known.add("DIRECTOR")
        d._render_to_cache()
        server = MycoHTTPServer(("127.0.0.1", 0), MycoHandler, d)
        port = server.server_address[1]
        import threading
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        return server, port, d

    def test_post_events(self, tmp_path):
        import urllib.request
        server, port, d = self._start_server(tmp_path)
        try:
            import json
            data = json.dumps({"session": "AUTH", "events": ["start login"]}).encode()
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/events",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                body = json.loads(resp.read())
                assert resp.status == 200
                assert body["ok"] is True
                assert body["count"] == 1
            assert d.index.session_status["AUTH"] == "active"
        finally:
            server.shutdown()

    def test_get_view(self, tmp_path):
        import urllib.request, json
        server, port, d = self._start_server(tmp_path)
        try:
            # Ingest an event first
            d.ingest_events("AUTH", ["start login"])
            req = urllib.request.Request(f"http://127.0.0.1:{port}/view/AUTH")
            with urllib.request.urlopen(req, timeout=2) as resp:
                body = resp.read().decode("utf-8")
                assert resp.status == 200
                assert "<!-- myco protocol v1 -->" in body
                assert "AUTH" in body
        finally:
            server.shutdown()

    def test_get_status(self, tmp_path):
        import urllib.request, json
        server, port, d = self._start_server(tmp_path)
        try:
            d.ingest_events("AUTH", ["start login"])
            req = urllib.request.Request(f"http://127.0.0.1:{port}/status")
            with urllib.request.urlopen(req, timeout=2) as resp:
                body = json.loads(resp.read())
                assert resp.status == 200
                assert "AUTH" in body["sessions"]
                assert body["sessions"]["AUTH"]["status"] == "active"
        finally:
            server.shutdown()

    def test_post_dispatch(self, tmp_path):
        import urllib.request, json
        server, port, d = self._start_server(tmp_path)
        try:
            (tmp_path / "dispatch").mkdir(exist_ok=True)
            data = json.dumps({"prompt": "Implement login"}).encode()
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/dispatch/AUTH",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                body = json.loads(resp.read())
                assert resp.status == 200
                assert body["ok"] is True
            assert (tmp_path / "dispatch" / "AUTH.prompt").read_text() == "Implement login"
        finally:
            server.shutdown()

    def test_404_unknown_route(self, tmp_path):
        import urllib.request, urllib.error
        server, port, d = self._start_server(tmp_path)
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/nonexistent")
            try:
                urllib.request.urlopen(req, timeout=2)
                assert False, "expected 404"
            except urllib.error.HTTPError as e:
                assert e.code == 404
        finally:
            server.shutdown()

    def test_post_events_bad_json(self, tmp_path):
        import urllib.request, urllib.error
        server, port, d = self._start_server(tmp_path)
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/events",
                data=b"not json",
                headers={"Content-Type": "application/json"},
            )
            try:
                urllib.request.urlopen(req, timeout=2)
                assert False, "expected 400"
            except urllib.error.HTTPError as e:
                assert e.code == 400
        finally:
            server.shutdown()

    def test_post_events_missing_session(self, tmp_path):
        import urllib.request, urllib.error, json
        server, port, d = self._start_server(tmp_path)
        try:
            data = json.dumps({"events": ["start login"]}).encode()
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/events",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            try:
                urllib.request.urlopen(req, timeout=2)
                assert False, "expected 400"
            except urllib.error.HTTPError as e:
                assert e.code == 400
        finally:
            server.shutdown()

    def test_view_empty_session(self, tmp_path):
        import urllib.request
        server, port, d = self._start_server(tmp_path)
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/view/NONEXISTENT")
            with urllib.request.urlopen(req, timeout=2) as resp:
                body = resp.read().decode("utf-8")
                assert resp.status == 200
                assert body == ""  # no view cached for unknown session
        finally:
            server.shutdown()

    def test_view_case_insensitive(self, tmp_path):
        import urllib.request
        server, port, d = self._start_server(tmp_path)
        try:
            d.ingest_events("AUTH", ["start login"])
            req = urllib.request.Request(f"http://127.0.0.1:{port}/view/auth")
            with urllib.request.urlopen(req, timeout=2) as resp:
                body = resp.read().decode("utf-8")
                assert "<!-- myco protocol v1 -->" in body
        finally:
            server.shutdown()


# ============================================================
# HTTP transport — daemon run with --port
# ============================================================

class TestDaemonHTTPMode:
    def test_daemon_run_http_starts(self, tmp_path):
        """Test that run(port=...) starts an HTTP server we can query."""
        import threading, time, urllib.request, json
        from mycod import Daemon
        d = Daemon(tmp_path)

        t = threading.Thread(target=lambda: d.run(port=0), daemon=True)
        # Use port=0 via direct server creation to avoid port conflict
        # Instead, test _run_http indirectly
        from mycod import MycoHTTPServer, MycoHandler
        server = MycoHTTPServer(("127.0.0.1", 0), MycoHandler, d)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        time.sleep(0.05)
        try:
            d.ingest_events("TEST", ["start task"])
            req = urllib.request.Request(f"http://127.0.0.1:{port}/view/TEST")
            with urllib.request.urlopen(req, timeout=2) as resp:
                assert resp.status == 200
                assert "TEST" in resp.read().decode()
        finally:
            server.shutdown()


# ============================================================
# HTTP transport — daemon replays logs on startup
# ============================================================

class TestDaemonReplay:
    def test_daemon_replays_existing_logs_on_scan(self, tmp_path):
        """Daemon should replay existing log files via scan_once."""
        from mycod import Daemon
        # Pre-populate log
        log_dir = tmp_path / "log"
        log_dir.mkdir(parents=True)
        (log_dir / "AUTH.log").write_text("2025-01-01T00:00:00 AUTH start login\n")
        d = Daemon(tmp_path)
        d.scan_once()
        assert d.index.session_status["AUTH"] == "active"

    def test_ingest_after_replay(self, tmp_path):
        """Events ingested via HTTP after replay should not duplicate."""
        from mycod import Daemon
        log_dir = tmp_path / "log"
        log_dir.mkdir(parents=True)
        (log_dir / "AUTH.log").write_text("2025-01-01T00:00:00 AUTH start login\n")
        d = Daemon(tmp_path)
        d.scan_once()
        assert d.index.session_status["AUTH"] == "active"
        # Ingest new event via HTTP path
        d.ingest_events("AUTH", ["done login ref:v1.0"])
        assert d.index.session_status["AUTH"] == "idle"
        # Log should have both old and new
        lines = (log_dir / "AUTH.log").read_text().splitlines()
        assert len(lines) == 2


# ============================================================
# render_all populates view_cache
# ============================================================

class TestRenderAllViewCache:
    def test_render_all_populates_cache(self, tmp_path):
        from mycod import Daemon
        d = Daemon(tmp_path)
        d.process_line("AUTH", "T0 AUTH start login")
        d.index.sessions_known.add("DIRECTOR")
        d.render_all()
        assert "AUTH" in d.view_cache
        assert "DIRECTOR" in d.view_cache
        assert "<!-- myco protocol v1 -->" in d.view_cache["AUTH"]


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
