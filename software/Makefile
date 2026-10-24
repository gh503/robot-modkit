# 注意：本机装了 ROS 2 Humble，pytest 会自动加载 launch_testing 插件并因缺 pyyaml 报错。
# 因此这里显式关闭插件自动加载。
PY ?= $(shell test -x ../.venv/bin/python && echo ../.venv/bin/python || echo python3)

.PHONY: test install demo lint
install:
	$(PY) -m pip install -e .

test:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PY) -m pytest -q

demo:
	$(PY) -m modkit.cli --sim scan
	$(PY) -m modkit.cli --sim pose --x 150 --y 0 --z 150
