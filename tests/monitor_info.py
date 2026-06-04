import json
import wmi
from mss import MSS
from screeninfo import get_monitors


def decode_wmi_string(data):
    if data is None:
        return ""

    return "".join(
        chr(x)
        for x in data
        if isinstance(x, int) and x > 0
    ).strip()


def get_monitor_names():
    w = wmi.WMI(namespace="root\\wmi")

    monitors = []

    for monitor in w.WmiMonitorID():

        monitors.append({
            "manufacturer": decode_wmi_string(
                monitor.ManufacturerName
            ) or "Unknown",

            "model": decode_wmi_string(
                monitor.UserFriendlyName
            ) or "Unknown",

            "serial": decode_wmi_string(
                monitor.SerialNumberID
            ) or "Unknown"
        })

    return monitors


def get_monitor_mapping():

    wmi_monitors = get_monitor_names()
    screeninfo_monitors = get_monitors()

    monitor_map = []

    with MSS() as sct:

        # Skip monitor[0] (virtual desktop)
        for mss_index, mss_monitor in enumerate(
            sct.monitors[1:], start=1
        ):

            matched_screen_idx = None

            for idx, screen in enumerate(screeninfo_monitors):

                if (
                    screen.x == mss_monitor["left"]
                    and screen.y == mss_monitor["top"]
                    and screen.width == mss_monitor["width"]
                    and screen.height == mss_monitor["height"]
                ):
                    matched_screen_idx = idx
                    break

            info = {
                "mss_index": mss_index,
                "manufacturer": "Unknown",
                "model": "Unknown",
                "serial": "Unknown",
                "x": mss_monitor["left"],
                "y": mss_monitor["top"],
                "width": mss_monitor["width"],
                "height": mss_monitor["height"]
            }

            if (
                matched_screen_idx is not None
                and matched_screen_idx < len(wmi_monitors)
            ):
                info.update(
                    wmi_monitors[matched_screen_idx]
                )

            monitor_map.append(info)

    return monitor_map


if __name__ == "__main__":

    monitors = get_monitor_mapping()

    print("\nDetected Monitors")
    print("=" * 70)

    for monitor in monitors:

        print(
            json.dumps(
                monitor,
                indent=4
            )
        )

        print()