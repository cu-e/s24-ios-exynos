PYTHON ?= python3
.PHONY: check test validate doctor status board board-check capabilities capabilities-check tasks sources
check: validate board-check capabilities-check test
validate:
	$(PYTHON) tools/lab.py validate
test:
	$(PYTHON) -m unittest discover -s tests -v
doctor:
	$(PYTHON) tools/lab.py doctor
status:
	$(PYTHON) tools/lab.py status --write
board:
	$(PYTHON) tools/lab.py board --write
board-check:
	$(PYTHON) tools/lab.py board --check
capabilities:
	$(PYTHON) tools/capabilities.py --write
capabilities-check:
	$(PYTHON) tools/capabilities.py --check
tasks:
	$(PYTHON) tools/lab.py task list
sources:
	$(PYTHON) tools/lab.py sources
