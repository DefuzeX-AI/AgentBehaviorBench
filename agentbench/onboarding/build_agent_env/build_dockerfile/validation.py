"""Catch common generated Dockerfile mistakes before starting a container build."""

import shlex

from ..common.errors import BuildError


def validate_dockerfile(content: str) -> None:
    """Check install ordering and shell quoting; Docker remains the full validator.

    Input is generated Dockerfile text. No instructions are executed. This covers
    simple generated Python images, including multiline shell RUN instructions.
    """
    source_copied = False
    for line in content.replace("\\\n", " ").splitlines():
        instruction, _, value = line.strip().partition(" ")
        if instruction.upper() == "FROM":
            source_copied = False
        if instruction.upper() == "COPY":
            # COPY agent/ ... and JSON-form COPY both make source available.
            tokens = shlex.split(value.replace("[", " ").replace("]", " ").replace(",", " "))
            if any(token.rstrip("/") in {"agent", "./agent", "."} for token in tokens[:-1]):
                source_copied = True
        if instruction.upper() != "RUN":
            continue
        lexer = shlex.shlex(value, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
        for index, token in enumerate(tokens):
            if token != "install" or not any("pip" in part for part in tokens[:index]):
                continue
            arguments = []
            for argument in tokens[index + 1:]:
                if argument in {"&&", "||", ";"}:
                    break
                arguments.append(argument)
            if any(item in {"<", ">", ">=", "<=", ">>"} for item in arguments):
                raise BuildError("Quote pip version constraints in Dockerfile RUN instructions")
            if any(item.startswith(("./agent", "/opt/agent/agent")) for item in arguments) and not source_copied:
                raise BuildError("Dockerfile must COPY Agent source before installing it")
