#!/usr/bin/env python3
# Connection test: prints the vehicle telemetry for 15 seconds (sends no commands).
"""ArgazUI mission script example — read-only connection test.

This script sends nothing to the vehicle; it only listens to the MAVLink
stream. Copy the connection pattern below when writing your own scripts.
"""
import os
import sys
import time

from pymavlink import mavutil

# ArgazUI uses two separate MAVLink outputs:
#   14550 -> the ArgazUI interface itself (the quick command buttons)
#   14551 -> mission scripts (this one)
# Two clients cannot bind the same UDP port, so scripts must use 14551.
PORT = int(os.environ.get("ARGAZ_MAVLINK_SCRIPT_PORT", "14551"))


def connect(timeout=30):
    print(f"[script] listening on udpin:127.0.0.1:{PORT} ...", flush=True)
    conn = mavutil.mavlink_connection(f"udpin:127.0.0.1:{PORT}")
    if conn.wait_heartbeat(timeout=timeout) is None:
        print("[script] ERROR: no heartbeat. Is the vehicle running?", file=sys.stderr)
        sys.exit(1)
    print(f"[script] connected — sysid={conn.target_system} comp={conn.target_component}",
          flush=True)
    return conn


def main():
    conn = connect()
    t0 = time.time()
    while time.time() - t0 < 15:
        msg = conn.recv_match(
            type=["HEARTBEAT", "GLOBAL_POSITION_INT", "VFR_HUD"],
            blocking=True, timeout=2,
        )
        if msg is None:
            continue
        kind = msg.get_type()
        if kind == "HEARTBEAT":
            armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
            print(f"[script] mode={mavutil.mode_string_v10(msg):<12} "
                  f"armed={armed}", flush=True)
        elif kind == "GLOBAL_POSITION_INT":
            print(f"[script] alt={msg.relative_alt / 1000.0:6.1f} m  "
                  f"lat={msg.lat / 1e7:.6f} lon={msg.lon / 1e7:.6f}", flush=True)
        elif kind == "VFR_HUD":
            print(f"[script] ground speed={msg.groundspeed:5.1f} m/s", flush=True)
    print("[script] done.", flush=True)


if __name__ == "__main__":
    main()
