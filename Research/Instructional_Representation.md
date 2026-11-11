<a id="paper-instructional-representation"></a>
<a id="ir"></a>
<a id="ir-prose-program-boundary"></a>
# Instructional Representation & the Prose–Program Boundary

## Abstract

Language-model instructions often encode relationships such as scope, priority, reference identity, authority, and evidence that do not require executable program semantics. This paper defines **instructional representation** as a directly model-interpreted form that makes these relationships explicit while retaining natural-language meaning. It distinguishes instruction structure from program structure and situates instructional representation between structured documents and pseudocode. ArcGrav serves as an implementation example using familiar structural cues for references, hierarchy, priority, and operations. The resulting design principle is to match representational structure to semantic function: use program representations for procedural relationships and instructional representations for relationships governing how information should be interpreted and acted upon. Comparative benefits in interpretability, reliability, and operational efficiency remain empirical questions.

## Introduction

Large language models can interpret prose, structured documents, pseudocode, and programming languages through the same interface. This creates a representational question that conventional software does not face: **what form should an instruction take when its interpreter can understand both language and code?**

Within [Model-Native Structural Representation](./Model_Native_Structural_Representation.md), **structural representation** is the broader category of external representations that make task-relevant relationships explicit. **Instructional representation** is the narrower subtype examined here: representations specialized for relationships governing how information should be interpreted, prioritized, constrained, referenced, or acted upon while preserving natural-language semantic content.

Much structured prompting has understandably moved toward programming. Programming languages provide explicit hierarchy, reference, ordering, conditions, operations, and composition. Code-shaped prompts can therefore make relationships that are ambiguous in prose substantially more explicit.

However, this creates an immediate tension for pseudocode as a prompting endpoint: if a relationship is sufficiently procedural that it benefits from code-shaped representation, the model often already understands an established programming language that *expresses the same relationship*. At best, a new pseudolanguage can therefore be unnecessary indirection. At worst, increasingly novel syntax can trade away some of the recognition advantage supplied by widely represented languages without adding compensating semantics.

<a id="ir-program-structure"></a>
<a id="ir-instruction-structure"></a>
The useful distinction is not simply structured versus unstructured input. It is **program structure versus instruction structure**.

## Role Within the Research Program

Instructional representation is the model-interpreted, non-executable category within [MNSR](./Model_Native_Structural_Representation.md). This paper defines its boundaries and explains why explicit instruction structure need not become executable program structure.

## Structure Is Not Synonymous With Programming

If a prompt representation increasingly resembles a programming language—using functions, variables, methods, loops, branches, operators, and program-like control flow—then a basic question arises:

> **Why approximate code when the model already understands code?**

A model that understands:

```text
for document in documents:
    if is_relevant(document):
        collect(document)
```

obviously does not require a new pseudolanguage expressing essentially the same procedural relationship.

Established programming languages are heavily represented in model training corpora and carry widely shared structural associations. Their syntax, control flow, scoping conventions, and operator meanings are already recognizable to both models and people. A newly invented pseudolanguage must either reuse those associations or unnecessarily ask the model to infer new ones from context.

That creates a potential diminishing-return problem: **the closer a pseudolanguage moves toward ordinary program semantics, the less obvious its advantage over actual code becomes** -- the farther it moves away through novel operators, control structures, or conventions, the more it risks weakening the very recognition advantage that code-shaped representation was intended to provide. Whether that penalty appears in a particular model or task is empirical, but the design tradeoff is fundamental.

A code-shaped prompt language may still be useful when it intentionally relaxes executable semantics, abstracts implementation details, or introduces genuinely useful domain-specific constructs, but as its semantics approach those of an existing programming language, it acquires a burden of proof. Pseudolanguage must demonstrate what is gained by introducing novel syntax while giving up the executability, standardization, tooling, human familiarity, and extensive corpus representation of languages such as Python.

*The relevant comparison for code-shaped prompt languages is therefore not only:*

> **Prose vs. Pseudocode**

*but more importantly:*

> **Pseudocode vs. Actual Code**

The success of pseudocode over prose can demonstrate that explicit structure matters without demonstrating that pseudocode is the ideal endpoint. In many cases, if the desired representation is already fundamentally procedural, ordinary code or conventional pseudocode may be sufficient.

