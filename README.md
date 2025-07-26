# bash2gitlab
Compile bash to yaml pipelines to get IDE support for bash and import bash from template repos

build.sh + template.yml = template.compiled.yml

And now you can import both the bash and template from template.compiled.yml. 

## Scenario
Your .gitlab-ci.yml pipelines are more bash than yaml. 1000s of lines of bash. But your IDE doesn't recognize
your bash as bash, it is a yaml string. You get syntax highlighting telling you that `script:` is a yaml key and that
is it.

So you extract the bash to a .sh file and execute it. But your job is mostly defined in a template in a centralized
repository. So the .sh file needs to be in every repo that imports the template. That's not good. You can't import
bash from the other repo.

Do you want to import the template from the centralized repo and clone the centralized repo to get the non-yaml files?
That requires additional permissions that a simple yaml import doesn't and clutters the file system.

## Name
Gitlab runners expect bash, sh or powershell. To use another shell, you have to use bash to execute a script in the other
shell.

## Special files
 
- global_variables.sh

## Out of scope
This doesn't inline include templates, only references to `.sh` files.

