FROM abb-harness-repair-validation:20261016
USER root
RUN python -m pip uninstall -y kuma-defuzex && python -c "import importlib.util; assert importlib.util.find_spec('kuma') is None"