The narrower principle is:

> **Structure is beneficial, but structure is not synonymous with programming**

<a id="ir-instructional-representation"></a>
## The Missing Category: ***Instructional Representation***

**In plain language.** Instructional representation gives natural-language instructions explicit relationships such as scope, priority, evidence, and references without turning the instructions into executable code.

**The alternative to pseudocode is not necessarily structured prose (Markdown for instance)**

The category described here is not historically absent from human communication. Requirements documents, technical specifications, legal instruments, standards, procedures, and controlled forms of natural language have long used structure to make instructional relationships explicit. What is comparatively underdeveloped in LLM interaction is treating **instructional representation itself as a first-class category**, rather than treating it merely as formatted prose on one side or incomplete programming on the other.

Prompting discussions often move directly from prose and Markdown toward templates, schemas, pseudocode, or prompt-programming systems. In that framing, additional structure tends to be interpreted as movement toward programming. However, an instruction *can* become more explicit, compositional, and operational *without* becoming more program-like.

This matters because many prompts are fundamentally **instructions rather than programs**. Their important relationships concern things such as:

- Scope
- Context
- Authority
- Priority
- Evidence
- Constraints
- Interpretation
- Reference identity
- Requested transformations
- Output requirements

These concepts can be forced into programming constructs:

```text
context = [...]
constraints = [...]
authority = [...]
output_requirements = [...]
```

but doing so does not necessarily clarify their meaning. The resulting representation looks computational even when the underlying semantics are not:

- A priority is not inherently a variable
- Authority is not inherently a numeric value
- A contextual reference is not necessarily a runtime pointer
- A requirement is not naturally a function

The model is being told **how to interpret and act upon information**, not merely which computation to simulate.

This creates a useful representational space between ordinary structured prose and pseudocode: **instructional representation**. Its semantic content remains natural language, while relationships between pieces of that content are represented explicitly.

Treating this as a distinct LLM interaction design space changes the design question. Instead of asking how closely natural-language instructions can approximate programs, it asks which structural primitives make instructional semantics explicit with the least additional representational machinery. The relevant primitives are therefore not necessarily loops, functions, variables, and predicates. They may instead be authority, priority, scope, identity, dependency, constraint, evidence, transformation, and output obligation.

It also changes how such systems should be evaluated. An instructional representation need not be judged by parser completeness or programming-language expressiveness. More relevant questions include whether it improves instruction fidelity, reduces ambiguity, preserves relationships across long contexts, supports reuse without semantic drift, and does so efficiently across models and tasks.

<a id="ir-instructional-primitives"></a>
For example:

```text
[Evidence]:
- Customer record
- Verified audit record

Authority:
P0. Verified audit record
P1. Customer record

Constraint:
- Preserve disagreement when P0 sources conflict

Task:
=> Resolve the requested fields from [Evidence]
```

This representation has operational structure, but it does not present itself as source code. Its primitives describe instructional relationships rather than machine execution.

The "missing" category is therefore not a claim that instructional representation has never existed, it is the claim that for model interaction, there is value in recognizing **instructional representation as its own design target** rather than assuming that increasing structure should eventually converge on programming.

<a id="ir-model-native-instructional-representation"></a>
## Model-Native Instructional Representation

A model-native instructional representation is a directly model-interpreted, non-executable representation that preserves natural-language meaning while explicitly representing relationships important to instruction execution.

Its distinguishing properties are straightforward:

- **Direct interpretation** — no parser, compiler, renderer, or runtime supplies its semantics.
- **Natural-language substrate** — concepts can remain semantically open rather than becoming functions, types, or predicates.
- **Instructional primitives** — structure represents scope, hierarchy, priority, authority, reference, constraint, interpretation, and transformation.
- **Documentary form** — the representation reads primarily as structured instruction rather than source code.
- **Compositionality** — contextual units can be named, reused, combined, and operated upon.
- **Model-familiar cues** — surface syntax preferentially uses headings, lists, indentation, brackets, ordering markers, and arrows already common across natural and technical text.
- **Cross-model portability** — the representation remains directly usable across language-model families without model-specific parsers, runtimes, or prompt syntax.
- **Graceful interpretation** — meaning does not depend on parser-level syntactic validity; small formatting variations may affect interpretation without creating a formal syntax error.

