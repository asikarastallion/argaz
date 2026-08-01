#!/usr/bin/env python3
# Copter: GUIDED takeoff -> hold target altitude -> RTL. (Multirotors only.)
"""ArgazUI mission script example — autonomous takeoff and return.

Usage: start a Copter model (e.g. Iris) in ArgazUI, wait until MAVLink is
connected, then run this script with "RUN SCRIPT".
"""
import os
import sys
import time

from pymavlink import mavutil

PORT = int(os.environ.get("ARGAZ_MAVLINK_SCRIPT_PORT", "14551"))
TARGET_ALT = 15.0     # metres


def connect(timeout=30):
    print(f"[script] listening on udpin:127.0.0.1:{PORT} ...", flush=True)
    conn = mavutil.mavlink_connection(f"udpin:127.0.0.1:{PORT}")
    if conn.wait_heartbeat(timeout=timeout) is None:
        print("[script] ERROR: no heartbeat.", file=sys.stderr)
        sys.exit(1)
    print(f"[script] connected — sysid={conn.target_system}", flush=True)
    return conn


def command(conn, cmd_id, *params, label=""):
    """Send a command_long and wait for its ACK."""
    params = list(params) + [0.0] * (7 - len(params))
    conn.mav.command_long_send(conn.target_system, conn.target_component,
                               cmd_id, 0, *params)
    deadline = time.time() + 10
    while time.time() < deadline:
        ack = conn.recv_match(type="COMMAND_ACK", blocking=True, timeout=1)
        if ack and ack.command == cmd_id:
            ok = ack.result == mavutil.mavlink.MAV_RESULT_ACCEPTED
            name = mavutil.mavlink.enums["MAV_RESULT"][ack.result].name
            print(f"[script] {label or cmd_id}: {name}", flush=True)
            return ok
    print(f"[script] {label or cmd_id}: no ACK received", flush=True)
    return False


def set_mode(conn, name, timeout=10):
    mapping = conn.mode_mapping() or {}
    if name not in mapping:
        print(f"[script] ERROR: '{name}' not available. Modes: {sorted(mapping)}",
              file=sys.stderr)
        return False
    conn.set_mode(mapping[name])
    deadline = time.time() + timeout
    while time.time() < deadline:
        hb = conn.recv_match(type="HEARTBEAT", blocking=True, timeout=1)
        if hb and mavutil.mode_string_v10(hb) == name:
            print(f"[script] mode -> {name}", flush=True)
            return True
    print(f"[script] could not confirm mode {name}", file=sys.stderr)
    return False


def altitude(conn, timeout=2):
    msg = conn.recv_match(type="GLOBAL_POSITION_INT", blocking=True, timeout=timeout)
    return msg.relative_alt / 1000.0 if msg else None


def main():
    conn = connect()

    if not set_mode(conn, "GUIDED"):
        sys.exit(1)

    if not command(conn, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1, label="ARM"):
        print("[script] ARM rejected (EKF/GPS may not be ready yet). Exiting.",
              file=sys.stderr)
        sys.exit(1)

    if not command(conn, mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
                   0, 0, 0, 0, 0, 0, TARGET_ALT, label=f"TAKEOFF {TARGET_ALT:g}m"):
        sys.exit(1)

    print(f"[script] climbing to {TARGET_ALT:g} m ...", flush=True)
    deadline = time.time() + 90
    while time.time() < deadline:
        alt = altitude(conn)
        if alt is not None:
            print(f"[script] altitude: {alt:5.1f} m", flush=True)
            if alt >= TARGET_ALT * 0.95:
                print("[script] target altitude reached.", flush=True)
                break
        time.sleep(1)
    else:
        print("[script] WARNING: target altitude not reached, returning anyway.",
              flush=True)

    time.sleep(5)
    set_mode(conn, "RTL")
    print("[script] RTL commanded, script finished. Watch the landing in the terminal.",
          flush=True)


if __name__ == "__main__":
    main()
