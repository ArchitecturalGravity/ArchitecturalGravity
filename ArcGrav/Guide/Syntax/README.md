<a id="ag-arcgrav-syntax-reference"></a>
# ArcGrav Syntax Reference

This directory documents the core ArcGrav syntax used to structure, reference, and operate on context.

<a id="ag-syntax"></a>
## Syntax

<a id="ag-sectioning"></a>
### [Sectioning](Sectioning.md)
> Uses `Key:` headers to organize related information into explicitly scoped context sections.

<a id="ag-listing"></a>
### [Listing](Listing.md)
> Uses line prefixes to represent unordered values, ordered steps, and prioritized items.

<a id="ag-grouping"></a>
### [Grouping](Grouping.md)
> Uses indentation to establish parent-child hierarchy, nested scope, and contextual relationships.

<a id="ag-symbolic-referencing"></a>
### [Symbolic Referencing](Symbolic_Referencing.md)
> Uses bracket-wrapped identifiers such as `[Target]` to define and reuse explicitly anchored context.

<a id="ag-context-operation"></a>
### [Context Operation](Context_Operation.md)
> Uses `=>` to define an operation that transforms context rather than adding another context item.

<a id="ag-inline-representation"></a>
### [Inline Representation](Inline_Representation.md)
> Local interpretive forcing: bare content remains contextually interpreted, backticks identify exact structural names, and double quotes identify exact textual values.

<a id="ag-literal-quote-block"></a>
### [Literal Quote Block](Literal_Quote_Block.md)
> Uses triple double quotes (`"""`) to preserve multiline source material as a bounded literal value.

<a id="ag-explicit-block-binding"></a>
### [Explicit Block Binding](Block_Binding.md)
> Uses `↳` to bind an indented block to a complete preceding expression when ordinary `:` scope would be ambiguous.

<a id="ag-inline-aliasing"></a>
### [Inline Aliasing](Inline_Aliasing.md)
> Uses `AS` to assign the immediate prior context to a reusable symbolic reference.

<a id="ag-wildcarding"></a>
### [Wildcarding](Wildcarding.md)
> Uses `*` to represent matching values across filenames, paths, patterns, or context sets.
