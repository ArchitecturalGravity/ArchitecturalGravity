- Inspect diagnostics
- *

OperationList:
=> - Act
=> 1. Act

IndentWidth:
   - Act

IndentMixed:
 	- Act

ParentBlockOpener:
- Parent
  - Child

OrderedParentColon:
1. Parent
  - Child

ListEmpty:
1. First
2.
3. Third

OperationMultiple:
=> => Act

LineEnding:
- Done.

BacktickWhitespace:
- `two words`

BindingSpacing:
=> Act↳
  - Child

TrailingWhitespace:
- Act 

[DuplicateSymbol]: first
[DuplicateSymbol]: second

Create AS [DuplicateAlias]
Create again AS [DuplicateAlias]

[Empty]:

[Outer]:
- [New]: value

Task:
- Use [Later]
[Later]: value
Task:
- Use [Undefined]

"""
""""
Literal inner fence exceeds the outer width
""""
"""

- "This line contains a "double" quote within it"

Result: value

=> Finish:
  - Child

- Invalid symbolic syntax: [Outer [Inner] tail]

MixedLists:
- 1. Mixed
P0. - Mixed

IncompleteOperation:
=>

MissingBindingChild:
=> Act ↳
- Peer

IndentJump:
    - Child

MissingAliasSource:
AS [MissingSource]

[BindingSource]: value

ReferenceBinding:
- Derive from [BindingSource]:
  - Child

[FirstOwner]:
- `shared`
- `unused`
- `parent`:
  - `child`:
    - `leaf`
    - Use `leaf`
  - Use `child`
- Use `parent`

[SecondOwner]:
- `shared`

MemberReferences:
- Use `shared`
- Use `undefined`
- Read [SecondOwner].unused
- Read [FirstOwner].parent.child.leaf

UnmatchedQuotes:
- "unique value"
- "Unique value"

Misspellings:
- Please recieve the mispelled document

Result: value

=> Finish:
  - Child

"""
Unclosed literal content
