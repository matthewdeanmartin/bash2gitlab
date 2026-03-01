# A Survey of Modern Shell Orchestration: From Local Task Runners to Integrated CI/CD

## The Landscape of Automation and Orchestration

In modern software development, the automation of repetitive tasks is a foundational principle for achieving efficiency,
consistency, and speed. The tools that facilitate this automation exist on a wide spectrum, from simple command aliases
to sophisticated, multi-system orchestration platforms. Understanding the distinctions between these tools, the
paradigms they embody, and the contexts in which they operate is crucial for making informed architectural decisions.
This landscape has evolved significantly, driven by a continuous need to manage increasing complexity in software
projects and infrastructure.

### Defining the Spectrum: Command Runners, Task Runners, Build Systems, and Orchestrators

The terminology surrounding automation tools can often be ambiguous. A clearer understanding emerges when these tools
are categorized based on their primary function and level of abstraction.

At the most fundamental level are **command runners**, tools designed to execute specific, predefined system commands or
scripts.<sup>1</sup> Their main purpose is to provide a simple, memorable alias for commands that a developer already
has on their system, such as

cargo build or pytest.<sup>1</sup> They enhance developer ergonomics but typically lack complex control structures like
loops or conditional logic.

Slightly more advanced are **task runners**, which automate a broader range of repetitive processes in a project, such
as compiling code, running tests, and minifying files.<sup>2</sup> Unlike simple command runners, true task runners
often allow for the definition of more complex logic, such as iterating over files in a directory to perform an
action.<sup>1</sup> They are characterized by their ability to automate repetitive tasks, their modular structure
through plugins, and their capacity to integrate with other development tools like linters and preprocessors.<sup>
3</sup>

A **build system** is a specialized type of task runner with a primary focus on managing dependencies to construct a
final artifact, such as a program executable.<sup>6</sup> The canonical example, GNU Make, excels at determining which
parts of a large program need to be recompiled based on which source files have changed, thereby avoiding redundant
work.<sup>6</sup>

At the highest level of abstraction lies **orchestration**. Orchestration is not merely the automation of a single task
but the coordinated execution of multiple automated tasks across various systems, applications, and services to achieve
a complex, higher-order workflow.<sup>8</sup> An orchestrator manages dependencies between services, allocates resources
dynamically, and ensures that a sequence of processes—such as provisioning a server, configuring its operating system,
updating a firewall, and deploying an application—is performed in the correct order.<sup>8</sup> Tools like Kubernetes,
for container orchestration, and Jenkins, for orchestrating development pipelines, fall into this category.<sup>8</sup>

This hierarchy clarifies that the tools under review exist on a continuum of complexity. A command runner is a basic
task runner; a build system is a dependency-aware task runner; and an orchestrator coordinates the workflows composed of
these automated tasks.

### The Core Paradigm Shift: Understanding Imperative vs. Declarative Approaches

Underpinning the evolution of these tools is a critical paradigm shift from imperative to declarative methodologies.
This distinction is central to understanding their design and appropriate use cases.

* **Imperative Approach:** This paradigm focuses on the "how." The user provides a series of explicit, step-by-step
  commands that must be executed in a specific sequence to achieve the desired outcome.<sup>10</sup> Shell scripts are a
  classic example of the imperative approach, offering fine-grained control but placing the burden of managing state,
  error handling, and execution flow squarely on the developer.<sup>10</sup>
* **Declarative Approach:** This paradigm focuses on the "what." The user defines the desired final state of the system,
  and the underlying tool is responsible for determining the necessary steps to achieve and maintain that state.<sup>
  10</sup> This approach abstracts away the procedural complexity. Tools like Terraform and Kubernetes are prime
  examples; a user declares, "I want three servers with this configuration," and the tool handles the provisioning and
  reconciliation to match that declaration.<sup>10</sup> This model enhances simplicity and resilience, as the system
  can automatically correct any drift from the desired state.<sup>13</sup>

The tools discussed in this report embody these paradigms to varying degrees. Pure Bash scripting is fundamentally
imperative. Make is a hybrid: its dependency rules are declarative (stating that a target *depends on* its
prerequisites), but its recipes are imperative shell commands. Modern CI/CD systems like GitLab CI and GitHub Actions
are primarily declarative in their structure—the YAML file defines the pipeline's stages and jobs—but the steps within
those jobs execute imperative scripts.<sup>16</sup>

### Context is Key: Differentiating Local Execution from Remote, Event-Driven Pipelines

The final dimension for understanding these tools is their intended execution context, which generally falls into two
categories: the local development "inner loop" and the remote automation "outer loop."

* **Local Execution:** Tools like Make and Just are designed to be invoked manually by a developer on their local
  machine to perform project-specific tasks.<sup>17</sup> They are part of the inner development loop, providing
  immediate feedback for actions like building, testing, or linting code during the development process.
* **Remote, Event-Driven Pipelines:** CI/CD platforms such as GitLab CI and GitHub Actions are architected for
  automated, remote execution.<sup>19</sup> Their workflows are not typically triggered manually but by source control
  events, such as a \
  git push to a branch or the creation of a pull request.<sup>21</sup> These platforms form the core of the outer
  development loop, which automates the integration, validation, and delivery of code, ensuring quality and consistency
  for the entire team.

The progression from simple shell scripts to complex, declarative orchestration platforms is a direct response to the
escalating complexity of modern software. Early, monolithic applications could be managed with a few scripts.<sup>
24</sup> As projects incorporated more source files, the challenge of managing compilation dependencies gave rise to
build systems like

Make.<sup>7</sup> The web development era introduced a host of new repetitive, non-compilation tasks (e.g., asset
minification, transpilation), which led to the creation of generalized task runners like Grunt and Gulp.<sup>3</sup>
Finally, the shift to microservices, cloud infrastructure, and CI/CD created the need to coordinate automated tasks
across multiple, distributed systems, a problem solved by orchestration platforms.<sup>9</sup> This history reveals a
continuous layering of abstraction, with the declarative nature of modern CI/CD systems representing the current
state-of-the-art in managing this complexity by hiding the procedural "how" from the developer.

## Local Orchestration with File-Based Runners

For tasks executed within a developer's local environment, file-based runners provide a standardized and shareable way
to define and execute common project commands. GNU Make, the long-standing incumbent, and Just, a modern challenger,
represent two distinct philosophies in this space. While both use a simple text file to define tasks, their underlying
designs cater to fundamentally different use cases.

### The Progenitor: GNU Make and the Philosophy of Dependency Management

GNU Make is, first and foremost, a build system designed to solve a specific problem: efficiently recompiling large
programs by only rebuilding files whose dependencies have changed.<sup>6</sup> Its core principle is the dependency
graph, where a

target (usually a file) is updated by executing its recipe only if the target does not exist or if any of its
prerequisites (other files) have a more recent modification timestamp.<sup>7</sup>

A Makefile is composed of a series of rules, each with the following structure <sup>26</sup>:

    Makefile

target: prerequisite1 prerequisite2 \
&lt;tab>recipe_command \

The requirement of a literal tab character to indent recipe commands is a notorious syntactic quirk of Make.<sup>6</sup>

