TARGET = niw_psp_to_pc
OBJS = src/main.o src/config.o src/input_protocol.o src/ui.o

INCDIR = include
CFLAGS = -O2 -G0 -Wall -Wextra -std=c11
CXXFLAGS = $(CFLAGS) -fno-exceptions -fno-rtti
ASFLAGS = $(CFLAGS)

BUILD_PRX = 1
PSP_FW_VERSION = 660
PSP_EBOOT_TITLE = niwPSPtoPC
PSP_EBOOT_ICON = assets/ICON0.PNG
PSP_EBOOT_PIC1 = assets/PIC1.PNG
EXTRA_TARGETS = EBOOT.PBP

# build.mak and the PSP compiler specs provide the standard user/network/
# utility stubs. Power and the physical WLAN-switch query need explicit libs.
LIBS = -lpsppower -lpspwlan

PSPSDK := $(shell psp-config --pspsdk-path)
include $(PSPSDK)/lib/build.mak

EBOOT.PBP: $(PSP_EBOOT_ICON) $(PSP_EBOOT_PIC1)
