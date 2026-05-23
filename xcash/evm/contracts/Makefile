SOLC ?= solc
FORGE ?= forge
SOLC_BIN := $(shell command -v $(SOLC) 2>/dev/null || printf "%s" "$(SOLC)")

.PHONY: all build build-yul build-sol test clean fixtures

all: build fixtures

build: build-yul build-sol

build-yul:
	@$(SOLC) --version | grep -q "Version: 0.8.35" || \
		(echo "build-yul requires solc 0.8.35; set SOLC=/path/to/solc-0.8.35" >&2; exit 1)
	@mkdir -p artifacts
	$(SOLC) --strict-assembly --bin --optimize --optimize-runs=200 src/NativeCollector.yul \
		| awk '/Binary representation:/{flag=1;next} flag{printf "0x%s", $$0;exit}' > artifacts/NativeCollector.bin
	$(SOLC) --strict-assembly --bin --optimize --optimize-runs=200 src/ERC20Collector.yul \
		| awk '/Binary representation:/{flag=1;next} flag{printf "0x%s", $$0;exit}' > artifacts/ERC20Collector.bin
	@test -s artifacts/NativeCollector.bin
	@test -s artifacts/ERC20Collector.bin

build-sol:
	$(FORGE) build --skip yul --use $(SOLC_BIN) --offline
	@mkdir -p artifacts
	@cp out/PaymentCollectorFactory.sol/PaymentCollectorFactory.json artifacts/PaymentCollectorFactory.json
	@python3 -c "import json; d=json.load(open('artifacts/PaymentCollectorFactory.json')); print(d['bytecode']['object'][2:])" > artifacts/PaymentCollectorFactory.bin
	@python3 -c "import json; d=json.load(open('artifacts/PaymentCollectorFactory.json')); print(json.dumps(d['abi'], indent=2, ensure_ascii=False))" > artifacts/PaymentCollectorFactory.abi.json

test:
	$(FORGE) test --skip yul --use $(SOLC_BIN) --offline -vvv

fixtures: build-yul
	@mkdir -p ../tests/fixtures
	$(FORGE) script scripts/DumpFixtures.s.sol --tc DumpFixtures --use $(SOLC_BIN) --offline

clean:
	rm -rf out/ cache/ artifacts/*.bin artifacts/*.json