Despite its age, Make is a remarkably powerful tool, offering extensive features for creating complex build logic:

* **Variables (Macros):** Allow for the parameterization of commands and file paths, making Makefiles reusable and
  easier to maintain.<sup>26</sup>
* **Pattern Rules:** Use the % wildcard to define generic rules for transforming files, such as a rule to compile any .c
  file into a corresponding .o object file.<sup>6</sup>
* **Automatic Variables:** Special variables like $@ (the target name), $^ (all prerequisites), and $&lt; (the first
  prerequisite) enable the writing of concise, generic recipes.<sup>26</sup>
* **Functions:** Built-in functions for string manipulation (patsubst), shell command execution (shell), and list
  processing (filter) provide advanced scripting capabilities.<sup>6</sup>

However, Make's file-centric design becomes awkward when it is co-opted for tasks that do not produce file artifacts,
such as running tests or cleaning up a directory. For these cases, the .PHONY directive is necessary.<sup>17</sup> A
phony target tells

Make to always run the recipe, regardless of whether a file with that name exists or what its timestamp is. The
widespread use of .PHONY targets for commands like test, clean, and deploy is a strong indicator that Make is often used
as a general-purpose task runner, a role for which it was not originally designed.<sup>31</sup>

### The Modern Alternative: Just and the Command Runner Paradigm

Just is a modern tool that was created in direct response to the common practice of using Make as a command runner.<sup>
17</sup> It explicitly positions itself as a "handy way to save and run project-specific commands," not as a build
system.<sup>17</sup> It deliberately sheds the complexities of

Make that are irrelevant to this purpose, most notably file-based dependency checking and the .PHONY directive.<sup>
17</sup> In

Just, every recipe is effectively "phony" by default.

Recipes are defined in a file named justfile, with a syntax that is inspired by Make but is simpler and more
intuitive.<sup>17</sup>

Just is distributed as a single, dependency-free binary that runs on Linux, macOS, and Windows, requiring only a
standard sh-compatible shell.<sup>17</sup>

Key features that highlight its focus on developer experience include:

* **Simple Recipe Execution:** Running just &lt;recipe_name> executes the desired command. Invoking just with no
  arguments runs the first recipe in the file, which is often used as the default task.<sup>33</sup>
* **Recipe Listing:** The command just --list provides a clean, documented list of available recipes, a feature that
  requires a custom target in Make.<sup>33</sup>
* **Native Argument Passing:** Passing arguments to recipes is a first-class feature, with a clear and simple syntax, a
  common pain point in Make.<sup>33</sup>
