// SPDX-License-Identifier: GPL-2.0-only
/*
 * NAT-045: L6-L8 of the ladder, the NAT-041 engine behind the platform rungs (see ladder.h). usbmon_init() does the whole
 * core bring-up (GSNPSID check, soft reset, GCTL/GUSB2PHYCFG, event buffer, ep0, RUN_STOP) in one call; this file only
 * maps its result and the later waits onto the ladder's stop codes, so a native run reports one stage number per rung.
 *
 * Only built into an image that also has LAD_WRITING_RUNGS: it is never called otherwise.
 */
#include "usbmon.h"
#include "usbmon_port.h"
#include "ladder.h"

int lad_usb_start(struct usbmon *m, const struct usbmon_cfg *cfg, int *err)
{
	int rc = usbmon_init(m, cfg);
	int e = LAD_OK;

	switch (rc) {
	case USBMON_OK:
		break;
	case USBMON_E_ID:
		e = LAD_ERR(LAD_USB_RUNG_START, LAD_E_NOTALIVE);
		break;
	case USBMON_E_RESET:
	case USBMON_E_HALT:
		e = LAD_ERR(LAD_USB_RUNG_START, LAD_E_TIMEOUT);
		break;
	case USBMON_E_CMD:
		e = LAD_ERR(LAD_USB_RUNG_START, LAD_E_READBACK);
		break;
	default:
		e = LAD_ERR(LAD_USB_RUNG_START, LAD_E_CFG);
		break;
	}
	if (err)
		*err = e;
	return e;
}

int lad_usb_wait(struct usbmon *m, unsigned rung, uint32_t flag, uint32_t max_polls, uint32_t poll_delay_us)
{
	uint32_t n;

	if (rung != LAD_USB_RUNG_CONNECT && rung != LAD_USB_RUNG_HOST)
		return LAD_ERR(rung, LAD_E_CFG);
	for (n = 0; n < max_polls; n++) {
		usbmon_poll(m);
		if (m->flags & flag)
			return LAD_OK;
		if (poll_delay_us)
			usbmon_delay_us(poll_delay_us);
	}
	return LAD_ERR(rung, LAD_E_TIMEOUT);
}
