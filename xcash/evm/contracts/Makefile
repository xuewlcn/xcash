FORGE ?= forge
OPENZEPPELIN_CONTRACTS_VERSION := v5.6.1

.PHONY: all deps build test clean fixtures

all: build fixtures

deps:
	@test -f lib/openzeppelin-contracts/package.json || \
		$(FORGE) install OpenZeppelin/openzeppelin-contracts@$(OPENZEPPELIN_CONTRACTS_VERSION) --no-git --shallow
	@python3 -c "import json; version=json.load(open('lib/openzeppelin-contracts/package.json'))['version']; assert version == '$(OPENZEPPELIN_CONTRACTS_VERSION)'[1:], f'openzeppelin-contracts version mismatch: {version}'"

build: deps
	$(FORGE) build --offline
	@mkdir -p artifacts
	@cp out/XcashDepositTemplate.sol/XcashDepositTemplate.json artifacts/XcashDepositTemplate.json
	@python3 -c "import json; d=json.load(open('artifacts/XcashDepositTemplate.json')); print(d['bytecode']['object'])" > artifacts/XcashDepositTemplate.bin
	@python3 -c "import json; d=json.load(open('artifacts/XcashDepositTemplate.json')); print(json.dumps(d['abi'], indent=2, ensure_ascii=False))" > artifacts/XcashDepositTemplate.abi.json
	@cp out/XcashDepositFactory.sol/XcashDepositFactory.json artifacts/XcashDepositFactory.json
	@python3 -c "import json; d=json.load(open('artifacts/XcashDepositFactory.json')); print(d['bytecode']['object'])" > artifacts/XcashDepositFactory.bin
	@python3 -c "import json; d=json.load(open('artifacts/XcashDepositFactory.json')); print(json.dumps(d['abi'], indent=2, ensure_ascii=False))" > artifacts/XcashDepositFactory.abi.json

test: deps
	$(FORGE) test --offline -vvv

fixtures: deps
	@mkdir -p ../tests/fixtures
	$(FORGE) script scripts/DumpXcashDepositFixtures.s.sol --tc DumpXcashDepositFixtures --offline

clean:
	rm -rf out/ cache/
