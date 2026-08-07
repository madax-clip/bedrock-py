# bedrock-cli

`bedrock-cli` is the 0.2.1 scaffolding companion for the Bedrock ecosystem.

Its intended role is to provide CLI tooling for scaffolding, validation, inspection, and other developer workflows around Bedrock modular applications.

## Current status

The package provides project initialization, module scaffolding, and code generation. Its command surface remains
evolutionary; pin the 0.2 release line when reproducible scaffolding output matters.

## Intended responsibilities

The future CLI is expected to cover areas such as:

- workspace initialization
- module scaffolding
- CRUD/code generation helpers
- manifest validation
- dependency graph inspection
- project health checks

## Implementation note

The current package exists as an exploratory implementation area.
Its internal structure may change significantly once the Bedrock runtime contract is finalized.
