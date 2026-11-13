/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * DesignWare USB3 DRD device-side register, TRB and event layout used by the polled EP0 monitor (NAT-041).
 *
 * The names and values are taken from the Linux dwc3 driver as shipped in the pinned vendor kernel `s24-linux`
 * (revision 417484173abc2c4fa93e738ea82ad9f2e84911b1): drivers/usb/dwc3/core.h and drivers/usb/dwc3/gadget.h,
 * both "SPDX-License-Identifier: GPL-2.0", Copyright (C) 2010-2011 Texas Instruments Incorporated - https://www.ti.com,
 * Authors: Felipe Balbi <balbi@ti.com>, Sebastian Andrzej Siewior <bigeasy@linutronix.de>.
 * Only the constants this engine uses are copied, none of the driver code. `test_engine.py` re-reads the pinned files
 * and fails if any value here differs from the vendor definition of the same name.
 */
#ifndef USBMON_DWC3_REGS_H
#define USBMON_DWC3_REGS_H

#include <stdint.h>

#define BIT(n) (1U << (n))

/* ---- global registers (offsets from the controller base) ---- */
#define DWC3_GSBUSCFG0		0xc100
#define DWC3_GRXTHRCFG		0xc10c
#define DWC3_GCTL		0xc110
#define DWC3_GSTS		0xc118
#define DWC3_GSNPSID		0xc120
#define DWC3_GUID		0xc128
#define DWC3_GUCTL		0xc12c
#define DWC3_GHWPARAMS0		0xc140
#define DWC3_GHWPARAMS1		0xc144
#define DWC3_GHWPARAMS3		0xc14c
#define DWC3_GHWPARAMS7		0xc15c
#define DWC3_GUSB2PHYCFG(n)	(0xc200 + ((n) * 0x04))
#define DWC3_GUSB3PIPECTL(n)	(0xc2c0 + ((n) * 0x04))
#define DWC3_GEVNTADRLO(n)	(0xc400 + ((n) * 0x10))
#define DWC3_GEVNTADRHI(n)	(0xc404 + ((n) * 0x10))
#define DWC3_GEVNTSIZ(n)	(0xc408 + ((n) * 0x10))
#define DWC3_GEVNTCOUNT(n)	(0xc40c + ((n) * 0x10))
#define DWC3_GFLADJ		0xc630

/* ---- device registers ---- */
#define DWC3_DCFG		0xc700
#define DWC3_DCTL		0xc704
#define DWC3_DEVTEN		0xc708
#define DWC3_DSTS		0xc70c
#define DWC3_DALEPENA		0xc720
#define DWC3_DEP_BASE(n)	(0xc800 + ((n) * 0x10))
#define DWC3_DEPCMDPAR2		0x00
#define DWC3_DEPCMDPAR1		0x04
#define DWC3_DEPCMDPAR0		0x08
#define DWC3_DEPCMD		0x0c

#define DWC3_GSNPSID_MASK	0xffff0000
#define DWC3_GEVNTCOUNT_MASK	0xfffc
#define DWC3_GEVNTSIZ_INTMASK	BIT(31)
#define DWC3_GEVNTSIZ_SIZE(n)	((n) & 0xffff)

#define DWC3_GCTL_PRTCAPDIR(n)	((n) << 12)
#define DWC3_GCTL_PRTCAP_DEVICE	2
#define DWC3_GCTL_SCALEDOWN_MASK (3 << 4)
#define DWC3_GCTL_U2EXIT_LFPS	BIT(2)
#define DWC3_GCTL_DSBLCLKGTNG	BIT(0)

#define DWC3_GUSB2PHYCFG_U2_FREECLK_EXISTS	BIT(30)
#define DWC3_GUSB2PHYCFG_ENBLSLPM		BIT(8)
#define DWC3_GUSB2PHYCFG_SUSPHY			BIT(6)

#define DWC3_GFLADJ_30MHZ_SDBND_SEL	BIT(7)
#define DWC3_GFLADJ_30MHZ_MASK		0x3f
#define DWC3_GFLADJ_REFCLK_FLADJ_MASK	0x003fff00u	/* GENMASK(21, 8) */
#define DWC3_GFLADJ_REFCLK_LPM_SEL	BIT(23)
#define DWC3_GFLADJ_240MHZDECR		0x7f000000u	/* GENMASK(30, 24) */
#define DWC3_GFLADJ_240MHZDECR_PLS1	BIT(31)
#define DWC3_GUCTL_REFCLKPER_MASK	0xffc00000
#define DWC3_GUCTL_REFCLKPER_SEL	22

#define DWC3_GSBUSCFG0_INCRBRSTENA	BIT(0)
#define DWC3_GSBUSCFG0_INCR4BRSTENA	BIT(1)
#define DWC3_GSBUSCFG0_INCR8BRSTENA	BIT(2)
#define DWC3_GSBUSCFG0_INCR16BRSTENA	BIT(3)

