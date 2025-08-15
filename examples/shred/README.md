# Shred Example

This decompiles a .gitlab-ci.yml file into the constituent bash files.

The use case is for someone who already has a set of gitlab pipelines full of bash and would like to start using
tooling for the bash. So the output folder is `src`. After the original is shredded, you back it up and start
editing the `/src/` files and compiling them to `.gitlab-ci.yml`