* **Flexible Shells:** While sh is the default, Just allows specifying other shells like powershell or even using a
  shebang (#!) to write recipes in interpreted languages like Python.<sup>17</sup>
* **Recipe Dependencies:** Just supports dependencies between recipes, but unlike Make, a dependent recipe is *always*
  executed, reflecting the assumption that the user wants the full sequence of commands to run every time.<sup>35</sup>

The fundamental difference between these two tools lies in their handling of state. Make is a stateful system where the
state is the modification time of files on the filesystem. This makes it highly effective for its intended purpose:
avoiding the redundant work of recompilation in incremental builds. Just, by contrast, is stateless. Each invocation is
a fresh execution, independent of the filesystem's condition. This design makes it ideal for imperative actions like "
run tests" or "deploy to staging," where the developer's intent is to perform the action unconditionally. The existence
of the .PHONY target in Make can be seen as a workaround to force Make into a stateless mode for which it was not
designed. Just recognized this common usage pattern and built a tool that makes this stateless, command-running mode the
default and only behavior, thereby providing a more elegant and focused solution.

This philosophical split has led to a "great unbundling" of Make's dual roles as a dependency engine and a command
runner. Modern developers are increasingly opting for specialized tools. Just excels at the command-running aspect,
while other tools like Taskfile, with its checksum-based dependency checking, offer a more robust and modern take on the
dependency management aspect.<sup>18</sup>

### Table 1: Comparison of Local Task Runners

<table>
  <tr>
   <td>Feature
   </td>
   <td>GNU Make
   </td>
   <td>Just
   </td>
   <td>Taskfile
   </td>
  </tr>
  <tr>
   <td><strong>Primary Philosophy</strong>
   </td>
   <td>Build System <sup>6</sup>
   </td>
   <td>Command Runner <sup>17</sup>
   </td>
   <td>Task Runner / Build Tool <sup>37</sup>
   </td>
  </tr>
  <tr>
   <td><strong>Dependency Checking</strong>
   </td>
   <td>Timestamp-based <sup>18</sup>
   </td>
   <td>None (by design) <sup>18</sup>
   </td>
   <td>Checksum-based <sup>18</sup>
   </td>
  </tr>
  <tr>
   <td><strong>Syntax</strong>
   </td>
   <td>Makefile (tabs required) <sup>6</sup>
   </td>
   <td>Justfile (Makefile-like) <sup>17</sup>
   </td>
   <td>Taskfile.yml (YAML) <sup>31</sup>
   </td>
  </tr>
  <tr>
   <td><strong>Cross-Platform Support</strong>
   </td>
   <td>High (with care) <sup>7</sup>
   </td>
   <td>Excellent (native binary) <sup>17</sup>
   </td>
   <td>Excellent (native binary) <sup>37</sup>
   </td>
  </tr>
  <tr>
   <td><strong>Argument Passing</strong>
   </td>
   <td>Basic (via variables) <sup>26</sup>
   </td>
   <td>Advanced (native) <sup>33</sup>
   </td>
   <td>Advanced (templates) <sup>37</sup>
   </td>
  </tr>
  <tr>
   <td><strong>Recipe Listing</strong>
   </td>
   <td>Requires custom target
   </td>
   <td>Built-in (--list) <sup>33</sup>
   </td>
   <td>Built-in (--list) <sup>37</sup>
   </td>
  </tr>
  <tr>
   <td><strong>Installation</strong>
   </td>
   <td>Ubiquitous on Unix-like systems
   </td>
   <td>Single binary <sup>17</sup>
   </td>
   <td>Single binary <sup>37</sup>
   </td>
  </tr>
</table>

## The Power and Pitfalls of Pure Bash Orchestration

Before the widespread adoption of dedicated task runners and CI/CD platforms, the Bourne Again Shell (Bash) was the de
facto tool for automation and orchestration on Unix-like systems. Its universal availability and powerful scripting
capabilities make it a viable, if challenging, choice for coordinating complex workflows. Understanding how to leverage
pure Bash, particularly for parallel execution, provides a foundational perspective on the problems that higher-level
tools aim to solve.

### Bash as an Orchestration Engine

At its core, Bash automation involves writing scripts—text files containing a sequence of shell commands—to automate
repetitive or complex processes.<sup>38</sup> These scripts are often described as an "early orchestration version,"
capable of managing tasks from file manipulation and system configuration to full software deployment workflows.<sup>
24</sup>

The power of Bash for orchestration stems from several key features:

* **Universal Availability:** Bash is the default shell on most Linux distributions and macOS, and is readily available
  on Windows via subsystems, making scripts highly portable across developer machines and servers.
* **Control Structures:** Bash provides a full suite of programming constructs, including if-else statements for
  conditional logic, case statements for multi-way branching, for and while loops for iteration, and functions for
  creating modular, reusable code blocks.<sup>25</sup>
* **The Unix Philosophy:** Bash excels at embodying the Unix philosophy of "do one thing and do it well." Complex
  workflows can be constructed by chaining together small, specialized command-line utilities (like grep, sed, awk,
  curl) using pipes (|), where the output of one command becomes the input for the next.<sup>24</sup>

However, relying solely on Bash for complex orchestration has significant drawbacks. As scripts grow in length and
complexity, they can become difficult to read, maintain, and debug.<sup>43</sup> They lack the declarative structure
that makes workflows in tools like GitLab CI or GitHub Actions easy to visualize and understand. Error handling, state
management, and dependency logic must all be implemented manually, placing a high cognitive burden on the
developer.<sup>1</sup> This often leads to the creation of brittle, ad-hoc frameworks that are understood only by their
original author.

### Unleashing Concurrency: A Deep Dive into Bash Parallelism

One of the most powerful capabilities of Bash is its ability to execute tasks concurrently. This is essential for
performance-critical orchestration, such as processing large datasets or running independent tests simultaneously. There
are three primary methods for achieving parallelism in Bash, each with distinct trade-offs in terms of simplicity and
control.

#### Simple Parallelism with & and wait

The most fundamental mechanism for parallelism in Bash involves the & operator and the wait command.

* **The Ampersand (&):** Placing an ampersand at the end of a command instructs the shell to execute it in the
  background. The script does not pause for the command to finish and immediately proceeds to the next line.<sup>
  44</sup>
* **The wait Command:** This built-in command pauses the script's execution until all child processes running in the
  background have completed.<sup>44</sup>

This combination is perfect for running a known, finite number of independent tasks in parallel.

**Example: Parallel Downloads**

```Bash

#!/bin/bash
for id in 237 238 239; do
    echo "Downloading image $id..."
    wget -q https://example.com/img$id.jpg &
done

echo "Waiting for all downloads to complete..."
wait
echo "All downloads finished."
```

In this example, the for loop initiates three wget processes in the background. The script then immediately reaches the
wait command, where it pauses until all three downloads are complete before printing the final message.

#### Advanced Parallelism with xargs

For data parallelism—applying the same command to a large list of inputs—xargs is a powerful and widely available
tool.<sup>47</sup> While its primary function is to build command lines from standard input, its

-P option enables parallel execution.

* **xargs -P &lt;max-procs>:** The -P flag tells xargs to run up to &lt;max-procs> processes simultaneously. If set to
  0, xargs will run as many processes as possible.<sup>44</sup> This is invaluable for efficiently utilizing multi-core
  processors.
* **Handling Special Characters:** xargs is often paired with find -print0, which separates filenames with a null
  character instead of a newline. The corresponding xargs -0 option correctly interprets this input, making the pipeline
  robust against filenames containing spaces or other special characters.<sup>44</sup>

**Example: Parallel File Compression**

```Bash
#!/bin/bash
# Find all.log files and compress them using up to 4 parallel processes
find. -type f -name '*.log' -print0 | xargs -0 -P 4 gzip
echo "All log files have been compressed."
```

This one-liner efficiently finds and compresses a large number of files, automatically managing the pool of worker
processes.

#### Maximum Control with GNU parallel

For the most complex parallel processing scenarios, GNU parallel is the tool of choice. It is a feature-rich utility
designed specifically for this purpose, offering capabilities far beyond those of xargs.<sup>48</sup>

Key features of GNU parallel include:

* **Job Control:** It provides fine-grained control over the number of parallel jobs (-j).<sup>49</sup>
* **Output Management:** It can guarantee that the output from parallel jobs is printed in the same order as the input (
  --keep-order or -k), preventing interleaved and confusing logs.<sup>44</sup>
* **Remote Execution:** It can distribute jobs across multiple machines via SSH (--sshloginfile), turning a cluster of
  machines into a single parallel processing grid.<sup>49</sup>
* **Resilience:** It can log the progress of jobs (--joblog) and resume an interrupted run (--resume), which is critical
  for long-running tasks.<sup>52</sup>
* **Flexible Input:** It accepts input from standard input (pipes), from command-line arguments using the ::: separator,
  or from a file using the -a flag.<sup>52</sup>

**Example: Running a Complex Command with Ordered Output**

```Bash
#!/bin/bash
# Process a list of servers, ensuring output is printed in order
cat server_list.txt | parallel -j 8 --keep-order 'echo "Processing {}"; ssh {} "uptime"'
```

In this scenario, GNU parallel will SSH into up to eight servers at a time to get their uptime, but it will buffer the
output to ensure that the results are printed in the same order as the servers appeared in server_list.txt.

In summary, while pure Bash offers the ultimate imperative control, this flexibility comes at the cost of increased
developer responsibility. As orchestration requirements scale, particularly around parallelism and error handling, a
developer using only Bash will often find themselves re-implementing features that are provided out-of-the-box by
standardized tools. The journey from a simple script to one that manages concurrency with process limits and error
checking demonstrates the inherent value of adopting more structured tools like xargs or, for maximum power, GNU
parallel.

## Cloud-Native Orchestration: YAML-Based CI/CD Platforms

While local tools are essential for the inner development loop, modern software delivery relies on remote, automated
platforms for the outer loop of integration, testing, and deployment. Cloud-native Continuous Integration and Continuous
Delivery (CI/CD) systems, such as GitLab CI/CD and GitHub Actions, have become the standard for this purpose. They
operate on a declarative model, where the entire workflow is defined as code in YAML files stored within the project's
repository, enabling version-controlled, auditable, and repeatable automation.

### Core Concepts of Modern CI/CD

Despite differences in syntax and philosophy, modern CI/CD platforms are built upon a common set of core concepts:

* **Pipeline as Code:** The entire CI/CD process is defined in one or more YAML files (e.g., .gitlab-ci.yml or files in
  .github/workflows/) that live alongside the application code. This practice ensures that changes to the delivery
  process are versioned, reviewed, and auditable.<sup>20</sup>
* **Event-Driven Automation:** Pipelines are not typically run manually. Instead, they are automatically triggered by
  events in the source code repository, such as a push to a branch, the creation of a merge request or pull request, or
  on a predefined schedule.<sup>21</sup> This tight integration with the version control system is a key advantage over
  standalone scripting.
* **Runners:** These are the agents or virtual machines that execute the tasks defined in the pipeline. They can be
  hosted by the platform provider (e.g., GitLab.com, GitHub-hosted) or self-hosted on a company's own infrastructure,
  providing flexibility in terms of performance, security, and environment customization.<sup>22</sup>
* **Jobs and Stages:** A pipeline is composed of **jobs**, which are discrete sets of commands or scripts that
  accomplish a specific task like compiling code or running tests. Jobs are often grouped into **stages** (e.g., build,
  test, deploy). Typically, all jobs within a single stage run in parallel, and stages are executed sequentially. A
  failure in one stage usually prevents subsequent stages from running, acting as a quality gate.<sup>21</sup>
* **Artifacts and Caching:** **Artifacts** are files (like binaries or test reports) produced by one job that can be
  passed to subsequent jobs in later stages. **Caching** is used to store dependencies (like node_modules or Maven
  packages) between pipeline runs to speed up execution time.<sup>58</sup>

### Deep Dive: GitLab CI/CD

GitLab CI/CD is presented as a single, fully integrated DevOps platform, where CI/CD is a core component rather than a
separate product. This results in a tightly coupled, centralized, and often more opinionated user experience.<sup>
61</sup>

#### Mastering .gitlab-ci.yml

The entire pipeline configuration for a project is typically defined in a single file named .gitlab-ci.yml at the
repository's root.<sup>55</sup> This centralized approach provides a single source of truth for the project's entire
CI/CD process.

Key keywords in .gitlab-ci.yml include:

* stages: Defines the sequence of stages for the pipeline (e.g., [build, test, deploy]).
* image: Specifies the Docker image to use for a job, ensuring a consistent and isolated execution environment.
* script, before_script, after_script: Define the shell commands to be executed by the runner.
* rules: Provides a powerful mechanism for conditionally including or excluding jobs from a pipeline based on variables
  like the branch name or commit message.
* needs: Allows the creation of a Directed Acyclic Graph (DAG) of jobs, enabling jobs to run as soon as their specific
  dependencies are met, rather than waiting for an entire stage to complete.<sup>58</sup>

#### Advanced Features

* **Reusability with include:** GitLab's primary mechanism for code reuse is the include keyword. It allows a
  .gitlab-ci.yml file to import configuration from other YAML files. These can be local files within the same
  repository, files from other projects on the same GitLab instance, templates from a remote URL, or built-in templates
  provided by GitLab.<sup>58</sup> This feature is particularly powerful for enforcing organizational standards, where a
  central platform team can maintain common pipeline templates that other projects include.
* **Secret Management:** GitLab manages secrets through CI/CD variables, which can be defined at the project, group, or
  instance level. Variables can be "protected" to be available only on protected branches or tags, and "masked" to be
  redacted from job logs.<sup>55</sup> For more advanced use cases, GitLab offers native integration with external
  secret managers like HashiCorp Vault, Azure Key Vault, and Google Cloud Secret Manager, allowing secrets to be fetched
  dynamically at runtime.<sup>64</sup>
* **Runners and Environments:** GitLab Runners are agents that poll the GitLab instance for jobs. The Shell executor is
  a specific type of runner that executes jobs directly on the host machine, which has significant security implications
  as jobs could potentially access data from other projects on the same machine.<sup>66</sup> Environments are a
  first-class concept in GitLab, allowing users to track deployments to specific environments like \
  staging or production.<sup>58</sup>

### Deep Dive: GitHub Actions

GitHub Actions is designed as a more decentralized and composable CI/CD platform, deeply integrated with the GitHub
ecosystem and centered around a marketplace of reusable components called "actions".<sup>61</sup>

#### Mastering Workflow Files

Unlike GitLab's single-file approach, GitHub Actions configurations are defined in multiple YAML files located in the
.github/workflows/ directory. Each file represents a separate workflow, which can be triggered by different events.<sup>
20</sup>

Key keywords in a GitHub Actions workflow file include:

* on: Specifies the event(s) that trigger the workflow, such as push, pull_request, or workflow_dispatch for manual
  runs.
* jobs: Defines one or more jobs that make up the workflow.
* runs-on: Specifies the type of runner for a job (e.g., ubuntu-latest, windows-latest, or a self-hosted runner label).
* steps: A sequence of tasks within a job. Each step can either run a shell command or uses a reusable action.
* if: Provides conditional execution for jobs or steps.
* strategy: matrix: A powerful feature that creates multiple jobs by performing variable substitution in a job
  definition, ideal for testing across different platforms or language versions.<sup>20</sup>

#### Advanced Features

* **Reusability with Actions and Reusable Workflows:** GitHub's reusability model is multifaceted. The primary unit of
  reuse is an **action**, a packaged script or set of commands that can be published to the GitHub Marketplace and
  easily consumed by any workflow with the uses keyword.<sup>61</sup> For more complex logic, developers can create \
  **Composite Actions** to bundle multiple steps into a single action within their repository, or **Reusable Workflows**
  to call an entire workflow file from another, passing inputs and secrets.<sup>62</sup>
* **Secret Management:** Secrets are managed as encrypted environment variables at three levels: repository,
  environment, and organization.<sup>71</sup> \
  **Environment secrets** are particularly powerful, as they can be combined with environment protection rules that
  require manual approval from a designated reviewer before a job can access them, providing a crucial safeguard for
  production deployments.<sup>71</sup> GitHub Actions also strongly supports OpenID Connect (OIDC) for passwordless
  authentication to major cloud providers, which is considered a best practice.<sup>71</sup>
* **Runners and Environments:** GitHub-hosted runners provide a fresh, isolated virtual machine for every job, enhancing
  security and ensuring a clean environment.<sup>75</sup> Self-hosted runners are also supported for custom needs.
  Environments can be configured with protection rules, such as required reviewers or deployment branch restrictions, to
  control the deployment process.<sup>60</sup>

The value of these YAML-based platforms extends beyond simple automation. They provide a framework for codified
governance. The YAML file becomes a policy document, version-controlled and subject to review, that defines and enforces
how software is built, tested, and deployed across an organization. This transforms what might have been an
inconsistent, manual process into a standardized, auditable, and reliable corporate asset.

Furthermore, the contrasting reusability models of GitLab and GitHub reflect different organizational philosophies.
GitLab's include mechanism is well-suited for a top-down, centralized governance model, where a platform team provides
standard templates. GitHub's Marketplace and action-centric model foster a more bottom-up, federated approach, where
teams can create and share components in an open-source-like ecosystem. The choice between them depends not only on
technical features but also on the desired organizational structure and culture.

## A Comparative Framework for Strategic Tool Selection

Choosing the right orchestration tool requires a nuanced understanding of the trade-offs between local and remote
execution, imperative and declarative paradigms, and the specific features of each system. A direct comparison across
key dimensions reveals the distinct strengths and ideal use cases for pure Bash, GNU Make, Just, GitLab CI, and GitHub
Actions.

### Analysis of Key Differentiators

#### State and Dependency Management

The handling of state and dependencies is a primary differentiator.

* **GNU Make** uses file modification timestamps to create a dependency graph, making it highly efficient for
  incremental builds where avoiding redundant work is paramount.<sup>18</sup>
* **Just** is intentionally stateless. It does not check file dependencies and always executes recipes when called,
  prioritizing predictable command execution over incremental builds.<sup>18</sup>
* **Pure Bash** requires the developer to manage state and dependencies manually, a complex and error-prone task.
* **GitLab CI and GitHub Actions** manage dependencies between jobs declaratively using the needs keyword. They manage
  state between pipeline runs through a combination of artifacts (passing files between jobs) and caching (persisting
  dependencies).<sup>58</sup>

#### Reusability and Modularity

Each tool offers a different approach to creating reusable logic.

* **Bash:** Reusability is achieved through functions and the source command to include other scripts. This is flexible
  but lacks a formal packaging or discovery mechanism.
* **GitLab CI:** The include keyword is the primary mechanism, allowing for the inclusion of local files, templates from
  other projects, or remote files. This promotes a centralized, template-driven approach to reuse.<sup>58</sup>
* **GitHub Actions:** Offers a multi-layered reusability model with composite actions (bundling steps), reusable
  workflows (calling entire workflows), and a vast public Marketplace of third-party actions. This fosters a
  decentralized, ecosystem-driven approach.<sup>62</sup>

#### Environment and Secret Management

The management of execution environments and sensitive data marks a significant gap between local tools and integrated
platforms.

* **Local Tools (Bash, Make, Just):** Environment setup is a manual process, often relying on developers to have the
  correct tools and libraries installed. Secrets are typically managed through environment variables or .env files,
  which can be insecure and inconsistent across different machines.<sup>16</sup>
* **CI/CD Platforms (GitLab, GitHub):** Environments are defined and controlled as part of the pipeline. Jobs run in
  consistent, isolated containers or virtual machines.<sup>56</sup> Secret management is a core, integrated feature,
  offering encrypted storage, role-based access control, audit logs, and secure injection into jobs. Both platforms also
  support advanced features like integration with external vaults (GitLab) and OIDC for passwordless authentication (
  GitHub).<sup>64</sup>

#### Developer Experience and Learning Curve

The ease of use and cognitive overhead vary significantly.

* **Bash and Make:** Are ubiquitous in Unix-like environments but have idiosyncratic syntax and a steep learning curve
  for advanced features.<sup>31</sup>
* **Just:** Is designed for a superior developer experience with a simple, clean syntax, helpful error messages, and
  intuitive features like recipe listing and argument passing.<sup>31</sup>
* **GitLab CI and GitHub Actions:** Require learning a specific YAML-based domain-specific language (DSL). While
  powerful, this can be complex, and each platform has its own set of keywords and concepts. GitHub Actions is often
  considered slightly easier for beginners due to its event-driven model and extensive Marketplace, while GitLab CI is
  seen as more powerful but with a steeper learning curve for complex pipelines.<sup>61</sup>

### Comprehensive Orchestration Tool Matrix

The following table provides a summary comparison across the key dimensions of orchestration.


<table>
  <tr>
   <td>Dimension
   </td>
   <td>Pure Bash
   </td>
   <td>GNU Make
   </td>
   <td>Just
   </td>
   <td>GitLab CI
   </td>
   <td>GitHub Actions
   </td>
  </tr>
  <tr>
   <td><strong>Paradigm</strong>
   </td>
   <td>Imperative
   </td>
   <td>Hybrid
   </td>
   <td>Imperative
   </td>
   <td>Declarative/Imperative
   </td>
   <td>Declarative/Imperative
   </td>
  </tr>
  <tr>
   <td><strong>Execution Context</strong>
   </td>
   <td>Local
   </td>
   <td>Local
   </td>
   <td>Local
   </td>
   <td>Remote/Event-Driven
   </td>
   <td>Remote/Event-Driven
   </td>
  </tr>
  <tr>
   <td><strong>Setup Complexity</strong>
   </td>
   <td>None (Built-in)
   </td>
   <td>None (Built-in)
   </td>
   <td>Low (Single Binary)
   </td>
   <td>Medium (Platform Config)
   </td>
   <td>Medium (Platform Config)
   </td>
  </tr>
  <tr>
   <td><strong>Dependency Mgmt</strong>
   </td>
   <td>Manual
   </td>
   <td>Timestamp-based
   </td>
   <td>None
   </td>
   <td>needs / Artifacts
   </td>
   <td>needs / Artifacts
   </td>
  </tr>
  <tr>
   <td><strong>Parallelism</strong>
   </td>
   <td>Manual (&, xargs)
   </td>
   <td>Basic (-j)
   </td>
   <td>None (by design)
   </td>
   <td>High (per Stage/needs)
   </td>
   <td>High (per Job/matrix)
   </td>
  </tr>
  <tr>
   <td><strong>Reusability</strong>
   </td>
   <td>Functions / source
   </td>
   <td>include (limited)
   </td>
   <td>None
   </td>
   <td>include / Components
   </td>
   <td>Actions / Workflows
   </td>
  </tr>
  <tr>
   <td><strong>Secret Management</strong>
   </td>
   <td>Manual (Env Vars)
   </td>
   <td>Manual (Env Vars)
   </td>
   <td>Manual (Env Vars)
   </td>
   <td>Integrated (Variables/Vault)
   </td>
   <td>Integrated (Secrets/OIDC)
   </td>
  </tr>
  <tr>
   <td><strong>Environment Control</strong>
   </td>
   <td>Manual / Docker
   </td>
   <td>Manual / Docker
   </td>
   <td>Manual / Docker
   </td>
   <td>Runners / Containers
   </td>
   <td>Runners / Containers
   </td>
  </tr>
  <tr>
   <td><strong>Ecosystem</strong>
   </td>
   <td>OS Tools
   </td>
   <td>Limited
   </td>
   <td>Growing
   </td>
   <td>Integrated Platform
   </td>
   <td>Marketplace
   </td>
  </tr>
</table>

### Recommendations and Decision Guide

The optimal tool depends heavily on the project's context, scale, and governance requirements.

* **For Small Personal Projects or CLI Tools:** Just is an excellent choice for creating simple, memorable aliases for
  common commands like build, test, and run. If the project involves a compilation step where incremental builds offer a
  significant performance benefit, GNU Make remains a solid option. Simple, one-off setup tasks can be handled by a pure
  bash script.
* **For an Open-Source Library (e.g., hosted on GitHub):** GitHub Actions is the natural and expected choice for
  continuous integration. Its free tier for public repositories and seamless integration with pull requests make it
  ideal. A Justfile or Makefile can be included in the repository to provide a consistent local development experience
  for contributors.
* **For a Complex Monorepo with Multiple Services:** A powerful CI/CD platform is non-negotiable. GitLab CI offers
  strong features for managing complex pipelines, such as parent-child pipelines and the centralized include mechanism
  for enforcing standards. Within each service's subdirectory, a Justfile can be used to standardize local development
  commands (e.g., just test, just build, just run-local), providing a consistent interface for developers regardless of
  the underlying technology of the service.
* **For an Enterprise Application with Strict Governance and Security Requirements:** GitLab CI is often favored in
  these environments due to its all-in-one platform approach, which includes integrated security scanning, compliance
  features, and robust role-based access controls. The ability to use include to enforce standardized, centrally managed
  pipeline templates is a significant advantage for governance. The use of self-hosted runners provides complete control
  over the execution environment and infrastructure.

## Conclusion: The Future of Shell-Based Orchestration

The journey from simple shell scripts to sophisticated, declarative CI/CD platforms illustrates a clear and persistent
trend in software engineering: the continuous abstraction of complexity. While the shell remains the fundamental
execution layer—the universal runtime for getting things done on a server—the way developers interact with it has
fundamentally changed. The cognitive burden of manually scripting complex, stateful, and concurrent workflows has proven
to be a significant bottleneck, driving the adoption of higher-level tools that manage this complexity on the
developer's behalf.

Pure Bash scripting offers unparalleled control and flexibility but demands the most from the developer, who must act as
the architect of their own orchestration framework. Tools like GNU Make introduced a crucial declarative concept—the
dependency graph—to solve the specific problem of incremental builds, but its file-centric design and idiosyncratic
syntax make it an awkward fit for general-purpose task running. Modern command runners like Just represent a direct
response to this, unbundling Make's features to create a stateless, ergonomic tool focused exclusively on running
commands, thereby optimizing for the developer's inner loop.

The most significant evolution, however, has been the rise of integrated, YAML-based CI/CD platforms like GitLab CI and
GitHub Actions. These systems are not merely task runners; they are comprehensive orchestration engines that provide
codified, version-controlled governance over the entire software delivery lifecycle. By abstracting away the
complexities of environment provisioning, secret management, concurrency, and dependency flow, they allow developers to
focus on the declarative "what" of their pipeline, rather than the imperative "how." The choice between GitLab's
centralized model and GitHub's ecosystem-driven approach reflects different philosophies on how to achieve reusability
and standardization at scale, but both lead to more secure, reliable, and maintainable automation.

The current state-of-the-art for most development teams is a hybrid approach. A simple, local runner like Just provides
a fast, consistent, and user-friendly interface for day-to-day development tasks—the inner loop. In parallel, a
powerful, integrated CI/CD platform automates the build, validation, and deployment pipeline—the outer loop—enforcing
quality and governance for the entire team. This combination leverages the best of both worlds: the immediate,
imperative control needed for local development and the robust, declarative abstraction required for modern,
cloud-native software delivery. The shell is not being replaced; it is being orchestrated.

#### Works cited

1. Why you should use a task runner and not a command runner. Seriously! | by David Danier, accessed August 17,
   2025, [https://medium.com/@david.danier/why-you-should-use-a-task-runner-and-not-a-command-runner-seriously-5efb56a6ec63](https://medium.com/@david.danier/why-you-should-use-a-task-runner-and-not-a-command-runner-seriously-5efb56a6ec63)
2. www.educative.io, accessed August 17,
   2025, [https://www.educative.io/answers/what-is-a-javascript-task-runner#:~:text=To%20summarize%2C%20a%20task%20runner,enhancing%20code%2C%20and%20managing%20dependencies.](https://www.educative.io/answers/what-is-a-javascript-task-runner#:~:text=To%20summarize%2C%20a%20task%20runner,enhancing%20code%2C%20and%20managing%20dependencies.)
3. Task Runners (Gulp, Grunt) - Dataforest, accessed August 17,
   2025, [https://dataforest.ai/glossary/task-runners-gulp-grunt](https://dataforest.ai/glossary/task-runners-gulp-grunt)
4. Grunt: The JavaScript Task Runner, accessed August 17, 2025, [https://gruntjs.com/](https://gruntjs.com/)
5. Task Runners & Build Automation Tools 2024 - KVY TECH, accessed August 17,
   2025, [https://kvytechnology.com/blog/software/task-runners-and-build-automation-tools/](https://kvytechnology.com/blog/software/task-runners-and-build-automation-tools/)
6. Makefile Tutorial By Example, accessed August 17,
   2025, [https://makefiletutorial.com/](https://makefiletutorial.com/)
7. CS107 Guide to makefiles, accessed August 17,
   2025, [https://web.stanford.edu/class/archive/cs/cs107/cs107.1174/guide_make.html](https://web.stanford.edu/class/archive/cs/cs107/cs107.1174/guide_make.html)
8. What is orchestration? - Red Hat, accessed August 17,
   2025, [https://www.redhat.com/en/topics/automation/what-is-orchestration](https://www.redhat.com/en/topics/automation/what-is-orchestration)
9. What is Orchestration in Software Development? - Xygeni, accessed August 17,
   2025, [https://xygeni.io/sscs-glossary/what-is-orchestration-in-software-development/](https://xygeni.io/sscs-glossary/what-is-orchestration-in-software-development/)
10. Everything You Need to Know When Assessing Declarative vs Imperative Skills - Alooba, accessed August 17,
    2025, [https://www.alooba.com/skills/concepts/infrastructure-as-code-iac-588/declarative-vs-imperative/](https://www.alooba.com/skills/concepts/infrastructure-as-code-iac-588/declarative-vs-imperative/)
11. Declarative vs. Imperative Programming: 4 Key Differences | Codefresh, accessed August 17,
    2025, [https://codefresh.io/learn/infrastructure-as-code/declarative-vs-imperative-programming-4-key-differences/](https://codefresh.io/learn/infrastructure-as-code/declarative-vs-imperative-programming-4-key-differences/)
12. The Data Engineers Guide to Declarative vs Imperative for Data - DataOps.live, accessed August 17,
    2025, [https://www.dataops.live/blog/the-data-engineers-guide-to-declarative-vs-imperative-for-data](https://www.dataops.live/blog/the-data-engineers-guide-to-declarative-vs-imperative-for-data)
13. Terraform: Declarative vs. Imperative Approaches in Infrastructure as Code - Medium, accessed August 17,
    2025, [https://medium.com/@beingkh/terraform-declarative-vs-imperative-in-infrastructure-as-code-e87ca6fe114c](https://medium.com/@beingkh/terraform-declarative-vs-imperative-in-infrastructure-as-code-e87ca6fe114c)
14. Declarative vs Imperative: DevOps done right - Ubuntu, accessed August 17,
    2025, [https://ubuntu.com/blog/declarative-vs-imperative-devops-done-right](https://ubuntu.com/blog/declarative-vs-imperative-devops-done-right)
15. The Shift to Declarative Continuous Deployment | DEVOPSdigest, accessed August 17,
    2025, [https://www.devopsdigest.com/declarative-continuous-deployment](https://www.devopsdigest.com/declarative-continuous-deployment)
16. Gitlab CI is still the best CI in the game IMO, but GitHub Actions ..., accessed August 17,
    2025, [https://news.ycombinator.com/item?id=38508705](https://news.ycombinator.com/item?id=38508705)
17. casey/just: Just a command runner - GitHub, accessed August 17,
    2025, [https://github.com/casey/just](https://github.com/casey/just)
18. Just Make a Task (Make vs. Taskfile vs. Just) · Applied Go, accessed August 17,
    2025, [https://appliedgo.net/spotlight/just-make-a-task/](https://appliedgo.net/spotlight/just-make-a-task/)
19. Ultimate guide to CI/CD: Fundamentals to advanced implementation - GitLab, accessed August 17,
    2025, [https://about.gitlab.com/blog/ultimate-guide-to-ci-cd-fundamentals-to-advanced-implementation/](https://about.gitlab.com/blog/ultimate-guide-to-ci-cd-fundamentals-to-advanced-implementation/)
20. GitHub actions beginner guide - Graphite, accessed August 17,
    2025, [https://graphite.dev/guides/github-actions-beginner-guide](https://graphite.dev/guides/github-actions-beginner-guide)
21. CI/CD pipelines | GitLab Docs, accessed August 17,
    2025, [https://docs.gitlab.com/ci/pipelines/](https://docs.gitlab.com/ci/pipelines/)
22. Understanding GitHub Actions - GitHub Enterprise Cloud Docs, accessed August 17,
    2025, [https://docs.github.com/enterprise-cloud@latest/actions/learn-github-actions/understanding-github-actions](https://docs.github.com/enterprise-cloud@latest/actions/learn-github-actions/understanding-github-actions)
23. Understanding GitHub Actions - GitHub Docs, accessed August 17,
    2025, [https://docs.github.com/en/actions/learn-github-actions/understanding-github-actions](https://docs.github.com/en/actions/learn-github-actions/understanding-github-actions)
24. Bash-Script vs. Stored Procedure vs. Traditional ETL Tools vs. Python-Script, accessed August 17,
    2025, [https://www.dedp.online/part-2/4-ce/bash-stored-procedure-etl-python-script.html](https://www.dedp.online/part-2/4-ce/bash-stored-procedure-etl-python-script.html)
25. Introduction to automation with Bash scripts | Opensource.com, accessed August 17,
    2025, [https://opensource.com/article/19/12/automation-bash-scripts](https://opensource.com/article/19/12/automation-bash-scripts)
26. A Simple Makefile Tutorial - Colby Computer Science, accessed August 17,
    2025, [https://www.cs.colby.edu/maxwell/courses/tutorials/maketutor/](https://www.cs.colby.edu/maxwell/courses/tutorials/maketutor/)
27. What is a JavaScript task runner? - Educative.io, accessed August 17,
    2025, [https://www.educative.io/answers/what-is-a-javascript-task-runner](https://www.educative.io/answers/what-is-a-javascript-task-runner)
28. xygeni.io, accessed August 17,
    2025, [https://xygeni.io/sscs-glossary/what-is-orchestration-in-software-development/#:~:text=Orchestration%20in%20software%20automates%20the,control%2C%20testing%2C%20and%20deployment.](https://xygeni.io/sscs-glossary/what-is-orchestration-in-software-development/#:~:text=Orchestration%20in%20software%20automates%20the,control%2C%20testing%2C%20and%20deployment.)
29. Makefile Tutorial - learn make by example - GitHub, accessed August 17,
    2025, [https://github.com/vampy/Makefile](https://github.com/vampy/Makefile)
30. MakeFile Tutorial - YouTube, accessed August 17,
    2025, [https://www.youtube.com/watch?v=U1I5UY_vWXI](https://www.youtube.com/watch?v=U1I5UY_vWXI)
31. Command Runners: make vs. scripts/ vs. just vs. taskfile : r/devops - Reddit, accessed August 17,
    2025, [https://www.reddit.com/r/devops/comments/1axj8t2/command_runners_make_vs_scripts_vs_just_vs/](https://www.reddit.com/r/devops/comments/1axj8t2/command_runners_make_vs_scripts_vs_just_vs/)
32. A universal task runner to run them all | by Brick Pop | Stack Me Up | Medium, accessed August 17,
    2025, [https://medium.com/stack-me-up/a-universal-task-runner-to-run-them-all-d93f1a1bf8b1](https://medium.com/stack-me-up/a-universal-task-runner-to-run-them-all-d93f1a1bf8b1)
33. Just, start using it! - Berk Karaal, accessed August 17,
    2025, [https://berkkaraal.com/blog/2024/12/06/just-start-using-it/](https://berkkaraal.com/blog/2024/12/06/just-start-using-it/)
34. Use just to manage project specific commands | developerlife.com, accessed August 17,
    2025, [https://developerlife.com/2023/08/28/justfile/](https://developerlife.com/2023/08/28/justfile/)
35. How I Use Just to Quickly Organize Project-Level Commands - DEV Community, accessed August 17,
    2025, [https://dev.to/casualcoders/just-the-best-way-to-handle-project-level-scripting-k4g](https://dev.to/casualcoders/just-the-best-way-to-handle-project-level-scripting-k4g)
36. I've tried the "just" task runner. Is it worth it? - twdev.blog, accessed August 17,
    2025, [https://twdev.blog/2024/06/just/](https://twdev.blog/2024/06/just/)
37. Task, accessed August 17, 2025, [https://taskfile.dev/](https://taskfile.dev/)
38. What is Bash Automation? | Use Bash to Automate Sys-Admin Tasks ..., accessed August 17,
    2025, [https://attuneops.io/bash-automation-guide/](https://attuneops.io/bash-automation-guide/)
39. Shell Scripting for Deployment Automation and Backup - AWS in Plain English, accessed August 17,
    2025, [https://aws.plainenglish.io/shell-scripting-for-devops-with-examples-b593f412fbf4](https://aws.plainenglish.io/shell-scripting-for-devops-with-examples-b593f412fbf4)
40. Conditions in bash scripting (if statements) | by Gudisa Gebi - Medium, accessed August 17,
    2025, [https://medium.com/@gudisagebi1/conditions-in-bash-scripting-if-statements-94e883a8d493](https://medium.com/@gudisagebi1/conditions-in-bash-scripting-if-statements-94e883a8d493)
41. How Relational Operators Work in Case Statements in Bash | Baeldung on Linux, accessed August 17,
    2025, [https://www.baeldung.com/linux/bash-case-relational-operators](https://www.baeldung.com/linux/bash-case-relational-operators)
42. Design patterns or best practices for shell scripts [closed] - Stack Overflow, accessed August 17,
    2025, [https://stackoverflow.com/questions/78497/design-patterns-or-best-practices-for-shell-scripts](https://stackoverflow.com/questions/78497/design-patterns-or-best-practices-for-shell-scripts)
43. Are YAMLs and Bash enough for CI/CD? : r/devops - Reddit, accessed August 17,
    2025, [https://www.reddit.com/r/devops/comments/1i29vyv/are_yamls_and_bash_enough_for_cicd/](https://www.reddit.com/r/devops/comments/1i29vyv/are_yamls_and_bash_enough_for_cicd/)
44. How to Parallelize a Bash for Loop | Baeldung on Linux, accessed August 17,
    2025, [https://www.baeldung.com/linux/bash-for-loop-parallel](https://www.baeldung.com/linux/bash-for-loop-parallel)
45. How do you run multiple programs in parallel from a bash script ..., accessed August 17,
    2025, [https://stackoverflow.com/questions/3004811/how-do-you-run-multiple-programs-in-parallel-from-a-bash-script](https://stackoverflow.com/questions/3004811/how-do-you-run-multiple-programs-in-parallel-from-a-bash-script)
46. How to Use Multithreading in Bash Scripts on Linux - Squash.io, accessed August 17,
    2025, [https://www.squash.io/exploring-multithreading-in-bash-scripts-on-linux/](https://www.squash.io/exploring-multithreading-in-bash-scripts-on-linux/)
47. How to Use the xargs Command in Linux | Linode Docs, accessed August 17,
    2025, [https://www.linode.com/docs/guides/using-xargs-with-examples/](https://www.linode.com/docs/guides/using-xargs-with-examples/)
48. NAME — GNU Parallel 20250722 documentation, accessed August 17,
    2025, [https://www.gnu.org/s/parallel/man.html](https://www.gnu.org/s/parallel/man.html)
49. How can I use GNU Parallel to run a lot of commands in parallel?, accessed August 17,
    2025, [https://msi.umn.edu/our-resources/knowledge-base/jobs-faqs/how-can-i-use-gnu-parallel-run-lot-commands-parallel](https://msi.umn.edu/our-resources/knowledge-base/jobs-faqs/how-can-i-use-gnu-parallel-run-lot-commands-parallel)
50. NAME — GNU Parallel 20250722 documentation, accessed August 17,
    2025, [https://www.gnu.org/software/parallel/man.html](https://www.gnu.org/software/parallel/man.html)
51. A short tutorial on Gnu Parallel | The Bowman Lab, accessed August 17,
    2025, [https://www.polarmicrobes.org/a-short-tutorial-on-gnu-parallel/](https://www.polarmicrobes.org/a-short-tutorial-on-gnu-parallel/)
52. GNU parallel - Research IT, accessed August 17,
    2025, [https://docs-research-it.berkeley.edu/services/high-performance-computing/user-guide/running-your-jobs/gnu-parallel/](https://docs-research-it.berkeley.edu/services/high-performance-computing/user-guide/running-your-jobs/gnu-parallel/)
53. GNU Parallel - CU Research Computing User Guide, accessed August 17,
    2025, [https://curc.readthedocs.io/en/latest/software/GNUParallel.html](https://curc.readthedocs.io/en/latest/software/GNUParallel.html)
54. Parallelising Jobs with GNU Parallel - RONIN BLOG, accessed August 17,
    2025, [https://blog.ronin.cloud/gnu-parallel/](https://blog.ronin.cloud/gnu-parallel/)
55. Get started with GitLab CI/CD, accessed August 17, 2025, [https://docs.gitlab.com/ci/](https://docs.gitlab.com/ci/)
56. Migrating from GitLab CI/CD to GitHub Actions, accessed August 17,
    2025, [https://docs.github.com/actions/learn-github-actions/migrating-from-gitlab-cicd-to-github-actions](https://docs.github.com/actions/learn-github-actions/migrating-from-gitlab-cicd-to-github-actions)
57. GitLab Runner, accessed August 17, 2025, [https://docs.gitlab.com/runner/](https://docs.gitlab.com/runner/)
58. CI/CD YAML syntax reference - GitLab Docs, accessed August 17,
    2025, [https://docs.gitlab.com/ci/yaml/](https://docs.gitlab.com/ci/yaml/)
59. Tutorial: Create and run your first GitLab CI/CD pipeline | GitLab Docs, accessed August 17,
    2025, [https://docs.gitlab.com/ci/quick_start/](https://docs.gitlab.com/ci/quick_start/)
60. GitHub Actions documentation, accessed August 17,
    2025, [https://docs.github.com/actions](https://docs.github.com/actions)
61. GitLab CI vs. GitHub Actions: a Complete Comparison in 2025, accessed August 17,
    2025, [https://www.bytebase.com/blog/gitlab-ci-vs-github-actions/](https://www.bytebase.com/blog/gitlab-ci-vs-github-actions/)
62. Migrating from GitHub Actions - GitLab Docs, accessed August 17,
    2025, [https://docs.gitlab.com/ci/migration/github_actions/](https://docs.gitlab.com/ci/migration/github_actions/)
63. CI/CD YAML syntax reference | GitLab Docs, accessed August 17,
    2025, [https://docs.gitlab.com/ee/ci/yaml/index.html#include](https://docs.gitlab.com/ee/ci/yaml/index.html#include)
64. Secrets Management in GitLab CI/CD - Infisical, accessed August 17,
    2025, [https://infisical.com/blog/gitlab-secrets](https://infisical.com/blog/gitlab-secrets)
65. Using external secrets in CI | GitLab Docs, accessed August 17,
    2025, [https://docs.gitlab.com/ci/secrets/](https://docs.gitlab.com/ci/secrets/)
66. The Shell executor | GitLab Docs, accessed August 17,
    2025, [https://docs.gitlab.com/runner/executors/shell/](https://docs.gitlab.com/runner/executors/shell/)
67. GitHub Actions, accessed August 17, 2025, [https://github.com/features/actions](https://github.com/features/actions)
68. Learn to Use GitHub Actions: a Step-by-Step Guide - freeCodeCamp, accessed August 17,
    2025, [https://www.freecodecamp.org/news/learn-to-use-github-actions-step-by-step-guide/](https://www.freecodecamp.org/news/learn-to-use-github-actions-step-by-step-guide/)
69. GitHub Actions documentation - GitHub Docs, accessed August 17,
    2025, [https://docs.github.com/en/actions](https://docs.github.com/en/actions)
70. Creating a composite action - GitHub Docs, accessed August 17,
    2025, [https://docs.github.com/en/actions/creating-actions/creating-a-composite-action](https://docs.github.com/en/actions/creating-actions/creating-a-composite-action)
71. Best Practices for Managing Secrets in GitHub Actions - Blacksmith, accessed August 17,
    2025, [https://www.blacksmith.sh/blog/best-practices-for-managing-secrets-in-github-actions](https://www.blacksmith.sh/blog/best-practices-for-managing-secrets-in-github-actions)
72. 8 GitHub Actions Secrets Management Best Practices to Follow - StepSecurity, accessed August 17,
    2025, [https://www.stepsecurity.io/blog/github-actions-secrets-management-best-practices](https://www.stepsecurity.io/blog/github-actions-secrets-management-best-practices)
73. Using secrets in GitHub Actions, accessed August 17,
    2025, [https://docs.github.com/actions/security-guides/using-secrets-in-github-actions](https://docs.github.com/actions/security-guides/using-secrets-in-github-actions)
74. Using secrets in GitHub Actions - GitHub Docs, accessed August 17,
    2025, [https://docs.github.com/en/actions/security-guides/using-secrets-in-github-actions](https://docs.github.com/en/actions/security-guides/using-secrets-in-github-actions)
75. Building a CI/CD Workflow with GitHub Actions | GitHub Resources ..., accessed August 17,
    2025, [https://resources.github.com/learn/pathways/automation/essentials/building-a-workflow-with-github-actions/](https://resources.github.com/learn/pathways/automation/essentials/building-a-workflow-with-github-actions/)
76. Gitlab CI vs Jenkins vs GitHub Actions : r/devops - Reddit, accessed August 17,
    2025, [https://www.reddit.com/r/devops/comments/105a2bn/gitlab_ci_vs_jenkins_vs_github_actions/](https://www.reddit.com/r/devops/comments/105a2bn/gitlab_ci_vs_jenkins_vs_github_actions/)
77. From Makefile to Justfile (or Taskfile): Recipe Runner Replacement - YouTube, accessed August 17,
    2025, [https://www.youtube.com/watch?v=hgNN2wOE7lc](https://www.youtube.com/watch?v=hgNN2wOE7lc)