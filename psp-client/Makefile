TARGET = niw_psp_to_pc
OBJS = src/main.o src/config.o src/input_protocol.o src/ui.o

INCDIR = include
CFLAGS = -O2 -G0 -Wall -Wextra -std=c11
SENDER_INPUT_MODE ?= peek
ifeq ($(SENDER_INPUT_MODE),read)
CFLAGS += -DNIW_SENDER_USE_READ=1
else ifneq ($(SENDER_INPUT_MODE),peek)
$(error SENDER_INPUT_MODE must be "read" or "peek")
endif
CXXFLAGS = $(CFLAGS) -fno-exceptions -fno-rtti
ASFLAGS = $(CFLAGS)

BUILD_PRX = 1
PSP_FW_VERSION = 660
PSP_EBOOT_TITLE = niwPSPtoPC
PSP_EBOOT_ICON = assets/ICON0.PNG
PSP_EBOOT_PIC1 = assets/PIC1.PNG
EXTRA_TARGETS = EBOOT.PBP

# build.mak and the PSP compiler specs provide the standard user/network/
# utility stubs. Power, WLAN and CFW user/kernel bridges need explicit libs.
LIBS = -lpsppower -lpspwlan -lpspsystemctrl_user -lpspkubridge

PSPSDK := $(shell psp-config --pspsdk-path)
include $(PSPSDK)/lib/build.mak

EBOOT.PBP: $(PSP_EBOOT_ICON) $(PSP_EBOOT_PIC1)