#define DWC3_GHWPARAMS7_RAM2_DEPTH(n)	(((n) >> 16) & 0xffff)

/* ---- DCFG / DCTL / DEVTEN / DSTS ---- */
#define DWC3_DCFG_DEVADDR(addr)	((addr) << 3)
#define DWC3_DCFG_DEVADDR_MASK	DWC3_DCFG_DEVADDR(0x7f)
#define DWC3_DCFG_SPEED_MASK	(7 << 0)
#define DWC3_DCFG_SUPERSPEED	(4 << 0)
#define DWC3_DCFG_HIGHSPEED	(0 << 0)
#define DWC3_DCFG_FULLSPEED	BIT(0)
#define DWC3_DCFG_NUMP_SHIFT	17
#define DWC3_DCFG_NUMP_MASK	(0x1f << DWC3_DCFG_NUMP_SHIFT)
#define DWC3_DCFG_IGNSTRMPP	BIT(23)

#define DWC3_DCTL_RUN_STOP	BIT(31)
#define DWC3_DCTL_CSFTRST	BIT(30)
#define DWC3_DCTL_KEEP_CONNECT	BIT(19)
#define DWC3_DCTL_TSTCTRL_MASK	(0xf << 1)

#define DWC3_DEVTEN_EVNTOVERFLOWEN	BIT(11)
#define DWC3_DEVTEN_CMDCMPLTEN		BIT(10)
#define DWC3_DEVTEN_ERRTICERREN		BIT(9)
#define DWC3_DEVTEN_WKUPEVTEN		BIT(4)
#define DWC3_DEVTEN_ULSTCNGEN		BIT(3)
#define DWC3_DEVTEN_CONNECTDONEEN	BIT(2)
#define DWC3_DEVTEN_USBRSTEN		BIT(1)
#define DWC3_DEVTEN_DISCONNEVTEN	BIT(0)

#define DWC3_DSTS_DEVCTRLHLT		BIT(22)
#define DWC3_DSTS_CONNECTSPD		(7 << 0)
#define DWC3_DSTS_SUPERSPEED		(4 << 0)
#define DWC3_DSTS_HIGHSPEED		(0 << 0)
#define DWC3_DSTS_FULLSPEED		BIT(0)

/* ---- endpoint commands (DEPCMD) ---- */
#define DWC3_DEPCMD_PARAM_SHIFT		16
#define DWC3_DEPCMD_PARAM(x)		((x) << DWC3_DEPCMD_PARAM_SHIFT)
#define DWC3_DEPCMD_GET_RSC_IDX(x)	(((x) >> DWC3_DEPCMD_PARAM_SHIFT) & 0x7f)
#define DWC3_DEPCMD_STATUS(x)		(((x) >> 12) & 0x0F)
#define DWC3_DEPCMD_CMDACT		BIT(10)
#define DWC3_DEPCMD_CMDIOC		BIT(8)
#define DWC3_DEPCMD_DEPSTARTCFG		(0x09 << 0)
#define DWC3_DEPCMD_ENDTRANSFER		(0x08 << 0)
#define DWC3_DEPCMD_STARTTRANSFER	(0x06 << 0)
#define DWC3_DEPCMD_UPDATETRANSFER	(0x07 << 0)	/* NAT-076: drivers/usb/dwc3/core.h:566 */
#define DWC3_DEPCMD_SETSTALL		(0x04 << 0)
#define DWC3_DEPCMD_SETTRANSFRESOURCE	(0x02 << 0)
#define DWC3_DEPCMD_SETEPCONFIG		(0x01 << 0)
#define DWC3_DEPCMD_CMD(x)		((x) & 0xf)
#define DWC3_DALEPENA_EP(n)		BIT(n)
#define DEPEVT_TRANSFER_NO_RESOURCE	1
#define DEPEVT_TRANSFER_BUS_EXPIRY	2

#define DWC3_DEPCMD_TYPE_CONTROL	0
#define DWC3_DEPCMD_TYPE_BULK		2	/* NAT-076: core.h:587 */

/* DEPCFG parameter 1 */
#define DWC3_DEPCFG_XFER_COMPLETE_EN	BIT(8)
#define DWC3_DEPCFG_XFER_IN_PROGRESS_EN	BIT(9)	/* NAT-076: gadget.h:25 */
#define DWC3_DEPCFG_XFER_NOT_READY_EN	BIT(10)
#define DWC3_DEPCFG_EP_NUMBER(n)	(((n) & 0x1f) << 25)
/* DEPCFG parameter 0 */
#define DWC3_DEPCFG_EP_TYPE(n)		(((n) & 0x3) << 1)
#define DWC3_DEPCFG_MAX_PACKET_SIZE(n)	(((n) & 0x7ff) << 3)
#define DWC3_DEPCFG_FIFO_NUMBER(n)	(((n) & 0x1f) << 17)
#define DWC3_DEPCFG_ACTION_INIT		(0 << 30)
#define DWC3_DEPCFG_ACTION_MODIFY	(2 << 30)
#define DWC3_DEPXFERCFG_NUM_XFER_RES(n)	((n) & 0xffff)

