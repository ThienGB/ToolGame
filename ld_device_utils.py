import ntpath
import os
import re
import subprocess
import time


def resolve_adb_path(base_path, adb_name="adb.exe"):
    if not base_path:
        return adb_name

    cleaned = str(base_path).strip().strip('"')
    if not cleaned:
        return adb_name

    normalized = cleaned.rstrip("\\/")
    base_name = ntpath.basename(normalized).lower()

    if base_name in {"ldconsole.exe", "dnconsole.exe", "ld.exe"}:
        folder = ntpath.dirname(normalized) or "."
        return ntpath.normpath(ntpath.join(folder, adb_name))

    if base_name.endswith(".exe") or base_name.endswith(".bat"):
        folder = ntpath.dirname(normalized) or "."
        return ntpath.normpath(ntpath.join(folder, adb_name))

    if "\\" in normalized or "/" in normalized:
        return ntpath.normpath(ntpath.join(normalized, adb_name))

    return adb_name


def parse_ldconsole_list2(output):
    devices = []
    if not output:
        return devices

    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue

        parts = [p.strip() for p in line.split(",")]
        if not parts:
            continue

        index = None
        serial = None
        running = False

        if parts[0].isdigit():
            index = int(parts[0])

        if len(parts) >= 5:
            status_value = parts[4].strip().lower()
            if status_value in {"1", "running", "on", "launched"}:
                running = True
            elif status_value in {"0", "stopped", "off", "shutdown", "exit"}:
                running = False

        for part in parts:
            if re.match(r"^(emulator-|127\.0\.0\.1:)\d+$", part):
                serial = part
                break
            if re.match(r"^\d{1,3}(?:\.\d{1,3}){3}:\d+$", part):
                serial = part
                break

        if not serial and running and index is not None:
            serial = f"127.0.0.1:{5554 + index * 2}"

        if running or serial:
            devices.append({
                "index": index,
                "serial": serial,
                "running": running,
            })

    return devices


def parse_adb_devices_output(output):
    devices = []
    if not output:
        return devices

    for line in output.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 2:
            continue
        serial = parts[0].strip()
        state = parts[1].strip().lower()
        if serial:
            devices.append((serial, state))
    return devices


def refresh_adb_devices(adb_path, serials=None, attempts=4, delay=2.0):
    if not adb_path:
        return []

    create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    serials = [s for s in (serials or []) if s]

    for _ in range(max(1, attempts)):
        try:
            subprocess.run([adb_path, "kill-server"], capture_output=True, text=True, timeout=5, creationflags=create_no_window)
        except Exception:
            pass
        try:
            subprocess.run([adb_path, "start-server"], capture_output=True, text=True, timeout=10, creationflags=create_no_window)
        except Exception:
            pass

        if serials:
            for serial in serials:
                try:
                    subprocess.run([adb_path, "connect", serial], capture_output=True, text=True, timeout=5, creationflags=create_no_window)
                except Exception:
                    pass

        try:
            res = subprocess.run([adb_path, "devices"], capture_output=True, text=True, timeout=10, creationflags=create_no_window)
            parsed = parse_adb_devices_output(res.stdout)
            online_devices = [serial for serial, state in parsed if state == "device"]
            if not serials:
                return parsed
            if any(serial in online_devices for serial in serials):
                return parsed
        except Exception:
            parsed = []

        if attempts > 1:
            time.sleep(delay)

    return []
