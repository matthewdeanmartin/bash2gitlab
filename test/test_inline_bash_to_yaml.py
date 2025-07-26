from bash2gitlab.inline_bash_to_yaml import inline_gitlab_scripts


def test_yaml_it():
    input_yaml = """\
    stages:
      - build
    
    build:job:
      stage: build
      script:
        - ./build.sh
    """

    bash_scripts = {
        "./build.sh": "make build"
    }

    result = inline_gitlab_scripts(input_yaml, script_sources=bash_scripts)
    assert result.replace(" ","") =="""\
    stages:
      - build
    
    build:job:
      stage: build
      script:
        - make build
    """.replace(" ","")
