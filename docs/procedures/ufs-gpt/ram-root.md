# Initial RAM root for a first native boot

This describes a plan drawn from the existing project documents. Nothing here has been built,
measured or run on the phone, and no boot has happened.

## Why a RAM root comes first

The first native milestone in `docs/implementation.md` is: loader entry, early XNU markers, MMU,
timer and interrupts, scheduler, then a RAM root with an owned static PID 1 on one CPU. A RAM root
lets that milestone proceed with no storage driver at all. The UFS boundary in this directory is
not on that path, so storage bugs cannot block the first boot and a first boot cannot damage
storage.

`docs/architecture.md` sets the constraint: the first potential native root is RAM-only, and Android
userdata must not be used as an iOS root or assumed decryptable from XNU.

## Contents

The first image holds only what the milestone needs:

- An owned, statically linked PID 1 that reports a marker and then holds.
- No Apple binaries. `AGENTS.md` forbids committing them, and the upstream stage0 `/sbin/launchd` is
  an owned test Mach-O, so running it says nothing about Apple's launchd, backboardd or SpringBoard.

## Open questions

Each of these needs a measurement or a design decision before it can be relied on:

| Question | How it gets answered |
| --- | --- |
| How the loader hands the image to XNU, and at what address | Loader design task; no mechanism is qualified yet |
| How much RAM is free after the kernel and reserved regions | Measure live reserved memory; no inherited address counts as measured |
| Whether a root image fits with kernel and GPU headroom | Measure the memory budget before loading |
| How markers leave the device without Android or adbd | NAT-002 control channel design |
| How the device returns to Android afterwards | NAT-001 recovery plan; a verified restoration is a separately gated native task |

`docs/implementation.md` gives the fallback if a real userland does not fit: a verified native USB
and host-backed block transport. Android USERDATA, EFS and super are not to be repurposed.

## Where read-only UFS fits later

Once a kernel runs and a controller driver exists, the GPT and READ(10) boundary can locate a
named partition and read within it. A real controller backend, DMA mapping and IOMMU setup do not
exist yet. Default storage writes stay disabled.

## Gate

Running any of this on the phone needs a separately authorized native hardware task. This
document does not grant that.
