[Blueprint]:
"""
Char_01: U+0048
Char_02: U+0065
Char_03: U+006C
Char_04: U+006C
Char_05: U+006F
Char_06: U+0020
Char_07: U+0057
Char_08: U+006F
Char_09: U+0072
Char_10: U+006C
Char_11: U+0064
Char_12: U+0021
"""

[CharacterFactory]:
- `value`
=> Create a fresh record whose `value` is the character decoded from the supplied Unicode code point

[Constraint]:
P0. Output only the assembled characters on one line

[Message]: []

Task:
1. Select Char_* entries from [Blueprint] in name order AS [Codes]
2. For each code point in [Codes] in order:
  => Invoke [CharacterFactory] and append its `value` to [Message]
3. Output [Message] ↳
  - Follow [Constraint]
