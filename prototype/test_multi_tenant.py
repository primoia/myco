#!/usr/bin/env python3
"""Test multi-tenant isolation and security features."""

import json
import os
import subprocess
import sys
import time
import requests
from pathlib import Path

# Test configuration
SWARM_DIR = Path("/tmp/myco-test-multi-tenant")
PORT = 9999
BASE_URL = f"http://localhost:{PORT}"

# Test tokens
TOKEN_VALID_1 = "myco-test-tenant-alpha-secure-token-abcdefghijklmnopqrstuvwxyz-1234567890"  # Good entropy
TOKEN_VALID_2 = "myco-test-tenant-beta-secure-token-zyxwvutsrqponmlkjihgfedcba-0987654321"  # Different valid token
TOKEN_WEAK = "abc123"  # Too short
TOKEN_LOW_ENTROPY = "a" * 64  # Low entropy (all same char)

PROTOTYPE_DIR = Path(__file__).resolve().parent


def cleanup():
    """Clean up test directory."""
    import shutil
    if SWARM_DIR.exists():
        shutil.rmtree(SWARM_DIR)

def start_daemon():
    """Start daemon in multi-tenant mode."""
    SWARM_DIR.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        ["python3", "mycod.py", "--multi-tenant", "--port", str(PORT), str(SWARM_DIR)],
        cwd=str(PROTOTYPE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Wait for startup
    time.sleep(2)
    return proc

def test_healthz():
    """Test health check endpoint."""
    print("Test 1: Health check...")
    resp = requests.get(f"{BASE_URL}/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["mode"] == "multi-tenant"
    print("  ✓ Health check passed")

def test_weak_token_rejection():
    """Test that weak tokens are rejected."""
    print("\nTest 2: Weak token rejection...")

    # Too short
    resp = requests.post(
        f"{BASE_URL}/events",
        headers={"Authorization": f"Bearer {TOKEN_WEAK}"},
        json={"session": "TEST", "events": ["start foo"]},
    )
    assert resp.status_code == 401
    data = resp.json()
    assert "too short" in data["error"]
    print("  ✓ Short token rejected")

    # Low entropy
    resp = requests.post(
        f"{BASE_URL}/events",
        headers={"Authorization": f"Bearer {TOKEN_LOW_ENTROPY}"},
        json={"session": "TEST", "events": ["start foo"]},
    )
    assert resp.status_code == 401
    data = resp.json()
    assert "weak" in data["error"] or "entropy" in data["error"]
    print("  ✓ Low entropy token rejected")

def test_tenant_isolation():
    """Test that tenants are completely isolated."""
    print("\nTest 3: Tenant isolation...")

    # Create event in tenant 1
    resp = requests.post(
        f"{BASE_URL}/events",
        headers={"Authorization": f"Bearer {TOKEN_VALID_1}"},
        json={"session": "ALICE", "events": ["start secret-project"]},
    )
    assert resp.status_code == 200
    print("  ✓ Event posted to tenant 1")

    # Create event in tenant 2
    resp = requests.post(
        f"{BASE_URL}/events",
        headers={"Authorization": f"Bearer {TOKEN_VALID_2}"},
        json={"session": "BOB", "events": ["start different-project"]},
    )
    assert resp.status_code == 200
    print("  ✓ Event posted to tenant 2")

    # Read view from tenant 1
    resp = requests.get(
        f"{BASE_URL}/view/ALICE",
        headers={"Authorization": f"Bearer {TOKEN_VALID_1}"},
    )
    assert resp.status_code == 200
    view1 = resp.text
    assert "secret-project" in view1
    assert "different-project" not in view1  # Should NOT see tenant 2 data
    assert "BOB" not in view1
    print("  ✓ Tenant 1 view isolated (sees only own data)")

    # Read view from tenant 2
    resp = requests.get(
        f"{BASE_URL}/view/BOB",
        headers={"Authorization": f"Bearer {TOKEN_VALID_2}"},
    )
    assert resp.status_code == 200
    view2 = resp.text
    assert "different-project" in view2
    assert "secret-project" not in view2  # Should NOT see tenant 1 data
    assert "ALICE" not in view2
    print("  ✓ Tenant 2 view isolated (sees only own data)")

def test_rate_limiting():
    """Test rate limiting against brute-force."""
    print("\nTest 4: Rate limiting...")

    # Make 6 failed attempts (limit is 5)
    for i in range(6):
        resp = requests.post(
            f"{BASE_URL}/events",
            headers={"Authorization": f"Bearer invalid-token-{i}"},
            json={"session": "TEST", "events": ["start foo"]},
        )
        if i < 5:
            assert resp.status_code == 401
        else:
            # 6th attempt should be rate limited
            assert resp.status_code == 401
            data = resp.json()
            assert "too many" in data["error"] or "retry" in data["error"]

    print("  ✓ Rate limiting activated after 5 failures")

def test_message_isolation():
    """Test that messages are isolated between tenants."""
    print("\nTest 5: Message isolation...")

    # Create message in tenant 1
    resp = requests.post(
        f"{BASE_URL}/msg/ALICE-001.md",
        headers={"Authorization": f"Bearer {TOKEN_VALID_1}"},
        data="Secret message from Alice",
    )
    if resp.status_code != 200:
        print(f"  DEBUG: POST /msg/ failed with status {resp.status_code}")
        print(f"  DEBUG: Response: {resp.text}")
    assert resp.status_code == 200
    print("  ✓ Message created in tenant 1")

    # Try to read from tenant 2 (should fail or not exist)
    resp = requests.get(
        f"{BASE_URL}/msg/ALICE-001.md",
        headers={"Authorization": f"Bearer {TOKEN_VALID_2}"},
    )
    assert resp.status_code == 404  # Different tenant = different msg directory
    print("  ✓ Message not accessible from tenant 2")

    # Read from tenant 1 (should work)
    resp = requests.get(
        f"{BASE_URL}/msg/ALICE-001.md?session=ALICE",
        headers={"Authorization": f"Bearer {TOKEN_VALID_1}"},
    )
    assert resp.status_code == 200
    assert "Secret message from Alice" in resp.text
    print("  ✓ Message accessible from tenant 1")

def main():
    print("=" * 60)
    print("Multi-tenant security test suite")
    print("=" * 60)

    cleanup()
    proc = None

    try:
        proc = start_daemon()
        print("\n[Starting daemon in multi-tenant mode...]")
        time.sleep(1)  # Give it time to start

        test_healthz()
        test_weak_token_rejection()
        test_tenant_isolation()
        test_message_isolation()
        test_rate_limiting()  # Run last - bans localhost for 5 min

        print("\n" + "=" * 60)
        print("All tests passed! ✓")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if proc:
            proc.terminate()
            proc.wait(timeout=2)
        cleanup()

if __name__ == "__main__":
    main()