/* ---- transfer request blocks ---- */
#define DWC3_TRB_SIZE_MASK	(0x00ffffff)
#define DWC3_TRB_SIZE_LENGTH(n)	((n) & DWC3_TRB_SIZE_MASK)
#define DWC3_TRB_SIZE_TRBSTS(n)	(((n) & (0x0fU << 28)) >> 28)
#define DWC3_TRBSTS_OK			0
#define DWC3_TRBSTS_SETUP_PENDING	2

#define DWC3_TRB_CTRL_HWO		BIT(0)
#define DWC3_TRB_CTRL_LST		BIT(1)
#define DWC3_TRB_CTRL_CHN		BIT(2)
#define DWC3_TRB_CTRL_CSP		BIT(3)	/* NAT-076: core.h:851 */
#define DWC3_TRB_CTRL_TRBCTL(n)		(((n) & 0x3f) << 4)
#define DWC3_TRB_CTRL_ISP_IMI		BIT(10)
#define DWC3_TRB_CTRL_IOC		BIT(11)
#define DWC3_TRBCTL_NORMAL		DWC3_TRB_CTRL_TRBCTL(1)	/* NAT-076: core.h:859 */
#define DWC3_TRBCTL_CONTROL_SETUP	DWC3_TRB_CTRL_TRBCTL(2)
#define DWC3_TRBCTL_CONTROL_STATUS2	DWC3_TRB_CTRL_TRBCTL(3)
#define DWC3_TRBCTL_CONTROL_STATUS3	DWC3_TRB_CTRL_TRBCTL(4)
#define DWC3_TRBCTL_CONTROL_DATA	DWC3_TRB_CTRL_TRBCTL(5)
#define DWC3_TRBCTL_LINK_TRB		DWC3_TRB_CTRL_TRBCTL(8)	/* NAT-076: core.h:866 */

/* ---- events ---- */
/* bit 0 is_devspec; device-specific events carry their type in bits 11:8, endpoint events carry the endpoint number in 5:1,
 * the event code in 9:6, the status in 15:12 and the parameters in 31:16 (struct dwc3_event_devt / dwc3_event_depevt). */
#define DWC3_DEVICE_EVENT_DISCONNECT		0
#define DWC3_DEVICE_EVENT_RESET			1
#define DWC3_DEVICE_EVENT_CONNECT_DONE		2
#define DWC3_DEVICE_EVENT_LINK_STATUS_CHANGE	3
#define DWC3_DEVICE_EVENT_WAKEUP		4
#define DWC3_DEVICE_EVENT_CMD_CMPL		10
#define DWC3_DEVICE_EVENT_OVERFLOW		11

#define DWC3_DEPEVT_XFERCOMPLETE	0x01
#define DWC3_DEPEVT_XFERINPROGRESS	0x02
#define DWC3_DEPEVT_XFERNOTREADY	0x03
#define DWC3_DEPEVT_RXTXFIFOEVT		0x04
#define DWC3_DEPEVT_STREAMEVT		0x06
#define DWC3_DEPEVT_EPCMDCMPLT		0x07

#define DEPEVT_STATUS_BUSERR	BIT(0)	/* NAT-076: core.h:1444-1447, event status of XferInProgress/XferComplete */
#define DEPEVT_STATUS_SHORT	BIT(1)
#define DEPEVT_STATUS_IOC	BIT(2)
#define DEPEVT_STATUS_CONTROL_DATA	1
#define DEPEVT_STATUS_CONTROL_STATUS	2

#define DWC3_EVT_IS_DEVSPEC(e)		((e) & 1U)
#define DWC3_EVT_DEV_TYPE(e)		(((e) >> 8) & 0xfU)
#define DWC3_EVT_DEV_RAWTYPE(e)		(((e) >> 1) & 0x7fU)	/* 0 = DWC3_EVENT_TYPE_DEV */
#define DWC3_EVT_EP_NUM(e)		(((e) >> 1) & 0x1fU)
#define DWC3_EVT_EP_EVENT(e)		(((e) >> 6) & 0xfU)
#define DWC3_EVT_EP_STATUS(e)		(((e) >> 12) & 0xfU)
#define DWC3_EVT_EP_PARAMS(e)		(((e) >> 16) & 0xffffU)

/* One transfer request block (16 bytes, little endian, 16-byte aligned). */
struct dwc3_trb {
	uint32_t bpl;
	uint32_t bph;
	uint32_t size;
	uint32_t ctrl;
};
_Static_assert(sizeof(struct dwc3_trb) == 16, "dwc3_trb is 16 bytes");

#endif
