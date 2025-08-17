# Orchestrating

Orchestration tools, in this context, means tying together disparate tools
to validate, build and deploy.

Common needs:
- dependency graphs (certain jobs must run after certain other jobs)
- Jobs invoke arbitrary CLI tools
- Jobs are a way of grouping code somewhat like a bash function.

## Makefile
Makefile can be used to order jobs, somewhat like a gitlab pipeline.

Bash2gitlab will generate a makefile when you decompile.

## Justfile
Justfile is like makefile, with fewer quirky design decisions.