The distinction from Markdown is also important. Markdown provides generic document structure. Instructional representation bridges instructional semantics to structural relationships—such as authority, priority, reference identity, constraint, and transformation—explicit. Markdown may serve as part of its surface substrate without itself defining those relationships.

The distinction from pseudocode is semantic rather than merely visual:

> **Pseudocode structures procedures. Instructional representation structures instructions.**

<a id="ir-representational-continuum"></a>
A useful continuum is therefore:

**Common Prose → Structured Documents → *Instructional Representation* → Pseudocode → Actual Code**

The boundaries are not absolute, but the dominant semantic role changes across the continuum.

<a id="ir-semantic-function-matching"></a>
## Representation Should Match Semantic Function

There is no reason to assume one representation is universally best.

For genuinely algorithmic relationships, actual code is often the natural representation. If a model is being asked to follow loops, state transitions, deterministic transformations, or numerical procedures, Python or another familiar programming language may provide clearer and more strongly learned semantics than an invented pseudolanguage. In that setting, pseudocode is useful only insofar as it adds flexibility or abstraction that actual code does not already provide.

For primarily instructional relationships, converting everything into code can introduce an unnecessary abstraction. Scope, evidence, authority, interpretation, priorities, and contextual constraints are already linguistic concepts. They may benefit from explicit structure without benefiting from programming semantics.

Hybrid tasks naturally combine both.

A software-development instruction, for example, may use ArcGrav structure for repository scope, priorities, constraints, and desired outcome while embedding actual source code for the computational material itself. A research task may use instructional representation for evidence authority and output requirements while using JSON or a schema for data that genuinely benefits from a formal representation.

This yields a simple principle:

> **Use program representations for program relationships and instructional representations for instruction relationships.**

<a id="ir-arcgrav-as-instructional-representation"></a>
## ArcGrav as Instructional Representation

ArcGrav is one implementation of this approach.

ArcGrav retains ordinary linguistic content while adding a small set of structural mechanisms for relationships that otherwise have to remain implicit:

```text
[Context]:
- Customer records
- Authority rules

[Constraint]:
P0. Preserve unresolved conflicts
P1. Do not infer missing values

Task:
=> Resolve [Context] following [Constraint]
```

Its section roles distinguish retrieval, framing, refinement, and execution. Named references establish reusable contextual identity. Priority notation expresses precedence. Indentation expresses hierarchy and binding. `=>` marks an operation or transformation.

These mechanisms do not attempt to reproduce a conventional programming grammar. Their purpose is to make relationships within an instruction explicit while allowing the meaning of the instruction to remain natural language.

That distinction is why describing ArcGrav only as a "prompt DSL" is misleading. The term places it beside systems whose primary abstraction is programming an LLM. ArcGrav instead aims to add operational structure to instruction without requiring the instruction to become a program.

The design principle is not that code-like representations are ineffective, it is that **instructional semantics should not be translated into program semantics unless doing so adds something useful**.

ArcGrav addresses the latter problem: its objective is not to convey natural language as code, but instead to structure information explicitly while allowing meaning to remain language.

**The broader claim is therefore modest but consequential:**
1. Structured model interaction does not need to converge on code
2. There is a distinct design space in which natural-language instructions can acquire explicit operational structure without becoming software

---

## Scope and Evidence Status

This paper establishes a representational category and a design principle. Comparative interpretation accuracy and downstream performance are evaluated in [Interpretive Efficiency](./ArcGrav_Interpretive_Efficiency.md) and related controlled studies rather than claimed here.

## Conclusion

Instruction structure and program structure serve different semantic functions. ArcGrav illustrates how a model can receive explicit scope, priority, references, and transformation roles while the substantive instruction remains natural language. The preferred representation matches the relationship being expressed rather than maximizing its resemblance to code.

## Related Papers

- [Model-Native Structural Representation](./Model_Native_Structural_Representation.md)
- [ArcGrav Interpretive Efficiency](./ArcGrav_Interpretive_Efficiency.md)
- [ArcGrav Syntax Efficiency](./ArcGrav_Syntax_Efficiency.md)
