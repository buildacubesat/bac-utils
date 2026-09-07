# bac-can-up v1.2.0

Build a CubeSat – brings up the CANable SLCAN interface for bench testing in one command. It stops a `slcand` left over from an earlier session, starts a fresh one on the adapter, sets the bitrate and brings the SocketCAN interface up, then shows `ip -details link show` so the state is visible at a glance. The privileged steps run through `sudo` unless the tool is already root.

## 1. Install

```sh
uv tool install ./tools/bac-can-up     # from the bac-utils checkout
bac-can-up --init                      # records the CANable's serial path
bac-can-up
```

`slcand` (from `can-utils`), `ip` (from `iproute2`) and, unless running as root, `sudo` must be installed; the tool says so if one is missing. `--init` lists the adapters under `/dev/serial/by-id/` and, when exactly one is plugged in, writes it into `~/.config/bac/bac-can-up.toml`; with none or several it writes the file with an empty `device.path` for you to fill in. That path carries the adapter's serial number, which is why it lives in the user config and not in the repository. `examples/bac-can-up.toml` shows the file.

## 2. Usage

```
bac-can-up [BITRATE] [--device PATH] [--interface NAME] [--config PATH] [--dry-run] [--init]
```

`BITRATE` is one of 10k, 20k, 50k, 100k, 125k, 250k, 500k, 800k, 1M and may be written as `500`, `500k` or `500000`; without it the config's default applies (500k as written by `--init`). `--device` and `--interface` override the configured adapter and interface name for one run. `--dry-run` prints the commands and runs nothing. Exit codes: `0` interface up, `1` a step failed, the adapter is missing or setup has not run, `2` bad arguments.

```
  bac-can-up  v1.2.0
  Bringing up can0 at 500 kbit/s.

  adapter /dev/serial/by-id/usb-Openlight_Labs_CANable2_…-if00
  ✓ Stopped earlier slcand
  ✓ Started slcand
  ✓ Set bitrate 500 kbit/s
  ✓ Brought can0 up
  3: can0: <NOARP,UP,LOWER_UP,ECHO> mtu 16 qdisc pfifo_fast state UP …
      can state ERROR-ACTIVE …

    Interface  :  can0
    Bitrate    :  500 kbit/s
    Commands   :  5
```

## 3. What it runs

```
sudo pkill -x slcand                                  # exit 1 (nothing running) is fine
sudo slcand -c DEVICE can0
sudo ip link set dev can0 type can bitrate 500000
sudo ip link set dev can0 up
ip -details link show can0
```

`pkill -x slcand` stops every `slcand` on the machine, not only the one for this adapter – the script has always done that, and with a second CAN adapter in use it would take that one down too. After stopping the old daemon the tool waits for `can0` to disappear, and after starting the new one for it to appear, up to `defaults.wait_timeout` seconds (5 by default) in each case; a timeout is reported as a failure with the step that did not complete. Two daemons on one port leave the interface in a state that only a replug fixes, which is why the old one is always stopped first.

## 4. Configuration

```toml
[device]
path = "/dev/serial/by-id/usb-Openlight_Labs_CANable2_…-if00"
interface = "can0"

[defaults]
bitrate = "500k"
wait_timeout = 5
```

## 5. Version history

| Version | Date | Change |
| :-- | :-- | :-- |
| 1.2.0 | 2026-09-07 | Moved into bac-utils as `bac-can-up` and rewritten in Python on `bac-common`: the adapter path moves from a constant in the script to `~/.config/bac/bac-can-up.toml` written by `--init`, which lists the adapters present; `--device`, `--interface` and `--dry-run` added; `sudo` skipped when already root; standard flags and Rich output; the commands themselves are unchanged. 26 tests with the operating system faked. |
| 1.1.0 | 2026-09-04 | `canup.sh`: bitrate argument in the three spellings, waits for the interface to disappear and appear. |
