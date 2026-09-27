Extended view + OTCv8 aware range (from matheuscollier/forgottenserver@5ccdda0)
applied onto your existing src (auras/wings/shaders/custom items kept).

WHAT CHANGED
- NETWORKMESSAGE_MAXSIZE 44590 -> 65500
- AwareRange used for map send, walk strips, floor change, canSee()
- OTCv8: split map per floor with opcode 0x4B (avoids one giant 0x64)
- Opcode 0x42 parseChangeAwareRange / sendAwareRange
- Opcode 0x43 sendFeatures (GameExtendedOpcode + GameChangeMapAwareRange)
- Optional zlib packet compression (adler32 = 0 means compressed)
- CMake now requires ZLIB

CONFIG.LUA
Add:
  packetCompression = true

CLIENT (OTClientV8)
  g_game.enableFeature(GameChangeMapAwareRange)
  g_game.enableFeature(GameExtendedOpcode)
  g_game.changeMapAwareRange(25, 21)

map.h in this tree is already:
  maxClientViewportX = 14
  maxClientViewportY = 10
  maxViewportX/Y = those + 2

So 25x21 is allowed (clamped to odd numbers).

BUILD
You need zlib (vcpkg / system package). CMake finds ZLIB::ZLIB.

Do not enable extra OTCv8 features in sendFeatures unless your client
has the same feature IDs (GameMagicEffectU16 etc.). Only the two needed
for extended view are sent.

Official 10.98 clients still get classic 0x64 map packets.
