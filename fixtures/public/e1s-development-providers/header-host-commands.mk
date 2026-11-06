# Native header recipe host commands; no SDK content or target-rule changes.
# Preserve the immutable standalone query/platform context, then bind real Linux tools.
include /home/egor/dev/pet/s24-ios-exynos/worktrees/str-011-e1s-development-exports-20261106/artifacts/e1s-development-exports/prepare-003/host-commands.mk
TR = /usr/bin/tr
BASH = /bin/bash
ECHO = /usr/bin/echo
PRINTF = /usr/bin/printf
MKDIR = /usr/bin/mkdir -p
RM = /usr/bin/rm -f
INSTALL = /usr/bin/install
ERR = $(ECHO) > /dev/stderr
LOG_PFX_LEN = 15
LOG_PFX_LEN_ADJ = $(LOG_PFX_LEN)
LOG = $(PRINTF) "$2%$4s$(Color0) $3%s$(Color0)\n" "$1"
_LOG_HOST = $(call LOG,$1,$(ColorH),$(ColorF),$(LOG_PFX_LEN))
LOG_INSTALLHDR = $(call _LOG_HOST,INSTALLHDR)
