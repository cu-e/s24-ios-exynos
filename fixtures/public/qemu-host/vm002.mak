# QEMU 10.2.0 minimal ARM_VIRT host profile, selected for VM-004.
# ARM_VIRT selects ACPI_CXL. With default devices disabled, include its genuine
# CXL provider and required PXB dependency to close cxl_fmws_get_all_sorted.
CONFIG_ARM_VIRT=y
CONFIG_PXB=y
CONFIG_PCIE_PORT=y
CONFIG_CXL=y
CONFIG_CXL_MEM_DEVICE=y
