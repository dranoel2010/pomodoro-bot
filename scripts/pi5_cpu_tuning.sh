#!/bin/sh
set -eu

ACTION="${1:-status}"

print_status() {
  echo "CPU governor status:"
  for f in /sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_governor; do
    [ -f "$f" ] || continue
    cpu_dir="$(basename "$(dirname "$(dirname "$f")")")"
    printf "  %s: %s\n" "$cpu_dir" "$(cat "$f")"
  done

  if command -v vcgencmd >/dev/null 2>&1; then
    echo ""
    echo "Thermals:"
    vcgencmd measure_temp || true
    echo "Throttle flags:"
    vcgencmd get_throttled || true
  fi

  echo ""
  echo "Current frequencies:"
  for f in /sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_cur_freq; do
    [ -f "$f" ] || continue
    cpu_dir="$(basename "$(dirname "$(dirname "$f")")")"
    khz="$(cat "$f")"
    mhz=$((khz / 1000))
    printf "  %s: %s MHz\n" "$cpu_dir" "$mhz"
  done
}

set_governor() {
  target="$1"
  if [ "$(id -u)" -ne 0 ]; then
    echo "This action requires root. Re-run with sudo." >&2
    exit 1
  fi

  for f in /sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_governor; do
    [ -f "$f" ] || continue
    echo "$target" > "$f"
  done

  echo "Set all CPU governors to '$target'."
}

case "$ACTION" in
  status)
    print_status
    ;;
  apply)
    set_governor performance
    print_status
    ;;
  reset)
    set_governor ondemand
    print_status
    ;;
  *)
    echo "Usage: $0 [status|apply|reset]" >&2
    exit 1
    ;;
esac
