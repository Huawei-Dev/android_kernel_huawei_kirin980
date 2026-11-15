# SPDX-License-Identifier: GPL-2.0
dtb-$(CONFIG_ARCH_HISI) += hi3660-hikey960.dtb
dtb-$(CONFIG_ARCH_HISI) += hi3798cv200-poplar.dtb
dtb-$(CONFIG_ARCH_HISI) += hi6220-hikey.dtb
dtb-$(CONFIG_ARCH_HISI) += hip05-d02.dtb
dtb-$(CONFIG_ARCH_HISI) += hip06-d03.dtb
dtb-$(CONFIG_ARCH_HISI) += hip07-d05.dtb

schumann_dtb_members := scm_w09_va.dtb

dtb-$(CONFIG_ARCH_HISI) += $(schumann_dtb_members)
dtb-$(CONFIG_ARCH_HISI) += schumann_catalog.dtb

# Assemble one FDT catalog from the 15 *compiled* DTBs. The Python tool
# validates the per-board identity and uses the kernel-built DTC only to
# pack the catalog; it does not recompile any board DTS file.
quiet_cmd_schumann_catalog = EVRCAT  $@
	cmd_schumann_catalog = python3 $(srctree)/arch/arm64/boot/dts/hisilicon/make_schumann_catalog.py \
	--output $@ --dtc $(DTC) \
	$(foreach m,$(schumann_dtb_members),--dtb $(obj)/$(m))

$(obj)/schumann_catalog.dtb: $(addprefix $(obj)/,$(schumann_dtb_members)) \
	$(srctree)/arch/arm64/boot/dts/hisilicon/make_schumann_catalog.py FORCE
	$(call if_changed,schumann_catalog)

targets += schumann_catalog.dtb

always		:= $(dtb-y)
subdir-y	:= $(dts-dirs)
clean-files	:= *.dtb schumann_catalog.dts
