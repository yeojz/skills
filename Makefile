# Entry points for the scripts in this repo, so tooling that looks for a
# declared command finds one without a package.json.
.PHONY: validate test

validate:
	./validate.sh

test:
	./plugins/jz/hooks/test-hooks.sh
