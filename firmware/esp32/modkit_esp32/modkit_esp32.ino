// modkit_esp32.ino —— 只做入口。逻辑在 app.cpp（原因见 app.cpp 顶部注释）。
// 接线见 firmware/esp32/README.md。
#include "app.h"

void setup() { appSetup(); }
void loop() { appLoop(); }
