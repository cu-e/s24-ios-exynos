/* SPDX-License-Identifier: Apache-2.0 */
/* Exercise unmodified odin4 firmware parser, with an unopened USB object.
   This PIT fixture is synthetic; it does not qualify the phone's PIT. */
#include "firmware/firmware_package.h"
#include "core/logger.h"
#include <cstring>
int main(int argc,char **argv) {
    if (argc!=2) return 2;
    set_log_level(LogLevel::Verbose);
    PitTable pit; PitEntry e{};
    e.identifier=20;
    std::strcpy(e.partition_name,"RECOVERY");
    std::strcpy(e.file_name,"recovery.img");
    pit.entries.push_back(e);
    UsbDevice unopened;
    return static_cast<int>(process_tar_file(argv[1],unopened,pit,false,false,false,false));
}
